"""Tool-specific fields, save settings and live split summaries."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ..engine import UserError, open_pdf, split_ranges
from ..images import EXPORT_FORMATS, IMAGE_EXTENSIONS, IMAGE_PATTERN, open_image_document
from ..passwords import ask_password, cached_password, ensure_password
from ..tools import TOOLS
from ..ui import BLUE, CARD_TEXT, MUTED, RED, icon


class FormController:
    """Tool-specific fields, save settings and live split summaries."""

    def organizer_settings(self):
        if self.busy():
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("페이지 정리 · 파일·저장 설정")
        dialog.geometry("560x390")
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Button(
            body,
            text="선택 문서 암호 입력",
            command=lambda: ensure_password(self, self.selected_file()),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="결과 저장 폴더").grid(row=2, column=0, sticky="w", pady=(10, 0))
        entry = ttk.Entry(body, textvariable=self.output)
        entry.grid(row=3, column=0, sticky="ew", pady=8)
        entry.bind("<KeyRelease>", lambda e: self.save_mode.set("지정한 폴더"))
        ttk.Button(body, text="폴더 선택", command=self.choose_output).grid(row=3, column=1, padx=8)
        ttk.Checkbutton(body, text="완료 후 저장 폴더 열기", variable=self.auto_open).grid(
            row=4, column=0, sticky="w", pady=10
        )
        ttk.Button(body, text="페이지 번호로 지정", command=self.organizer.apply_text).grid(
            row=5, column=0, sticky="w", pady=6
        )

        def done():
            dialog.destroy()
            self.refresh_organizer()

        ttk.Button(body, text="확인", command=done, style="Back.TButton").grid(
            row=6, column=0, sticky="e", pady=15
        )
        dialog.protocol("WM_DELETE_WINDOW", done)
        dialog.grab_set()
        return dialog

    def change_save_mode(self, event=None):
        if self.busy():
            return
        if self.save_mode.get() == "원본 파일과 같은 폴더" and self.files:
            self.output.set(
                str(
                    Path(
                        self.selected_file() if self.tool in ("extract", "split") else self.files[0]
                    ).parent
                )
            )
        elif self.save_mode.get() == "지정한 폴더":
            self.choose_output()

    def field(self, label, key, default="", choices=None, secret=False, browse=None):
        var = tk.StringVar(value=default)
        self.options[key] = var
        cell = ttk.Frame(self.form, style="Panel.TFrame")
        self.form_cells.append((key, cell))
        ttk.Label(cell, text=label, style="Panel.TLabel").pack(anchor="w", pady=(0, 3))
        controls = ttk.Frame(cell, style="Panel.TFrame")
        controls.pack(fill="x")
        if key == "compression":
            for i, choice in enumerate(choices):
                controls.columnconfigure(i, weight=1)
                ttk.Radiobutton(
                    controls,
                    text=choice,
                    variable=var,
                    value=choice,
                    style="Compression.TRadiobutton",
                ).grid(row=0, column=i, sticky="ew", padx=(0, 6), ipady=9)
            return
        if choices:
            widget = ttk.Combobox(
                controls, textvariable=var, values=choices, state="readonly", width=12
            )
        else:
            widget = ttk.Entry(controls, textvariable=var, width=12, show="●" if secret else "")
        widget.pack(side="left", fill="x", expand=True)
        if key == "input_password":
            widget.bind("<FocusOut>", lambda e: self.refresh_preview())
        if browse:

            def pick():
                path = (
                    filedialog.askdirectory(parent=self.root)
                    if browse == "dir"
                    else filedialog.askopenfilename(
                        parent=self.root, filetypes=[("이미지", IMAGE_PATTERN)]
                    )
                )
                if path:
                    var.set(path)

            ttk.Button(controls, text="선택", command=pick).pack(side="right", padx=(4, 0))

    def arrange_fields(self, width=None):
        width = max(200, width or self.form.winfo_width())
        columns = max(1, min(4, int(width / 180)))
        for col in range(4):
            self.form.columnconfigure(
                col,
                weight=1 if col < columns else 0,
                uniform="fields" if col < columns else "",
                minsize=0,
            )
        visible = []
        n_split = (
            self.tool == "split"
            and self.options.get("split_mode")
            and self.options["split_mode"].get() == "N개 파일로 나누기"
        )
        for key, cell in self.form_cells:
            cell.grid_forget()
            if self.tool == "split" and (
                (key == "pages" and n_split)
                or (key in ("split_count", "split_starts") and not n_split)
            ):
                continue
            if self.tool == "protect" and key == "output_password":
                if self.options["password_mode"].get() == "암호 제거":
                    continue
            if self.tool == "watermark":
                image = self.options["insert_mode"].get() == "이미지"
                if (image and key in ("text", "font_size")) or (
                    not image and key in ("stamp_path", "stamp_width")
                ):
                    continue
            visible.append(cell)
        for i, cell in enumerate(visible):
            cell.grid(
                row=i // columns,
                column=i % columns,
                columnspan=columns if self.tool == "compress" else 1,
                sticky="ew",
                padx=(0, 10),
                pady=5,
            )

    def update_split_preview(self, *_):
        if self.tool != "split" or self.split_updating:
            return
        self.arrange_fields()
        if self.options["split_mode"].get() != "N개 파일로 나누기":
            self.security.config(text="페이지를 비워 두면 전체 페이지를 처리합니다.")
            self.split_summary.config(
                text="선택한 페이지를 각각의 PDF로 저장합니다. 페이지 공란은 전체입니다.",
                foreground=MUTED,
            )
            return
        self.security.config(
            text="입력한 쪽부터 다음 파일이 시작됩니다. 예: 시작 쪽 5 → 1–4쪽 / 5쪽부터"
        )
        total = self.document_page_count()
        if not total:
            self.split_summary.config(
                text="PDF 하나를 선택하면 나누기 범위가 표시됩니다.", foreground=MUTED
            )
            return
        try:
            ranges = split_ranges(
                total, self.options["split_count"].get(), self.options["split_starts"].get()
            )
            text = "생성할 파일  " + "  /  ".join(
                f"{i + 1}: {a + 1}–{b + 1}쪽" for i, (a, b) in enumerate(ranges)
            )
            self.split_summary.config(text=text, foreground=BLUE)
        except UserError as exc:
            self.split_summary.config(text=str(exc), foreground=RED)
        self.schedule_preview()

    def document_page_count(self):
        path = self.selected_file()
        if not path:
            return 0
        try:
            doc = (
                open_image_document(path)
                if Path(path).suffix.lower() in IMAGE_EXTENSIONS
                else open_pdf(path, cached_password(self, path))[0]
            )
            try:
                return doc.page_count
            finally:
                doc.close()
        except (UserError, OSError):
            return 0

    def configure_form(self):
        for w in self.form.winfo_children():
            w.destroy()
        self.options = {}
        self.form_cells = []
        title, desc = TOOLS[self.tool]
        self.title.config(text=title)
        self.description.config(text=desc)
        self.description.config(foreground=MUTED)
        self.task_icon.delete("all")
        icon(self.task_icon, self.tool, 12, 12)
        self.run_button.config(text=CARD_TEXT[self.tool][0] + "  →")
        self.preview_button.config(state="normal")
        if self.tool == "redact":
            self.clear_preview_regions.pack(side="right")
        else:
            self.clear_preview_regions.pack_forget()
        self.output_name.set("합친문서.pdf" if self.tool == "merge" else "이미지문서.pdf")
        if self.tool in ("merge", "images_pdf"):
            self.name_frame.pack(fill="x", pady=(7, 0))
        else:
            self.name_frame.pack_forget()
        if self.tool == "redact":
            self.region_controls.pack(fill="x")
        else:
            self.region_controls.pack_forget()
        if self.tool not in (
            "merge",
            "images_pdf",
            "protect",
            "compress",
            "clean",
            "redact",
            "upscale",
        ):
            self.field("페이지", "pages", "")
        if self.tool == "split":
            self.field(
                "나누는 방식",
                "split_mode",
                "페이지별로 나누기",
                ["페이지별로 나누기", "N개 파일로 나누기"],
            )
            self.field("만들 파일 수 N", "split_count", "2")
            self.field("다음 파일의 시작 쪽 (예: 5,8)", "split_starts", "")
            for key in ("split_mode", "split_count", "split_starts"):
                self.options[key].trace_add("write", self.update_split_preview)
            self.split_summary.pack(fill="x", pady=(7, 0))
            self.update_split_preview()
        else:
            self.split_summary.pack_forget()
        if self.tool == "protect":
            self.field("작업", "password_mode", "암호 설정", ["암호 설정", "암호 제거"])
            self.field("새 암호", "output_password", secret=True)
            self.options["password_mode"].trace_add("write", self.update_password_mode)
        elif self.tool in ("merge", "images_pdf"):
            self.options["output_password"] = tk.StringVar()
        self.output_password_button.config(text="암호 추가")
        self.ai_preview_button.pack_forget()
        if self.tool == "compress":
            self.field("압축 수준", "compression", "권장", ["무손실", "선명하게", "권장", "작게"])
            self.options["compression"].trace_add("write", self.compression_note)
        if self.tool == "upscale":
            self.field("확대 배율 (배)", "scale", "2", ["2", "4"])
            self.ai_preview_button.pack(side="left", padx=8)
        if self.tool == "pdf_images":
            self.field("해상도 DPI", "dpi", "150", ["72", "100", "150", "200", "300"])
            self.field("저장 형식", "format", "JPG", list(EXPORT_FORMATS))
        if self.tool == "images_pdf":
            self.field("A4 방향", "orientation", "세로", ["세로", "가로"])
        if self.tool == "watermark":
            self.field("삽입 종류", "insert_mode", "문구", ["문구", "이미지"])
            self.field("문구", "text", "내부 업무용")
            self.field("글자 크기", "font_size", "24")
            self.field("이미지 파일", "stamp_path", browse="file")
            self.field("이미지 너비 pt", "stamp_width", "100")
            self.field(
                "삽입 위치",
                "position",
                "가운데",
                [
                    "왼쪽 위",
                    "가운데 위",
                    "오른쪽 위",
                    "가운데",
                    "왼쪽 아래",
                    "가운데 아래",
                    "오른쪽 아래",
                ],
            )
            self.field("불투명도", "opacity", "0.25")
            self.options["insert_mode"].trace_add("write", self.update_insert_mode)
        if self.tool == "number":
            self.field("시작 번호", "start", "1")
        if self.tool == "crop":
            self.field("여백 mm", "margin", "10")
        if self.tool == "ocr":
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
            self.field("언어자료 폴더", "tessdata", str(root / "tessdata"), browse="dir")
            self.field(
                "문서 언어", "language", "한국어 + 영어", ["한국어 + 영어", "한국어", "영어"]
            )
        self.security.config(
            text="페이지를 비워 두면 전체 페이지를 처리합니다." if "pages" in self.options else ""
        )
        if "pages" in self.options:
            self.security.pack(anchor="w", pady=(12, 0))
        else:
            self.security.pack_forget()
        self.update_file_summary()
        self.arrange_fields()
        if self.tool == "split":
            self.update_split_preview()
        if self.tool == "compress":
            self.compression_note()
        if self.tool == "upscale":
            self.security.config(
                text="CPU 처리 · 2배 권장 · 텍스트와 도형은 유지하며 스캔 이미지만 보정합니다."
            )
            self.security.pack(anchor="w", pady=(8, 0))
        self.update_region_status()
        self.hide_preview(restore=False)
        if self.tool == "extract":
            self.refresh_organizer()
            self.run_button.config(text="정리한 PDF 저장  →")
        elif self.tool == "redact":
            self.show_preview()

    def effective_tool(self):
        """Translate the selected mode into the existing worker operation."""
        if self.tool == "protect" and self.options["password_mode"].get() == "암호 제거":
            return "unlock"
        if self.tool == "watermark" and self.options["insert_mode"].get() == "이미지":
            return "stamp"
        return self.tool

    def update_password_mode(self, *_):
        removing = self.options["password_mode"].get() == "암호 제거"
        if removing:
            self.options["output_password"].set("")
        self.run_button.config(text=("암호 제거" if removing else "암호 설정") + "  →")
        self.arrange_fields()

    def update_insert_mode(self, *_):
        image = self.options["insert_mode"].get() == "이미지"
        self.options["position"].set("오른쪽 아래" if image else "가운데")
        self.options["opacity"].set("1" if image else "0.25")
        self.arrange_fields()

    def compression_note(self, *_):
        notes = {
            "무손실": "화질을 유지하며 문서 데이터를 정리합니다. 용량이 줄지 않을 수도 있습니다.",
            "선명하게": "이미지 300 DPI·품질 90 · 선명도를 우선합니다.",
            "권장": "이미지 150 DPI·품질 75 · 가독성과 용량의 균형을 맞춥니다.",
            "작게": "이미지 96 DPI·품질 50 · 작은 글자나 사진이 흐려질 수 있습니다.",
        }
        self.security.config(text=notes.get(self.options["compression"].get(), ""))
        self.security.pack(anchor="w", pady=(8, 0))

    def set_output_password(self):
        if self.busy():
            return
        password = ask_password(self, output=True)
        if password is not None:
            self.options["output_password"].set(password)
            self.output_password_button.config(text="암호 설정됨")

    def choose_output(self):
        if self.busy():
            return
        path = filedialog.askdirectory(parent=self.root, title="승인된 로컬 저장 폴더를 선택하세요")
        if path:
            self.output.set(path)
            self.save_mode.set("지정한 폴더")
