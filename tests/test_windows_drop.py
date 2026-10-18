import unittest
from collections import deque
from unittest.mock import Mock

from offline_pdf.windows_drop import WM_DROPFILES, NativeFileDrop, read_drop_paths


class FakeShell:
    def __init__(self, paths):
        self.paths = paths
        self.finished = []

    def DragQueryFileW(self, handle, index, buffer, size):
        if index == 0xFFFFFFFF:
            return len(self.paths)
        text = self.paths[index]
        if buffer is not None:
            buffer.value = text
        return len(text)

    def DragFinish(self, handle):
        self.finished.append(handle)


class DropTests(unittest.TestCase):
    def test_unicode_spaces_and_braces_are_preserved(self):
        paths = ["C:\\임대 자료\\첫 문서.pdf", "D:\\괄호 {자료}\\second file.PDF"]
        self.assertEqual(read_drop_paths(FakeShell(paths), 100), paths)

    def test_drop_is_queued_and_handle_is_released(self):
        support = NativeFileDrop.__new__(NativeFileDrop)
        support._closing = False
        support._pending = deque()
        support._timer_id = None
        support._shell = FakeShell(["C:\\한글 문서.pdf"])
        support.root = Mock()
        support.root.after.return_value = "queued-drop"
        support.on_files = Mock()
        self.assertEqual(support._window_proc(5, WM_DROPFILES, 101, 0, 0, 0), 0)
        self.assertEqual(support._shell.finished, [101])
        support.on_files.assert_not_called()
        support.root.assert_not_called()
        self.assertEqual(support.root.mock_calls, [], "No Tk API may run inside WndProc")
        support._poll_files()
        support.on_files.assert_called_once_with(["C:\\한글 문서.pdf"])
        self.assertFalse(support._pending)
        support.root.after.assert_called_once_with(75, support._poll_files)

    def test_native_handle_released_even_if_queue_fails(self):
        support = NativeFileDrop.__new__(NativeFileDrop)
        support._closing = False
        support._shell = FakeShell(["C:\\file.pdf"])
        support._queue_files = Mock(side_effect=RuntimeError("Tk is closing"))
        self.assertEqual(support._window_proc(5, WM_DROPFILES, 102, 0, 0, 0), 0)
        self.assertEqual(support._shell.finished, [102])

    def test_close_cancels_pending_drop(self):
        support = NativeFileDrop.__new__(NativeFileDrop)
        support._closing = False
        support._pending = deque([("C:\\private.pdf",)])
        support._timer_id = "drop-1"
        support.handles = set()
        support.enabled = True
        support.root = Mock()
        support.close()
        support.close()
        support.root.after_cancel.assert_called_once_with("drop-1")
        self.assertFalse(support.enabled)
        self.assertFalse(support._pending)

    def test_closed_poller_discards_delivery(self):
        support = NativeFileDrop.__new__(NativeFileDrop)
        support._closing = True
        support._pending = deque([("C:\\private.pdf",)])
        support._timer_id = "drop-1"
        support.root = Mock()
        support.on_files = Mock()
        support._poll_files()
        support.on_files.assert_not_called()
        self.assertEqual(support.root.mock_calls, [])

    def test_queued_batches_keep_order(self):
        support = NativeFileDrop.__new__(NativeFileDrop)
        support._closing = False
        support._pending = deque()
        support._timer_id = None
        support.root = Mock()
        support.on_files = Mock()
        support._queue_files(["C:\\one.pdf", "C:\\two.pdf"])
        support._queue_files(["C:\\three.pdf"])
        self.assertEqual(support.root.mock_calls, [])
        support._poll_files()
        support._poll_files()
        self.assertEqual(
            [call.args[0] for call in support.on_files.call_args_list],
            [["C:\\one.pdf", "C:\\two.pdf"], ["C:\\three.pdf"]],
        )


if __name__ == "__main__":
    unittest.main()
