"""Explorer argument handling, batching, and native Windows pipe handoff."""

import os
import queue
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from offline_pdf.explorer import ExplorerInbox, attach_inbox, parse_args


class ExplorerTests(unittest.TestCase):
    def test_paths_are_literal_arguments(self):
        args = parse_args(["--explorer", "merge", r"C:\한글 폴더\a & b.pdf", r"C:\x.pdf"])
        self.assertEqual(args.explorer, "merge")
        self.assertEqual(args.files, [r"C:\한글 폴더\a & b.pdf", r"C:\x.pdf"])
        with self.assertRaises(SystemExit):
            parse_args(["--explorer", "unknown"])

    def test_batch_sort_and_defer_while_busy(self):
        inbox = SimpleNamespace(messages=queue.Queue())
        app = SimpleNamespace(
            root=Mock(),
            busy=Mock(return_value=True),
            tool="merge",
            result_folder=None,
            pending_results=None,
            files=[],
            password_cache={},
            output=Mock(),
            save_mode=Mock(),
            select_tool=Mock(),
        )
        app.add_paths = lambda paths: app.files.extend(paths)
        inbox.messages.put({"action": "merge", "files": ["/tmp/z.pdf", "/tmp/a.pdf"]})
        inbox.messages.put({"action": "merge", "files": ["/tmp/z.pdf", "/tmp/no.txt"]})
        with patch("offline_pdf.explorer.time.monotonic", return_value=1):
            attach_inbox(app, inbox)
        poll = app.root.after.call_args.args[1]
        with patch("offline_pdf.explorer.time.monotonic", return_value=3):
            poll()
            self.assertEqual(app.files, [])
            app.busy.return_value = False
            poll()
        self.assertEqual(app.files, ["/tmp/a.pdf", "/tmp/z.pdf"])
        app.output.set.assert_called_with("/tmp")
        app.select_tool.assert_called_once_with("merge")

    @unittest.skipUnless(os.name == "nt", "Windows registry required")
    def test_register_and_remove_menu(self):
        import uuid
        import winreg

        from offline_pdf.explorer import ACTIONS, register_menu

        key = "Software\\OfflinePDF-Test-" + uuid.uuid4().hex
        with patch("offline_pdf.explorer.KEY", key):
            try:
                register_menu()
                for action in ACTIONS:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, key + "\\shell\\" + action
                    ) as handle:
                        self.assertEqual(
                            winreg.QueryValueEx(handle, "MultiSelectModel")[0], "Player"
                        )
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, key + "\\shell\\" + action + "\\command"
                    ) as handle:
                        command = winreg.QueryValueEx(handle, "")[0]
                        self.assertIn("--explorer " + action, command)
                        self.assertTrue(command.endswith('"%1"'))
            finally:
                register_menu(remove=True)
            with self.assertRaises(FileNotFoundError):
                winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)

    @unittest.skipUnless(os.name == "nt", "Windows named pipes required")
    def test_native_pipe_collects_multiple_processes(self):
        inbox = ExplorerInbox()
        self.assertTrue(inbox.owner)
        code = (
            "from offline_pdf.explorer import ExplorerInbox; "
            "i=ExplorerInbox(); assert not i.owner; "
            "i.submit('merge', ['C:/한글 폴더/a.pdf'])"
        )
        try:
            for _ in range(3):
                subprocess.run(
                    [sys.executable, "-c", code],
                    check=True,
                    timeout=15,
                    cwd=Path(__file__).resolve().parents[1],
                )
            for _ in range(3):
                message = inbox.messages.get(timeout=10)
                self.assertEqual(message["files"], ["C:/한글 폴더/a.pdf"])
        finally:
            inbox.close()
