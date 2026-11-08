"""Windows Explorer verbs and local named-pipe handoff (no TCP sockets)."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ACTIONS = {
    "merge": "PDF 병합",
    "split": "PDF 분할",
    "compress": "PDF 압축",
    "upscale": "AI 업스케일",
}
KEY = r"Software\Classes\SystemFileAssociations\.pdf\shell\OfflinePDF"


def register_menu(remove=False):
    import winreg

    def delete(key):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
                children = []
                while True:
                    try:
                        children.append(winreg.EnumKey(handle, len(children)))
                    except OSError:
                        break
            for child in children:
                delete(key + "\\" + child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass

    delete(KEY)
    if remove:
        return
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(__file__).resolve().parents[1] / "main.py"))

    def write(key, values):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as handle:
            for name, value in values.items():
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, value)

    write(KEY, {"MUIVerb": "OfflinePDF", "SubCommands": "", "Icon": sys.executable})
    for action, label in ACTIONS.items():
        key = KEY + "\\shell\\" + action
        write(key, {"MUIVerb": label, "MultiSelectModel": "Player"})
        write(
            key + "\\command",
            {"": subprocess.list2cmdline(command + ["--explorer", action]) + ' "%1"'},
        )


def parse_args(argv):
    parser = argparse.ArgumentParser(description="OfflinePDF")
    parser.add_argument("--explorer", choices=ACTIONS)
    parser.add_argument("--register-explorer", action="store_true")
    parser.add_argument("--unregister-explorer", action="store_true")
    parser.add_argument("files", nargs="*")
    return parser.parse_args(argv)


class ExplorerInbox:
    """One Explorer-launched window per user; collect per-file shell invocations."""

    def __init__(self):
        from multiprocessing.connection import Listener

        identity = os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")
        suffix = hashlib.sha256(identity.encode()).hexdigest()[:24]
        self.address = r"\\.\pipe\OfflinePDF-" + suffix
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        self.mutex = kernel.CreateMutexW(None, False, "Local\\OfflinePDF-" + suffix)
        if not self.mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.owner = ctypes.get_last_error() != 183
        self.closed = False
        self.messages = queue.Queue()
        if self.owner:
            self.listener = Listener(self.address, family="AF_PIPE")
            threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        while not self.closed:
            try:
                with self.listener.accept() as connection:
                    message = json.loads(connection.recv_bytes(1_000_000))
                if (
                    isinstance(message, dict)
                    and message.get("action") in ACTIONS
                    and isinstance(message.get("files"), list)
                    and all(isinstance(p, str) for p in message["files"])
                ):
                    self.messages.put(message)
            except (OSError, ValueError, TypeError):
                continue

    def close(self):
        self.closed = True
        if self.owner:
            self.listener.close()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(self.mutex)

    def submit(self, action, files):
        message = {"action": action, "files": files}
        if self.owner:
            self.messages.put(message)
            return
        from multiprocessing.connection import Client

        for attempt in range(50):
            try:
                with Client(self.address, family="AF_PIPE") as connection:
                    connection.send_bytes(json.dumps(message).encode())
                return
            except OSError:
                if attempt == 49:
                    raise
                time.sleep(0.1)


def attach_inbox(app, inbox):
    """Debounce Explorer calls on Tk's thread; never change a running job."""
    app.explorer_inbox = inbox
    pending = []
    changed = 0.0

    def poll():
        nonlocal changed
        while True:
            try:
                pending.append(inbox.messages.get_nowait())
                changed = time.monotonic()
            except queue.Empty:
                break
        if pending and not app.busy() and time.monotonic() - changed >= 0.7:
            action = pending[0]["action"]
            batch = []
            while pending and pending[0]["action"] == action:
                batch.extend(pending.pop(0)["files"])
            paths = sorted({p for p in batch if Path(p).suffix.lower() == ".pdf"}, key=str.casefold)
            if app.tool != action or app.result_folder:
                app.files = []
                app.password_cache.clear()
            app.pending_results = None
            app.select_tool(action)
            app.add_paths(paths)
            parents = {str(Path(p).parent) for p in app.files}
            if len(parents) == 1:
                app.output.set(parents.pop())
                app.save_mode.set("지정한 폴더")
            elif app.files:
                from tkinter import filedialog

                folder = filedialog.askdirectory(parent=app.root, title="결과 저장 폴더")
                app.output.set(folder)
                app.save_mode.set("지정한 폴더")
            app.root.deiconify()
            app.root.lift()
        app.root.after(150, poll)

    poll()
