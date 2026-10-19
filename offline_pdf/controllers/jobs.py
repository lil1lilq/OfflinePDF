"""Worker lifecycle, progress, cancellation and publication."""

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
from tkinter import messagebox

from ..engine import UserError, check_local_path, open_pdf, split_ranges, worker
from ..passwords import ask_password, cached_password, ensure_password


class JobController:
    """Worker lifecycle, progress, cancellation and publication."""

    def run(self, preview=False):
        if self.busy():
            return
        if not self.files:
            messagebox.showinfo("파일 추가", "처리할 파일을 먼저 추가하세요.", parent=self.root)
            return
        actual_tool = self.effective_tool()
        active_files = (
            [self.selected_file()]
            if preview or self.tool in ("extract", "split")
            else list(self.files)
        )
        if not all(path and self.accepted_path(path) for path in active_files):
            messagebox.showinfo(
                "파일 형식",
                "이 도구에서 지원하지 않는 파일을 목록에서 제거하거나 다른 도구를 선택하세요.",
                parent=self.root,
            )
            return
        for path in active_files:
            if not ensure_password(self, path):
                return
        if self.tool == "extract":
            if not self.organizer.doc or not self.organizer.matches(self.selected_file()):
                self.refresh_organizer()
                messagebox.showinfo(
                    "페이지 확인",
                    "페이지를 불러온 후 순서를 확인하고 다시 실행하세요.",
                    parent=self.root,
                )
                return
        if self.tool == "split" and self.options["split_mode"].get() == "N개 파일로 나누기":
            try:
                split_ranges(
                    self.document_page_count(),
                    self.options["split_count"].get(),
                    self.options["split_starts"].get(),
                )
            except UserError as exc:
                messagebox.showinfo("나누기 위치", str(exc), parent=self.root)
                return
        if self.tool == "redact" and len(self.files) != 1:
            messagebox.showinfo("파일 선택", "영구 삭제는 한 파일씩 처리하세요.", parent=self.root)
            return
        try:
            check_local_path(self.output.get())
        except UserError as exc:
            messagebox.showinfo("저장 폴더", str(exc), parent=self.root)
            return
        if not Path(self.output.get()).is_dir():
            messagebox.showinfo("저장 폴더", "결과를 저장할 폴더를 선택하세요.", parent=self.root)
            return
        if actual_tool in ("redact", "unlock", "pdf_images", "text", "crop"):
            notes = {
                "redact": "지정 영역을 실제 삭제하며 문서의 첨부파일·양식 필드·주석·링크·속성도 정리합니다. 잘린 페이지는 지원하지 않습니다. 지정 영역 밖의 정보는 남으므로 결과를 확인하세요.",
                "unlock": "결과 PDF의 암호가 제거됩니다.",
                "pdf_images": "결과 이미지에는 원본 PDF의 암호 보호가 적용되지 않습니다.",
                "text": "결과 TXT에는 원본 PDF의 암호 보호가 적용되지 않습니다.",
                "crop": "여백 자르기는 내용을 숨기는 기능입니다. 잘린 부분의 정보도 문서 안에 남습니다.",
            }
            if not messagebox.askokcancel(
                "작업 확인", notes[actual_tool] + "\n\n계속하시겠습니까?", parent=self.root
            ):
                return
        try:
            for path in active_files:
                if Path(path).suffix.lower() == ".pdf":
                    src, _ = open_pdf(
                        path,
                        cached_password(self, path),
                        extraction=self.tool in ("text", "pdf_images", "ocr"),
                    )
                    try:
                        signed = src.get_sigflags() > 0
                    finally:
                        src.close()
                    if signed and not messagebox.askokcancel(
                        "전자서명 문서",
                        "수정하면 기존 전자서명 검증 상태가 달라질 수 있습니다. 원본은 보존됩니다. 계속하시겠습니까?",
                        parent=self.root,
                    ):
                        return
        except UserError as exc:
            messagebox.showerror("파일 확인", str(exc), parent=self.root)
            return
        job = {
            "tool": actual_tool,
            "files": active_files,
            "output": self.output.get(),
            "options": {k: v.get() for k, v in self.options.items() if k != "hint"},
        }
        job["passwords"] = {p: cached_password(self, p) for p in active_files}
        if actual_tool == "unlock":
            job["options"].pop("output_password", None)
        if self.tool in ("merge", "images_pdf"):
            job["options"]["output_name"] = self.output_name.get()
        if (
            self.tool in ("merge", "images_pdf")
            and len({p for p in job["passwords"].values() if p}) > 1
            and not job["options"].get("output_password")
        ):
            password = ask_password(
                self,
                output=True,
                explanation="서로 다른 암호의 문서를 합칩니다. 결과 PDF에 사용할 새 암호를 설정하세요.",
            )
            if password is None:
                return
            job["options"]["output_password"] = password
        if preview:
            job["options"]["preview_only"] = True
        self.preview_job = preview
        self.converted_count = 0
        self.job_passwords = {}
        if not preview and actual_tool not in ("unlock", "text", "pdf_images"):
            for i, path in enumerate(active_files):
                self.job_passwords[f"{i + 1:03d}_"] = job["options"].get("output_password") or job[
                    "passwords"
                ].get(path, "")
            if self.tool in ("merge", "images_pdf"):
                self.job_passwords = {
                    "all": job["options"].get("output_password")
                    or next((v for v in job["passwords"].values() if v), "")
                }
        if self.tool == "extract":
            job["options"]["page_plan"] = self.organizer.model.plan()
        if self.tool == "redact":
            job["options"]["regions"] = self.regions.get(self.files[0], {})
        if self.tool == "ocr":
            job["options"]["language"] = {
                "한국어 + 영어": "kor+eng",
                "한국어": "kor",
                "영어": "eng",
            }.get(job["options"]["language"], job["options"]["language"])
        job["stage_id"] = uuid.uuid4().hex
        ctx = mp.get_context("spawn")
        self.events = ctx.Queue()
        self.cancel = ctx.Event()
        self.cancel_at = None
        self.stage = str(Path(self.output.get()).resolve() / (".offline-pdf-" + job["stage_id"]))
        self.process = ctx.Process(target=worker, args=(job, self.events, self.cancel))
        self.dead_at = None
        try:
            self.process.start()
        except Exception:
            self.process = None
            self.cleanup_stage()
            self.events.close()
            self.events = None
            messagebox.showerror(
                "실행 오류",
                "작업 프로세스를 실행할 수 없습니다. 백신·실행 권한·배포파일 구성을 확인하세요.",
                parent=self.root,
            )
            return
        if not preview:
            self.result_files = ()
            self.result_folder = None
            self.result_output = job["output"]
            self.result_tool = self.tool
        self.next_button.config(state="disabled")
        # Remove secrets from visible controls after the child has its own copy.
        for key in ("input_password", "output_password"):
            if key in self.options:
                self.options[key].set("")
        self.output_password_button.config(text="암호 추가")
        self.run_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.open_button.config(state="disabled")
        self.home_button.config(state="disabled")
        self.save_mode_combo.config(state="disabled")
        self.status.set("처리 중입니다. 원본 파일은 변경하지 않습니다.")
        self.progress["value"] = 0
        self.update_activity()

    def cancel_job(self):
        if self.process and self.cancel_at is None:
            self.cancel.set()
            self.cancel_at = time.monotonic()
            self.status.set("작업을 취소하고 임시 결과를 정리하고 있습니다.")

    def cleanup_stage(self):
        clean = True
        if self.stage:
            path = Path(self.stage)
            if path.name.startswith(".offline-pdf-"):
                shutil.rmtree(path, ignore_errors=True)
            clean = not path.exists()
            self.stage = None
        return clean

    def finish(self, message):
        if self.process:
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
        self.process = None
        self.cancel_at = None
        clean = self.cleanup_stage()
        if self.events:
            self.events.close()
            self.events = None
        self.update_file_summary()
        self.cancel_button.config(state="disabled")
        self.update_back_state()
        self.save_mode_combo.config(state="readonly")
        self.status.set(
            message
            if clean
            else message + " 임시자료가 남았습니다. 저장 폴더의 .offline-pdf- 폴더를 확인하세요."
        )
        self.update_activity()

    def poll(self):
        if self.process:
            try:
                while True:
                    event = self.events.get_nowait()
                    kind = event["type"]
                    if kind == "stage":
                        self.stage = event["folder"]
                    elif kind == "converted":
                        self.replace_converted_inputs(event["files"])
                    elif kind == "progress":
                        self.progress["value"] = 100 * event["current"] / max(1, event["total"])
                        self.status.set(event["label"])
                    elif kind == "done":
                        preview = self.preview_job
                        self.finish(
                            "미리보기 준비 완료"
                            if preview
                            else "완료했습니다. 결과를 확인하거나 “결과로 다음 작업”을 선택하세요."
                        )
                        if preview:
                            self.show_ai_comparison(event["folder"])
                        else:
                            self.remember_result(event["folder"])
                            if self.converted_count:
                                self.status.set(
                                    f"이미지 {self.converted_count}개를 PDF로 변경하고 작업을 완료했습니다."
                                )
                            self.progress["value"] = 100
                            self.open_button.config(state="normal")
                            self.result_passwords = {
                                p: self.job_passwords.get(
                                    "all",
                                    next(
                                        (
                                            v
                                            for k, v in self.job_passwords.items()
                                            if Path(p).name.startswith(k)
                                        ),
                                        "",
                                    ),
                                )
                                for p in self.result_files
                            }
                            if self.auto_open.get():
                                self.open_result()
                        break
                    elif kind == "cancelled":
                        self.finish("작업을 취소했습니다. 원본은 그대로 보관됩니다.")
                        break
                    elif kind == "error":
                        self.finish("작업을 완료하지 못했습니다. 원본은 그대로 보관됩니다.")
                        messagebox.showerror("처리 결과", event["message"], parent=self.root)
                        break
            except queue.Empty:
                pass
            if self.process:
                if self.cancel_at and time.monotonic() - self.cancel_at > 3:
                    self.finish("작업을 취소했습니다. 결과 폴더의 임시자료 정리 여부를 확인하세요.")
                elif not self.process.is_alive():
                    # Allow the multiprocessing queue feeder to flush a final message.
                    if getattr(self, "dead_at", None) is None:
                        self.dead_at = time.monotonic()
                    elif time.monotonic() - self.dead_at > 0.6:
                        self.finish("작업 프로세스가 종료되었습니다. 원본은 변경되지 않았습니다.")
                        self.dead_at = None
                else:
                    self.dead_at = None
        self.root.after(150, self.poll)

    def open_result(self):
        if not self.result_folder:
            return
        try:
            if os.name == "nt":
                os.startfile(self.result_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.result_folder])
            else:
                subprocess.Popen(["xdg-open", self.result_folder])
        except OSError:
            self.status.set("저장은 완료했습니다. 파일 탐색기에서 결과 폴더를 확인하세요.")
