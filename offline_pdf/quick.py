"""Compact Explorer task window. Processing stays in the existing worker."""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from tkinter import Canvas, filedialog

import customtkinter as ctk

from .branding import set_brand
from .engine import UserError, check_local_path, disable_network, open_pdf, worker
from .explorer import ACTIONS


def make_job(action, files, output, passwords, output_password=""):
    """Validate all inputs before processing; never silently omit a selection."""
    paths = sorted({str(check_local_path(p)) for p in files}, key=str.casefold)
    if not paths or any(Path(p).suffix.lower() != ".pdf" or not Path(p).is_file() for p in paths):
        raise UserError("선택한 PDF 파일을 찾을 수 없습니다.")
    options = {"compression": "권장", "scale": "1.5", "split_mode": "페이지별로 나누기"}
    if output_password:
        options["output_password"] = output_password
    if action == "merge" and len({v for v in passwords.values() if v}) > 1 and not output_password:
        raise UserError("서로 다른 암호의 PDF를 합치려면 결과에 사용할 새 암호를 설정하세요.")
    return {
        "tool": action,
        "files": paths,
        "output": str(check_local_path(output)),
        "passwords": dict(passwords),
        "options": options,
        "stage_id": uuid.uuid4().hex,
    }


class QuickWindow:
    def __init__(self, root, inbox):
        self.root, self.inbox = root, inbox
        self.pending = []
        self.changed = time.monotonic()
        self.state = "collecting"
        self.process = self.events = self.cancel = None
        self.stage = None
        self.cancel_at = self.dead_at = None
        self.folder = None
        self.files = []
        self.passwords = {}
        self.output_password = ""
        self.prompt = None
        root.title("OfflinePDF · 바로 실행")
        root.geometry("480x340")
        root.resizable(False, False)
        root.configure(fg_color="#ffffff")
        self.body = ctk.CTkFrame(root, fg_color="#ffffff", corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=26, pady=(20, 8))
        heading = ctk.CTkFrame(self.body, fg_color="transparent", height=34)
        heading.pack(fill="x")
        brand = Canvas(heading, width=32, height=32, highlightthickness=0)
        brand.pack(side="left", padx=(0, 10))
        set_brand(root, brand)
        self.title = ctk.CTkLabel(
            heading,
            text="파일 준비 중",
            text_color="#192b44",
            font=("맑은 고딕", 20, "bold"),
            anchor="w",
        )
        self.title.pack(fill="x", side="left", expand=True)
        self.subtitle = ctk.CTkLabel(
            self.body, text="선택한 파일을 모으고 있습니다…", text_color="#718098", anchor="w"
        )
        self.subtitle.pack(fill="x", pady=(0, 14))
        self.detail = ctk.CTkLabel(
            self.body, text="", text_color="#364a64", anchor="w", wraplength=420, justify="left"
        )
        self.detail.pack(fill="x", pady=(0, 8))
        self.progress = ctk.CTkProgressBar(
            self.body, height=7, progress_color="#3278e4", fg_color="#e9eef6"
        )
        self.progress.pack(fill="x", pady=8)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.fields = ctk.CTkFrame(self.body, fg_color="transparent", height=1)
        self.fields.pack(fill="x")
        self.error = ctk.CTkLabel(
            self.body, text="", text_color="#b43b42", wraplength=420, justify="left"
        )
        self.error.pack(fill="x")
        self.note = ctk.CTkLabel(
            self.body, text="원본 파일은 변경하지 않습니다.", text_color="#7a8798", anchor="w"
        )
        self.note.pack(fill="x", side="bottom")
        self.footer = ctk.CTkFrame(root, fg_color="#f7f9fc", corner_radius=0)
        self.footer.pack(side="bottom", fill="x", before=self.body)
        self.buttons = []
        self.actions(("취소", self.request_close))
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.after(150, self.poll)

    def actions(self, *items):
        for button in self.buttons:
            button.destroy()
        self.buttons = []
        for index, (text, callback) in enumerate(reversed(items)):
            b = ctk.CTkButton(
                self.footer,
                text=text,
                command=callback,
                width=100,
                height=32,
                fg_color="#2369cf" if index == 0 else "#e6ebf2",
                text_color="white" if index == 0 else "#405269",
            )
            b.pack(side="right", padx=(6, 18 if index == 0 else 0), pady=14)
            self.buttons.append(b)

    def clear_fields(self):
        for child in self.fields.winfo_children():
            if isinstance(child, ctk.CTkEntry):
                child.delete(0, "end")
            child.destroy()
        self.prompt = None
        self.fields.configure(height=1)
        self.root.geometry("480x340")

    def ask_secret(self, path=None):
        self.state = "password"
        self.progress.stop()
        self.progress.pack_forget()
        self.clear_fields()
        self.root.geometry("480x430")
        self.title.configure(text="비밀번호 설정" if path is None else "문서 암호 입력")
        self.detail.configure(
            text="결과 PDF에 사용할 새 암호를 입력하세요." if path is None else Path(path).name
        )
        first = ctk.CTkEntry(
            self.fields, show="●", placeholder_text="새 암호" if path is None else "문서 암호"
        )
        first.pack(fill="x", pady=6)
        second = None
        if path is None:
            second = ctk.CTkEntry(self.fields, show="●", placeholder_text="새 암호 확인")
            second.pack(fill="x", pady=6)
        self.prompt = (path, first, second)
        first.focus_set()
        first.bind("<Return>", lambda e: self.confirm_secret())
        if second:
            second.bind("<Return>", lambda e: self.confirm_secret())
        self.note.configure(text="입력한 암호는 저장하지 않습니다.")
        self.actions(("취소", self.request_close), ("확인 후 실행", self.confirm_secret))

    def confirm_secret(self):
        path, first, second = self.prompt
        value = first.get()
        try:
            if not value:
                raise UserError("암호를 입력하세요.")
            if path is None:
                if value != second.get():
                    raise UserError("두 암호가 일치하지 않습니다.")
                if len(value) > 40:
                    raise UserError("PDF 저장 암호는 40자 이하로 입력하세요.")
                self.output_password = value
            else:
                with open_pdf(path, value)[0]:
                    pass
                self.passwords[path] = value
            self.error.configure(text="")
            self.clear_fields()
            self.prepare()
        except UserError as exc:
            self.error.configure(text=str(exc))
        except Exception:
            self.finish("error", "파일을 열 수 없습니다. 손상 여부와 읽기 권한을 확인하세요.")

    def begin(self, action, files):
        self.action = action
        self.files = sorted({str(check_local_path(p)) for p in files}, key=str.casefold)
        self.passwords = {}
        self.output_password = ""
        self.folder = None
        self.error.configure(text="")
        self.title.configure(text=ACTIONS[action] + " 준비 중")
        self.subtitle.configure(text=f"PDF {len(self.files)}개 · 원본 보존")
        self.prepare()

    def prepare(self):
        for path in self.files:
            if path not in self.passwords:
                # Validate before prompting; open_pdf consistently enforces permissions.
                import pymupdf as pdf

                with pdf.open(check_local_path(path)) as doc:
                    if not doc.is_pdf:
                        raise UserError("PDF 파일을 선택하세요.")
                    if doc.needs_pass:
                        self.ask_secret(path)
                        return
                self.passwords[path] = ""
        if (
            self.action == "protect"
            or self.action == "merge"
            and len({v for v in self.passwords.values() if v}) > 1
        ) and not self.output_password:
            self.ask_secret()
            return
        parents = {str(Path(p).parent) for p in self.files}
        output = (
            parents.pop()
            if len(parents) == 1
            else filedialog.askdirectory(parent=self.root, title="결과 저장 폴더")
        )
        if not output:
            self.finish("cancelled")
            return
        job = make_job(self.action, self.files, output, self.passwords, self.output_password)
        self.stage = Path(output).resolve() / (".offline-pdf-" + job["stage_id"])
        ctx = mp.get_context("spawn")
        self.events, self.cancel = ctx.Queue(), ctx.Event()
        self.process = ctx.Process(target=worker, args=(job, self.events, self.cancel))
        try:
            self.process.start()
        except Exception:
            self.process = None
            self.finish("error", "작업 프로세스를 실행할 수 없습니다.")
            return
        self.state = "running"
        self.cancel_at = self.dead_at = None
        self.title.configure(text=ACTIONS[self.action] + " 중")
        self.detail.configure(text="선택한 파일을 처리하고 있습니다.")
        self.note.configure(text="원본 파일은 변경하지 않습니다.")
        self.progress.pack(fill="x", pady=8, before=self.fields)
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.actions(("취소", self.request_close))

    def request_close(self):
        if self.process:
            if self.state == "cancelling":
                return
            self.progress.stop()
            self.detail.configure(text="작업을 취소하시겠습니까?")
            self.actions(("계속 처리", self.resume), ("작업 취소", self.cancel_job))
        elif self.state == "password":
            self.finish("cancelled")
        else:
            self.inbox.close()
            self.root.destroy()

    def resume(self):
        self.detail.configure(text="선택한 파일을 처리하고 있습니다.")
        self.actions(("취소", self.request_close))

    def cancel_job(self):
        self.cancel.set()
        self.cancel_at = time.monotonic()
        self.state = "cancelling"
        self.detail.configure(text="작업을 취소하고 임시 결과를 정리하고 있습니다.")
        self.actions()

    def finish(self, state, message=""):
        if self.process:
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
        self.process = None
        if self.events:
            self.events.close()
            self.events = None
        clean = True
        if self.stage:
            shutil.rmtree(self.stage, ignore_errors=True)
            clean = not self.stage.exists()
            self.stage = None
        self.passwords.clear()
        self.output_password = ""
        self.clear_fields()
        self.progress.stop()
        self.progress.pack_forget()
        self.state = state
        self.title.configure(
            text={"done": "작업 완료", "error": "처리하지 못했습니다", "cancelled": "작업 취소됨"}[
                state
            ]
        )
        self.detail.configure(
            text=message
            or (
                "작업을 중단하고 임시 결과를 정리했습니다."
                if state == "cancelled"
                else "결과를 저장했습니다."
            )
        )
        self.note.configure(text="원본 파일은 변경하지 않았습니다.")
        if not clean:
            self.error.configure(
                text="임시자료가 남았습니다. 저장 폴더의 .offline-pdf- 폴더를 확인하세요."
            )
        actions = [("닫기", self.request_close)]
        if self.folder:
            actions.append(("결과 폴더 열기", self.open_result))
        elif state == "error":
            actions.append(("다시 시도", self.retry))
        self.actions(*actions)

    def retry(self):
        try:
            self.begin(self.action, list(self.files))
        except Exception as exc:
            self.finish(
                "error",
                str(exc)
                if isinstance(exc, UserError)
                else "파일을 열 수 없습니다. 손상 여부와 읽기 권한을 확인하세요.",
            )

    def open_result(self):
        try:
            if os.name == "nt":
                os.startfile(self.folder)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.folder])
        except OSError:
            self.error.configure(text="파일 탐색기에서 결과 폴더를 확인하세요.")

    def poll(self):
        try:
            while True:
                self.pending.append(self.inbox.messages.get_nowait())
                self.changed = time.monotonic()
        except queue.Empty:
            pass
        if self.process:
            try:
                while self.process:
                    event = self.events.get_nowait()
                    kind = event["type"]
                    if kind == "progress" and self.state != "cancelling":
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.set(event["current"] / max(1, event["total"]))
                        self.detail.configure(text=event["label"])
                        percent = round(100 * event["current"] / max(1, event["total"]))
                        self.subtitle.configure(
                            text=f"PDF {len(self.files)}개 · 현재 단계 {percent}%"
                        )
                    elif kind == "done":
                        self.folder = event["folder"]
                        self.finish(
                            "done", f"PDF {len(self.files)}개 처리 완료\n{Path(self.folder).name}"
                        )
                    elif kind in ("cancelled", "error"):
                        self.finish(kind, event.get("message", ""))
            except queue.Empty:
                pass
            if self.process:
                if self.cancel_at and time.monotonic() - self.cancel_at > 3:
                    self.finish("cancelled")
                elif not self.process.is_alive():
                    if self.dead_at is None:
                        self.dead_at = time.monotonic()
                    elif time.monotonic() - self.dead_at > 0.6:
                        self.finish(
                            "error",
                            "작업 프로세스가 종료되었습니다. 파일과 저장 공간을 확인하세요.",
                        )
        if (
            self.pending
            and not self.process
            and self.state != "password"
            and time.monotonic() - self.changed >= 1
        ):
            action = self.pending[0]["action"]
            files = []
            while self.pending and self.pending[0]["action"] == action:
                files.extend(self.pending.pop(0)["files"])
            try:
                self.begin(action, files)
            except Exception as exc:
                self.finish(
                    "error",
                    str(exc)
                    if isinstance(exc, UserError)
                    else "파일을 열 수 없습니다. 손상 여부와 읽기 권한을 확인하세요.",
                )
            self.root.deiconify()
            self.root.lift()
        self.root.after(150, self.poll)


def main(inbox):
    disable_network()
    from .theme import avoid_native_titlebar_updates, font_family, register_fonts

    avoid_native_titlebar_updates()
    register_fonts()
    ctk.set_appearance_mode("light")
    root = ctk.CTk()
    ctk.ThemeManager.theme["CTkFont"]["family"] = font_family(root)
    QuickWindow(root, inbox)
    root.mainloop()
