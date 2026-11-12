"""Manual updater dialog; network access is confined to a spawned process."""

import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from . import __version__, theme
from . import ctk_widgets as ttk
from .update_service import RELEASES, UpdateError, verify_file, worker

UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{9DC9CDFB-9463-416E-B5AB-E5E49805C3A7}_is1"


def installed_location():
    """Auto-install only into a registered installation of this exact executable."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return None
    import winreg

    folder = Path(sys.executable).resolve().parent
    for hive, mode in (
        (winreg.HKEY_CURRENT_USER, "/CURRENTUSER"),
        (winreg.HKEY_LOCAL_MACHINE, "/ALLUSERS"),
    ):
        try:
            with winreg.OpenKey(hive, UNINSTALL) as handle:
                value = winreg.QueryValueEx(handle, "InstallLocation")[0]
            if os.path.normcase(str(Path(value).resolve())) == os.path.normcase(str(folder)):
                return folder, mode
        except OSError:
            continue
    return None


class UpdateDialog:
    def __init__(self, app):
        self.app = app
        self.process = self.events = None
        self.folder = None
        self.release = self.downloaded = None
        self.dead_at = None
        self.closed = False
        self.dialog = ctk.CTkToplevel(app.root)
        self.dialog.title("최신버전 확인")
        self.dialog.resizable(False, False)
        self.dialog.transient(app.root)
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
        body = ttk.Frame(self.dialog)
        body.pack(fill="both", expand=True, padx=24, pady=20)
        ttk.Label(body, text="최신버전 확인", font=(theme.BOLD_FAMILY, 18, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"버전 {__version__}").pack(anchor="w", pady=8)
        self.status = ttk.Label(
            body, text="정식 릴리즈를 확인하고 있습니다…", wraplength=450, justify="left"
        )
        self.status.pack(fill="x", pady=10)
        ttk.Label(
            body,
            text="이 기능은 GitHub에 접속합니다. 문서·파일명·암호는 전송하지 않습니다.",
            wraplength=450,
            style="Muted.TLabel",
        ).pack(fill="x", pady=8)
        self.progress = ctk.CTkProgressBar(body, mode="indeterminate")
        self.progress.pack(fill="x", pady=8)
        self.progress.start()
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="닫기", command=self.close).pack(side="right")
        self.button = ttk.Button(actions, text="업데이트", command=self.update, state="disabled")
        self.button.pack(side="right", padx=8)
        self.launch("check")
        self.dialog.after(150, self.poll)

    def launch(self, action):
        ctx = mp.get_context("spawn")
        self.events = ctx.Queue()
        self.process = ctx.Process(
            target=worker,
            args=(
                action,
                __version__,
                self.events,
                self.release["tag"] if self.release else None,
                self.folder,
            ),
        )
        self.dead_at = None
        try:
            self.process.start()
        except Exception:
            self.process = None
            self.stop()
            self.release = self.downloaded = None
            self.status.config(text="업데이트 확인 프로세스를 실행하지 못했습니다.")
            self.progress.stop()
            self.button.config(text="다시 확인", state="normal")
        self.action = action

    def stop(self):
        if self.process:
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
            self.process = None
        if self.events:
            self.events.close()
            self.events = None

    def poll(self):
        if self.closed:
            return
        if self.process:
            try:
                while self.process:
                    event = self.events.get_nowait()
                    kind = event["type"]
                    if kind == "progress":
                        if event["total"]:
                            self.progress.stop()
                            self.progress.configure(mode="determinate")
                            self.progress.set(event["current"] / event["total"])
                    else:
                        self.stop()
                        self.progress.stop()
                        if kind == "release":
                            self.release = event
                            self.status.config(
                                text=f"새 버전 {event['version']}이 있습니다."
                                if event["available"]
                                else "최신 버전입니다."
                            )
                            if event["available"]:
                                self.button.config(state="normal")
                                if not installed_location() or not event["installable"]:
                                    self.status.config(
                                        text=f"새 버전 {event['version']}이 있습니다. 자동 설치는 등록된 설치형에서 지원합니다. 공식 다운로드 페이지를 엽니다."
                                    )
                        elif kind == "downloaded":
                            self.downloaded = event
                            self.status.config(
                                text="검증이 완료되었습니다. ‘업데이트 설치’를 누르면 프로그램을 종료하고 설치파일을 실행합니다."
                            )
                            self.button.config(text="업데이트 설치", state="normal")
                        else:
                            self.release = None
                            self.downloaded = None
                            self.status.config(text=event["message"])
                            self.button.config(text="다시 확인", state="normal")
            except queue.Empty:
                pass
            if self.process and not self.process.is_alive():
                if self.dead_at is None:
                    self.dead_at = time.monotonic()
                elif time.monotonic() - self.dead_at > 1:
                    self.stop()
                    self.release = self.downloaded = None
                    self.progress.stop()
                    self.status.config(
                        text="업데이트 확인 프로세스가 종료되었습니다. 다시 시도하세요."
                    )
                    self.button.config(text="다시 확인", state="normal")
        self.dialog.after(150, self.poll)

    def update(self):
        if self.process:
            return
        if self.downloaded:
            return self.install()
        if not self.release:
            self.button.config(state="disabled")
            self.progress.configure(mode="indeterminate")
            self.progress.start()
            return self.launch("check")
        location = installed_location()
        if not location or not self.release["installable"]:
            from .about import open_path

            return open_path(self.release.get("url", RELEASES + "/latest"))
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
        self.folder = tempfile.mkdtemp(prefix="OfflinePDF-update-")
        self.button.config(state="disabled")
        self.status.config(text="설치파일을 다운로드하고 검증하고 있습니다…")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.launch("download")

    def install(self):
        if self.app.busy():
            self.status.config(text="PDF 작업을 완료하거나 취소한 뒤 업데이트를 설치하세요.")
            return
        location = installed_location()
        if not location:
            self.status.config(
                text="설치 위치를 확인하지 못했습니다. 공식 다운로드 페이지에서 업데이트하세요."
            )
            return
        if not messagebox.askokcancel(
            "업데이트 설치", "프로그램을 종료하고 업데이트를 설치하시겠습니까?", parent=self.dialog
        ):
            return
        if self.app.busy():
            self.status.config(text="PDF 작업을 완료하거나 취소한 뒤 업데이트를 설치하세요.")
            return
        try:
            verify_file(self.downloaded["path"], self.downloaded["sha256"])
            folder, mode = location
            subprocess.Popen([self.downloaded["path"], mode, f"/DIR={folder}", "/NORESTART"])
        except (OSError, UpdateError):
            self.status.config(
                text="설치파일을 실행하지 못했습니다. 보안 정책 또는 파일 검증 상태를 확인하세요."
            )
            return
        # Installer needs its files until it exits; do not delete this directory.
        self.folder = None
        self.app._installing = True
        self.app.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop()
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder = None
        self.dialog.destroy()


def show_updates(app):
    current = getattr(app, "update_dialog", None)
    if current and not current.closed:
        current.dialog.lift()
        return current
    app.update_dialog = UpdateDialog(app)
    return app.update_dialog
