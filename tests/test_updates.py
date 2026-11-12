import hashlib
import io
import json
import multiprocessing as mp
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from offline_pdf.update_service import (
    SETUP,
    UpdateError,
    download,
    expected_hash,
    release_info,
    validate_url,
    version_tuple,
    worker,
)


def socket_probe(events):
    import socket

    with socket.socket():
        events.put(True)


class UpdateServiceTests(unittest.TestCase):
    def test_network_capable_child_does_not_enable_parent_network(self):
        import socket

        ctx = mp.get_context("spawn")
        events = ctx.Queue()
        process = ctx.Process(target=socket_probe, args=(events,))
        try:
            with patch.object(socket, "socket", side_effect=PermissionError("disabled")):
                process.start()
                self.assertTrue(events.get(timeout=15))
                with self.assertRaises(PermissionError):
                    socket.socket()
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            events.close()

    @unittest.skipUnless(os.name == "nt", "Windows registry required")
    def test_installed_location_matches_executable_directory(self):
        import winreg

        from offline_pdf import updates

        key = "Software\\OfflinePDF-update-test-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as temporary:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
                winreg.SetValueEx(handle, "InstallLocation", 0, winreg.REG_SZ, temporary)
            try:
                with (
                    patch.object(updates, "UNINSTALL", key),
                    patch("sys.frozen", True, create=True),
                    patch("sys.executable", str(Path(temporary) / "OfflinePDF.exe")),
                ):
                    self.assertEqual(
                        updates.installed_location(), (Path(temporary).resolve(), "/CURRENTUSER")
                    )
                with (
                    patch.object(updates, "UNINSTALL", key),
                    patch("sys.frozen", True, create=True),
                    patch("sys.executable", str(Path(temporary) / "portable" / "OfflinePDF.exe")),
                ):
                    self.assertIsNone(updates.installed_location())
            finally:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)

    def test_release_comparison_and_official_urls(self):
        info = release_info(
            {"tag_name": "v1.2.3.1", "assets": [{"name": SETUP}, {"name": "SHA256SUMS.txt"}]},
            "1.2.3",
        )
        self.assertTrue(info["available"])
        self.assertTrue(info["installable"])
        self.assertFalse(release_info({"tag_name": "v1.2.3"}, "1.2.4")["available"])
        for value in ("../../bad", "v1.2.3-beta", "https://evil.invalid", "1.2"):
            with self.assertRaises(UpdateError):
                version_tuple(value)
        for url in (
            "http://github.com/test",
            "https://github.com.evil.invalid/test",
            "https://user:secret@github.com/test",
            "file:///tmp/setup.exe",
        ):
            with self.assertRaises(UpdateError):
                validate_url(url)
        with self.assertRaises(UpdateError):
            release_info({"tag_name": "v1.3.0", "prerelease": True}, "1.2.3")

    def test_download_verifies_hash_and_rolls_back_partial_files(self):
        payload = b"synthetic installer, never executed"
        digest = hashlib.sha256(payload).hexdigest()
        manifest = (digest + "  " + SETUP).encode()

        class Response(io.BytesIO):
            headers = {"Content-Length": str(len(payload))}

        with tempfile.TemporaryDirectory() as temporary:
            for expected, success in (
                (manifest, True),
                (b"0" * 64 + b"  " + SETUP.encode(), False),
            ):
                with (
                    patch("offline_pdf.update_service.read_small", return_value=expected),
                    patch("offline_pdf.update_service.open_url", return_value=Response(payload)),
                ):
                    if success:
                        result = download("v1.2.4", temporary, Mock())
                        self.assertEqual(Path(result["path"]).read_bytes(), payload)
                        Path(result["path"]).unlink()
                    else:
                        with self.assertRaises(UpdateError):
                            download("v1.2.4", temporary, Mock())
                        self.assertEqual(list(Path(temporary).iterdir()), [])
        with self.assertRaises(UpdateError):
            expected_hash(manifest + b"\n" + manifest)

    def test_worker_emits_no_document_details_on_network_failure(self):
        events = Mock()
        with patch("offline_pdf.update_service.read_small", side_effect=OSError("SECRET PATH")):
            worker("check", "1.2.3", events)
        self.assertEqual(events.put.call_args.args[0]["type"], "error")
        self.assertNotIn("SECRET PATH", str(events.put.call_args))
        with patch(
            "offline_pdf.update_service.read_small",
            return_value=json.dumps({"tag_name": "v1.2.4"}).encode(),
        ):
            worker("check", "1.2.3", events)
        self.assertTrue(events.put.call_args.args[0]["available"])


class UpdateGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk

        try:
            self.root = ctk.CTk()
        except Exception:
            self.skipTest("Desktop unavailable")
        from offline_pdf.updates import UpdateDialog

        self.app = SimpleNamespace(root=self.root, busy=Mock(return_value=False), close=Mock())
        with patch.object(UpdateDialog, "launch") as launch:
            self.window = UpdateDialog(self.app)
            launch.assert_called_once_with("check")
        self.root.update()

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
            for timer in self.root.tk.call("after", "info"):
                self.root.after_cancel(timer)
            self.root.destroy()

    def test_busy_job_blocks_installer_then_requires_verified_file(self):
        from offline_pdf.updates import installed_location

        self.assertIsNone(installed_location())
        self.app.busy.return_value = True
        self.window.downloaded = {"path": "missing.exe", "sha256": "0" * 64}
        with patch("offline_pdf.updates.subprocess.Popen") as popen:
            self.window.install()
            popen.assert_not_called()
        self.app.busy.return_value = False
        with (
            patch(
                "offline_pdf.updates.installed_location",
                return_value=(Path("C:/OfflinePDF"), "/CURRENTUSER"),
            ),
            patch("offline_pdf.updates.messagebox.askokcancel", return_value=True),
            patch("offline_pdf.updates.subprocess.Popen") as popen,
        ):
            self.window.install()
            popen.assert_not_called()
            self.app.close.assert_not_called()

    def test_valid_installer_launch_and_close_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / SETUP
            path.write_bytes(b"test")
            self.window.downloaded = {
                "path": str(path),
                "sha256": hashlib.sha256(b"test").hexdigest(),
            }
            with (
                patch(
                    "offline_pdf.updates.installed_location",
                    return_value=(Path("C:/OfflinePDF"), "/CURRENTUSER"),
                ),
                patch("offline_pdf.updates.messagebox.askokcancel", return_value=True),
                patch("offline_pdf.updates.subprocess.Popen") as popen,
            ):
                self.window.install()
                self.assertIn("/CURRENTUSER", popen.call_args.args[0])
                self.app.close.assert_called_once()
                self.assertTrue(self.app._installing)
