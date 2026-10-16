import ctypes
import sys
import unittest
from unittest.mock import Mock

from offline_pdf.windows_drop import NativeFileDrop, WM_DROPFILES, read_drop_paths


class FakeShell:
    def __init__(self, paths):
        self.paths=paths
        self.finished=[]

    def DragQueryFileW(self, handle, index, buffer, size):
        if index==0xFFFFFFFF:return len(self.paths)
        text=self.paths[index]
        if buffer is not None:buffer.value=text
        return len(text)

    def DragFinish(self,handle):self.finished.append(handle)


class DropTests(unittest.TestCase):
    def test_unicode_spaces_and_braces_are_preserved(self):
        paths=['C:\\임대 자료\\첫 문서.pdf','D:\\괄호 {자료}\\second file.PDF']
        self.assertEqual(read_drop_paths(FakeShell(paths),100),paths)

    def test_drop_is_queued_and_handle_is_released(self):
        support=NativeFileDrop.__new__(NativeFileDrop)
        support._closing=False;support._pending=set();support._shell=FakeShell(['C:\\한글 문서.pdf'])
        support.root=Mock();support.root.after_idle.return_value='queued-drop'
        support.on_files=Mock()
        self.assertEqual(support._window_proc(5,WM_DROPFILES,101,0,0,0),0)
        self.assertEqual(support._shell.finished,[101]);support.on_files.assert_not_called()
        support.root.after_idle.call_args.args[0]()
        support.on_files.assert_called_once_with(['C:\\한글 문서.pdf'])
        self.assertFalse(support._pending)

    def test_native_handle_released_even_if_queue_fails(self):
        support=NativeFileDrop.__new__(NativeFileDrop)
        support._closing=False;support._shell=FakeShell(['C:\\file.pdf'])
        support._queue_files=Mock(side_effect=RuntimeError('Tk is closing'))
        self.assertEqual(support._window_proc(5,WM_DROPFILES,102,0,0,0),0)
        self.assertEqual(support._shell.finished,[102])

    def test_close_cancels_pending_drop(self):
        support=NativeFileDrop.__new__(NativeFileDrop)
        support._closing=False;support._pending={'drop-1'};support.handles=set();support.enabled=True
        support.root=Mock();support.close();support.close()
        support.root.after_cancel.assert_called_once_with('drop-1')
        self.assertFalse(support.enabled)


if __name__=='__main__':unittest.main()
