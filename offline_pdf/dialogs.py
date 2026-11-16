"""Owner-relative Tk and native dialogs, including negative desktop coordinates."""

from __future__ import annotations

import sys
import tkinter as tk
from contextlib import contextmanager
from tkinter import filedialog as tk_filedialog
from tkinter import messagebox as tk_messagebox

import customtkinter as ctk

from . import ctk_widgets as ttk


def monitor_work_area(anchor):
    """Physical work area of the monitor containing most of the anchor rectangle."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    nearest = user32.MonitorFromRect
    nearest.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
    nearest.restype = wintypes.HANDLE
    get_info = user32.GetMonitorInfoW
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    get_info.restype = wintypes.BOOL
    rect = wintypes.RECT(*anchor)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    handle = nearest(ctypes.byref(rect), 2)
    if handle and get_info(handle, ctypes.byref(info)):
        work = info.rcWork
        return work.left, work.top, work.right, work.bottom
    return None


def widget_rect(widget):
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def center_position(owner, size, bounds):
    left, top, right, bottom = bounds
    width, height = size
    x = (owner[0] + owner[2] - width) // 2
    y = (owner[1] + owner[3] - height) // 2
    return max(left, min(x, right - width)), max(top, min(y, bottom - height))


def dialog_parent(parent):
    """A nested picker belongs to the active modal, rather than the main window."""
    if not isinstance(parent, tk.Misc):
        return parent
    grabbed = parent.grab_current()
    return (grabbed or parent).winfo_toplevel()


def place_dialog(dialog, owner):
    """Center on the owner, repeating after a DPI size change but not a manual move."""
    for sequence, attr in (
        ("<Configure>", "_position_binding"),
        ("<Destroy>", "_position_cleanup"),
    ):
        previous = getattr(dialog, attr, None)
        if previous:
            dialog.unbind(sequence, previous)
    timer = getattr(dialog, "_position_timer", None)
    if timer:
        dialog.after_cancel(timer)
    dialog._position_timer = None
    dialog.withdraw()
    dialog.transient(owner)
    dialog.update_idletasks()

    def position(initial=False):
        dialog._position_timer = None
        if not dialog.winfo_exists():
            return
        size = (dialog.winfo_width(), dialog.winfo_height())
        if initial:
            size = (max(size[0], dialog.winfo_reqwidth()), max(size[1], dialog.winfo_reqheight()))
        dialog._placed_size = size
        rect = widget_rect(owner)
        x, y = center_position(rect, size, monitor_work_area(rect) or rect)
        dialog.geometry(f"+{x}+{y}")

    def resized(event):
        if event.widget is dialog and (event.width, event.height) != dialog._placed_size:
            if dialog._position_timer:
                dialog.after_cancel(dialog._position_timer)
            # Geometry requested inside Configure can be lost by Tk's current
            # layout pass. Wait for it to finish before positioning the new size.
            dialog._position_timer = dialog.after_idle(position)

    def destroyed(event):
        if event.widget is dialog and dialog._position_timer:
            dialog.after_cancel(dialog._position_timer)
            dialog._position_timer = None

    position(initial=True)
    dialog._position_binding = dialog.bind("<Configure>", resized, add="+")
    dialog._position_cleanup = dialog.bind("<Destroy>", destroyed, add="+")
    dialog.deiconify()
    dialog.lift()


@contextmanager
def native_dialog_position(owner):
    """Place owned Windows dialogs when activated, without calling Tk in Win32 callbacks.

    Windows file dialogs can otherwise restore a position on another monitor.
    The hook is restricted to this UI thread, standard dialog windows owned by
    this parent, and the duration of the synchronous native dialog call.
    """
    if sys.platform != "win32" or not isinstance(owner, tk.Misc):
        yield
        return
    import ctypes
    from ctypes import wintypes

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    get_ancestor = user32.GetAncestor
    get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
    get_ancestor.restype = wintypes.HWND
    get_owner = user32.GetWindow
    get_owner.argtypes = [wintypes.HWND, wintypes.UINT]
    get_owner.restype = wintypes.HWND
    get_rect = user32.GetWindowRect
    get_rect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    get_rect.restype = wintypes.BOOL
    get_class = user32.GetClassNameW
    get_class.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    move = user32.SetWindowPos
    move.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    move.restype = wintypes.BOOL
    hook_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    install = user32.SetWindowsHookExW
    install.argtypes = [ctypes.c_int, hook_type, wintypes.HINSTANCE, wintypes.DWORD]
    install.restype = wintypes.HANDLE
    uninstall = user32.UnhookWindowsHookEx
    uninstall.argtypes = [wintypes.HANDLE]
    next_hook = user32.CallNextHookEx
    next_hook.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    next_hook.restype = ctypes.c_ssize_t
    owner.update_idletasks()
    owner_handle = get_ancestor(owner.winfo_id(), 2)  # GA_ROOT
    fallback = widget_rect(owner)
    bounds = monitor_work_area(fallback) or fallback
    placed = set()

    @hook_type
    def activated(code, wparam, lparam):
        try:
            if code == 5 and wparam not in placed:  # HCBT_ACTIVATE
                name = ctypes.create_unicode_buffer(64)
                get_class(wparam, name, len(name))
                parent = get_owner(wparam, 4)  # GW_OWNER
                ancestor = parent
                while ancestor and ancestor != owner_handle:
                    ancestor = get_owner(ancestor, 4)
                if name.value == "#32770" and ancestor == owner_handle:
                    parent_rect, rect = wintypes.RECT(), wintypes.RECT()
                    if get_rect(parent, ctypes.byref(parent_rect)) and get_rect(
                        wparam, ctypes.byref(rect)
                    ):
                        anchor = (
                            parent_rect.left,
                            parent_rect.top,
                            parent_rect.right,
                            parent_rect.bottom,
                        )
                        x, y = center_position(
                            anchor, (rect.right - rect.left, rect.bottom - rect.top), bounds
                        )
                        move(wparam, None, x, y, 0, 0, 0x0015)  # NOSIZE | NOZORDER | NOACTIVATE
                        placed.add(wparam)
        except Exception:
            # Exceptions must never escape a ctypes callback into Windows.
            pass
        return next_hook(None, code, wparam, lparam)

    handle = install(5, activated, None, kernel32.GetCurrentThreadId())  # WH_CBT
    try:
        yield
    finally:
        if handle:
            uninstall(handle)


class OwnedDialogs:
    def __init__(self, module):
        self.module = module

    def __getattr__(self, name):
        def show(*args, **kwargs):
            parent = dialog_parent(kwargs.get("parent"))
            kwargs["parent"] = parent
            with native_dialog_position(parent):
                return getattr(self.module, name)(*args, **kwargs)

        return show


filedialog = OwnedDialogs(tk_filedialog)
messagebox = OwnedDialogs(tk_messagebox)


def ask_text(parent, title, prompt):
    """A positioned replacement for simpledialog's primary-screen clamping."""
    owner = dialog_parent(parent)
    dialog = ctk.CTkToplevel(owner)
    dialog.title(title)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog)
    body.pack(fill="both", expand=True, padx=24, pady=20)
    ttk.Label(body, text=prompt, wraplength=440).pack(anchor="w", pady=(0, 12))
    value = tk.StringVar(master=dialog)
    entry = ttk.Entry(body, textvariable=value, width=40)
    entry.pack(fill="x")
    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(16, 0))
    result = None

    def submit(event=None):
        nonlocal result
        result = value.get()
        dialog.destroy()

    ttk.Button(actions, text="확인", command=submit).pack(side="right", padx=(8, 0))
    ttk.Button(actions, text="취소", command=dialog.destroy).pack(side="right")
    dialog.bind("<Return>", submit)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    place_dialog(dialog, owner)
    previous = owner.grab_current()
    dialog.grab_set()
    entry.focus_set()
    try:
        owner.wait_window(dialog)
    finally:
        if previous is not None and previous.winfo_exists():
            previous.grab_set()
    return result
