"""Windows file drops via Shell APIs, using Python's standard library only.

SPDX-License-Identifier: AGPL-3.0-or-later
No OLE plug-in, external binary, package download, or network is required.
"""
from __future__ import annotations

import ctypes
import sys

WM_DROPFILES = 0x0233
WM_NCDESTROY = 0x0082


def read_drop_paths(shell, handle):
    """Read Unicode paths individually; never split on spaces or braces."""
    count = shell.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
    paths = []
    for index in range(count):
        length = shell.DragQueryFileW(handle, index, None, 0)
        if not length:
            continue
        buffer = ctypes.create_unicode_buffer(length + 1)
        if shell.DragQueryFileW(handle, index, buffer, length + 1):
            paths.append(buffer.value)
    return paths


class NativeFileDrop:
    """Accept Explorer drops on a Tk window and its file list / preview.

    Must be created and closed on the Tk thread. Keep this object alive until
    close() so that Windows never calls a collected ctypes callback.
    """

    def __init__(self, root, on_files, widgets=()):
        self.root = root
        self.on_files = on_files
        self.enabled = False
        self.handles = set()
        self._closing = False
        self._pending = set()
        if sys.platform != 'win32':
            return

        from ctypes import wintypes as w
        self._user = ctypes.WinDLL('user32', use_last_error=True)
        self._shell = ctypes.WinDLL('shell32', use_last_error=True)
        self._comctl = ctypes.WinDLL('comctl32', use_last_error=True)
        ptr = ctypes.c_size_t
        result = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(result, w.HWND, w.UINT, ptr,
                                      ctypes.c_ssize_t, ptr, ptr)
        self._callback = proc_type(self._window_proc)
        self._subclass_id = id(self)

        self._user.GetAncestor.argtypes = [w.HWND, w.UINT]
        self._user.GetAncestor.restype = w.HWND
        self._shell.DragAcceptFiles.argtypes = [w.HWND, w.BOOL]
        self._shell.DragAcceptFiles.restype = None
        self._shell.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]
        self._shell.DragQueryFileW.restype = w.UINT
        self._shell.DragFinish.argtypes = [w.HANDLE]
        self._shell.DragFinish.restype = None
        self._comctl.SetWindowSubclass.argtypes = [w.HWND, proc_type, ptr, ptr]
        self._comctl.SetWindowSubclass.restype = w.BOOL
        self._comctl.RemoveWindowSubclass.argtypes = [w.HWND, proc_type, ptr]
        self._comctl.RemoveWindowSubclass.restype = w.BOOL
        self._comctl.DefSubclassProc.argtypes = [w.HWND, w.UINT, ptr, ctypes.c_ssize_t]
        self._comctl.DefSubclassProc.restype = result

        root.update_idletasks()
        root_handle = root.winfo_id()
        targets = {root_handle, self._user.GetAncestor(root_handle, 2)}
        targets.update(widget.winfo_id() for widget in widgets)
        try:
            for hwnd in targets:
                if not hwnd:
                    continue
                if not self._comctl.SetWindowSubclass(hwnd, self._callback,
                                                      self._subclass_id, 0):
                    raise OSError('Cannot register file-drop window procedure')
                self.handles.add(hwnd)
                self._shell.DragAcceptFiles(hwnd, True)
            self.enabled = bool(self.handles)
        except BaseException:
            self.close()
            raise

    def _queue_files(self, paths):
        # Return to Tk before opening PDFs or changing widgets.
        token = None
        def deliver():
            self._pending.discard(token)
            if not self._closing:
                self.on_files(paths)
        token = self.root.after_idle(deliver)
        self._pending.add(token)

    def _window_proc(self, hwnd, message, wparam, lparam, subclass_id, ref_data):
        if message == WM_DROPFILES:
            try:
                if not self._closing:
                    paths = read_drop_paths(self._shell, wparam)
                    self._queue_files(paths)
            except Exception:
                # No exception may escape a native callback. Drop data is not logged.
                pass
            finally:
                self._shell.DragFinish(wparam)
            return 0
        if message == WM_NCDESTROY:
            self._comctl.RemoveWindowSubclass(hwnd, self._callback, self._subclass_id)
            self.handles.discard(hwnd)
        return self._comctl.DefSubclassProc(hwnd, message, wparam, lparam)

    def close(self):
        if self._closing:
            return
        self._closing = True
        for token in tuple(self._pending):
            try:
                self.root.after_cancel(token)
            except Exception:
                pass
        self._pending.clear()
        for hwnd in tuple(self.handles):
            self._shell.DragAcceptFiles(hwnd, False)
            self._comctl.RemoveWindowSubclass(hwnd, self._callback, self._subclass_id)
        self.handles.clear()
        self.enabled = False
