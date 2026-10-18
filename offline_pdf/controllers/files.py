"""Shared PDF/image list, credentials, imports and selection."""

from __future__ import annotations

import os
from pathlib import Path
from tkinter import filedialog, messagebox

import pymupdf as pdf

from ..engine import UserError, check_local_path
from ..images import IMAGE_EXTENSIONS, IMAGE_LABEL, IMAGE_PATTERN
from ..passwords import cached_password, ensure_password


class FileController:
    """Shared PDF/image list, credentials, imports and selection."""

    def add_files(self):
        if self.busy():
            return
        if self.pending_results is not None:
            self.status.set("다음 작업을 선택하거나 “이어서 작업 취소”를 누르세요.")
            return
        types = [("PDF·이미지", "*.pdf " + IMAGE_PATTERN)]
        paths = filedialog.askopenfilenames(
            parent=self.root, title="처리할 파일을 선택하세요", filetypes=types
        )
        if paths:
            self.add_paths(paths)

    def on_files_drop(self, paths):
        if self.pending_results is not None:
            messagebox.showinfo(
                "다음 작업",
                "다음 작업을 먼저 선택하세요. 새 파일을 추가하려면 “이어서 작업 취소”를 누르세요.",
                parent=self.root,
            )
            return
        self.add_paths(paths)

    def add_paths(self, paths):
        if self.pending_results is not None:
            self.status.set("다음 작업을 선택하거나 “이어서 작업 취소”를 누르세요.")
            return
        if self.busy():
            self.status.set("작업 중에는 파일을 추가할 수 없습니다. 완료 후 다시 끌어놓으세요.")
            return
        paths = list(paths)
        home = self.home.winfo_ismapped()
        extensions = IMAGE_EXTENSIONS | {".pdf"}
        expected = "PDF·" + IMAGE_LABEL
        known = {os.path.normcase(str(Path(path).resolve())) for path in self.files}
        added = duplicates = unsupported = blocked = 0
        for path in paths:
            candidate = Path(path)
            if candidate.suffix.lower() not in extensions:
                unsupported += 1
                continue
            try:
                candidate = check_local_path(candidate)
                if not candidate.is_file():
                    blocked += 1
                    continue
            except (UserError, OSError, RuntimeError):
                blocked += 1
                continue
            key = os.path.normcase(str(candidate))
            if key in known:
                duplicates += 1
                continue
            known.add(key)
            self.files.append(str(candidate))
            added += 1
        if added:
            for path in self.files[-added:]:
                ensure_password(self, path)
            self.sync_list()
            self.file_list.selection_clear(0, "end")
            self.file_list.selection_set(len(self.files) - added)
            self.feedback.file_added(range(len(self.files) - added, len(self.files)))
            self.update_file_summary()
            if not home:
                if self.tool == "extract":
                    self.refresh_organizer()
                elif self.tool == "split":
                    self.update_split_preview()
                else:
                    self.hide_preview(restore=False)
                self.refresh_preview(reset=True)
        details = [f"{added}개 추가", f"전체 {len(self.files)}개"]
        if duplicates:
            details.append(f"중복 {duplicates}개 제외")
        if unsupported:
            details.append(f"지원하지 않는 항목 {unsupported}개 제외 ({expected} 파일만 추가 가능)")
        if blocked:
            details.append(f"접근 불가·동기화·네트워크 경로 {blocked}개 제외")
        if added and any(Path(p).suffix.lower() in IMAGE_EXTENSIONS for p in self.files[-added:]):
            details.append("이미지는 자동으로 PDF로 변경되어 작업이 수행됩니다.")
        self.status.set(" · ".join(details))

    def replace_converted_inputs(self, mapping):
        selected = self.file_list.curselection()
        self.converted_count = len(mapping)
        self.save_mode.set("지정한 폴더")
        self.output.set(self.result_output or self.output.get())
        self.files = [mapping.get(path, path) for path in self.files]
        self.regions = {mapping.get(path, path): regions for path, regions in self.regions.items()}
        self.sync_list()
        self.file_list.selection_clear(0, "end")
        for i in selected:
            self.file_list.selection_set(i)
        self.feedback.file_added(i for i, path in enumerate(self.files) if path in mapping.values())
        if self.tool == "extract":
            self.refresh_organizer()
        else:
            self.hide_preview(restore=False)
        if self.tool == "split":
            self.update_split_preview()
        self.refresh_preview(reset=True)

    def sync_list(self, animate=False):
        self.password_cache = {p: v for p, v in self.password_cache.items() if p in self.files}
        self.metadata_cache.clear()
        self.file_list.set_files(self.files, self.file_metadata, animate=animate)
        total = sum(Path(path).stat().st_size for path in self.files if Path(path).is_file())
        self.sidebar_total.set(f"{len(self.files)}개 파일 · {total / 1024 / 1024:.1f} MB")
        self.update_file_summary()
        if self.tool == "extract":
            self.refresh_organizer()
        if self.tool == "split":
            self.update_split_preview()
        self.status.set(f"{len(self.files)}개 파일 · 목록의 위에서 아래 순서로 처리합니다.")

    def file_metadata(self, path):
        try:
            check_local_path(path)
            stat = Path(path).stat()
            key = (path, stat.st_size, stat.st_mtime_ns)
            if key not in self.metadata_cache:
                if Path(path).suffix.lower() == ".pdf":
                    with pdf.open(path) as doc:
                        if doc.needs_pass:
                            password = cached_password(self, path)
                            label = (
                                f"{doc.page_count}쪽 · 열림"
                                if password and doc.authenticate(password)
                                else "잠김 · 클릭하여 암호 입력"
                            )
                        else:
                            label = f"{doc.page_count}쪽"
                else:
                    from PIL import Image

                    with Image.open(path) as image:
                        label = f"{image.width}×{image.height} · {getattr(image, 'n_frames', 1)}장"
                self.metadata_cache[key] = f"{label} · {stat.st_size / 1024 / 1024:.1f} MB"
            meta = self.metadata_cache[key]
        except Exception:
            meta = "미리보기 확인 필요"
        if not self.home.winfo_ismapped() and not self.accepted_path(path):
            meta = "이 도구에서 사용 불가 · " + meta
        return meta

    def accepted_path(self, path):
        return Path(path).suffix.lower() in IMAGE_EXTENSIONS | {".pdf"}

    def file_selected(self, event=None):
        if self.busy() or self.pending_results is not None:
            return
        self.close_ai_comparison()
        ensure_password(self, self.selected_file())
        self.metadata_cache.clear()
        if not self.file_list.motion_timer:
            self.file_list.set_files(self.files, self.file_metadata)
        if self.tool == "extract":
            self.refresh_organizer()
        if self.tool == "split":
            self.update_split_preview()
        self.update_file_summary()
        self.refresh_preview(reset=True)
        if self.file_overview.winfo_manager():
            self.overview_title.config(
                text=Path(self.selected_file()).name if self.selected_file() else ""
            )

    def update_file_summary(self):
        self.file_count.config(text=f"작업 파일  {len(self.files)}개")
        self.summary.set(
            f"파일 {len(self.files)}개 선택됨" if self.files else "파일을 추가해 주세요."
        )
        if self.tool == "extract" and self.organizer.model:
            self.summary.set(f"{len(self.organizer.model.items)}페이지를 저장합니다")
        if self.tool == "split" and self.selected_file():
            self.summary.set("왼쪽에서 선택한 PDF 한 개를 나눕니다.")
        compatible = bool(self.files) and all(self.accepted_path(path) for path in self.files)
        if self.tool in ("extract", "split"):
            compatible = bool(self.selected_file() and self.accepted_path(self.selected_file()))
        self.run_button.config(state="normal" if compatible and not self.busy() else "disabled")
        if self.files and not compatible:
            self.summary.set("지원하지 않는 파일이 있습니다. 왼쪽 목록을 확인하세요.")
        if self.tool == "extract" and not self.organizer.model:
            self.run_button.config(state="disabled")
        if self.files and self.save_mode.get() == "원본 파일과 같은 폴더":
            self.output.set(
                str(
                    Path(
                        self.selected_file() if self.tool in ("extract", "split") else self.files[0]
                    ).parent
                )
            )

    def remove_files(self):
        if self.busy() or self.pending_results is not None:
            return
        selected = self.file_list.curselection()
        if not selected:
            self.status.set("제거할 파일을 선택하세요.")
            return
        for i in reversed(selected):
            self.files.pop(i)
        self.regions = {}
        self.sync_list(animate=True)
        self.refresh_preview(reset=True)
        self.status.set(
            f"{len(selected)}개 파일을 목록에서 제거했습니다. · 남은 파일 {len(self.files)}개"
        )

    def clear_files(self):
        if self.busy() or self.pending_results is not None:
            return
        self.files = []
        self.regions = {}
        self.sync_list(animate=True)
        self.refresh_preview(reset=True)
        self.status.set("파일 목록을 모두 비웠습니다.")

    def move(self, delta):
        if self.busy() or self.pending_results is not None:
            return
        sel = self.file_list.curselection()
        if len(sel) != 1:
            return
        i = sel[0]
        j = i + delta
        if 0 <= j < len(self.files):
            self.files[i], self.files[j] = self.files[j], self.files[i]
            self.sync_list(animate=True)
            self.file_list.selection_clear(0, "end")
            self.file_list.selection_set(j)
            self.file_selected()
            self.status.set(
                f"파일을 {'위로' if delta < 0 else '아래로'} 이동했습니다. · {Path(self.files[j]).name}"
            )

    def selected_file(self):
        sel = self.file_list.curselection()
        index = sel[0] if sel and sel[0] < len(self.files) else 0
        return self.files[index] if self.files else None
