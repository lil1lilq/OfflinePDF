"""Tool-specific fields, save settings and live split summaries."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .. import ctk_widgets as ttk
from ..engine import UserError, open_pdf, split_ranges
from ..images import EXPORT_FORMATS, IMAGE_EXTENSIONS, IMAGE_PATTERN, open_image_document
from ..localization import ChoiceVar
from ..output_options import BLANK_MODE
from ..passwords import ask_password, cached_password, ensure_password
from ..tools import TOOLS
from ..ui import BLUE, CARD_TEXT, MUTED, RED, chip_color, tool_icon


def wrap_captions(form, visible, width=None):
    """Wrap captions to an equal share of the form's width (its parent sets it)."""
    if not visible:
        return
    width = width or form.winfo_width()
    if not isinstance(width, int) or width <= 1:
        return
    # Same weights as the grid: compression 3, others 1, padded to 4 columns.
    weights = [3 if key == "compression" else 1 for key, _ in visible]
    share = width / (sum(weights) + max(0, 4 - len(visible)))
    for (key, cell), weight in zip(visible, weights):
        caption = getattr(cell, "caption", None)
        if caption is None:
            continue
        wrap = max(60, int(share * weight) - 14)
        if getattr(cell, "caption_wrap", None) != wrap:
            cell.caption_wrap = wrap
            caption.configure(wraplength=wrap)


UPSCALE_ADVANCED = ("max_output_mb", "min_dpi", "min_quality")


class FormController:
    """Tool-specific fields, save settings and live split summaries."""

    def organizer_settings(self):
        if self.busy():
            return
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("페이지 정리 · 파일·저장 설정")
        dialog.geometry("560x450")
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
            row=8, column=0, sticky="e", pady=15
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
        var = ChoiceVar(value=default, choices=choices) if choices else tk.StringVar(value=default)
        self.options[key] = var
        cell = ttk.Frame(self.form, style="Panel.TFrame")
        self.form_cells.append((key, cell))
        caption = ttk.Label(cell, text=label, style="Panel.TLabel", wraplength=80, justify="left")
        caption.pack(anchor="w", fill="x", pady=(0, 3))
        # Every option shares one row, so captions wrap instead of widening the cell.
        # arrange_fields sets the wrap width from the form's width, never from the
        # cell's own width: that would feed back into the cell size and relayout.
        cell.caption = caption
        controls = ttk.Frame(cell, style="Panel.TFrame")
        # Bottom-aligned, so inputs line up even when a neighbouring caption wraps.
        controls.pack(side="bottom", fill="x")
        if key == "scale":
            # Two plain choices instead of a numeric dropdown.
            labels = {"2배 (권장)": "2", "4배 (더 선명·느림)": "4"}
            toggle = ttk.SegmentedChoice(
                controls, values=labels, command=lambda label: var.set(labels[label])
            )
            toggle.set(next(label for label, value in labels.items() if value == default))
            toggle.pack(side="left", fill="x", expand=True)
            self.option_widgets[key] = toggle
            return
        if key == "compression":
            for i, choice in enumerate(choices):
                controls.columnconfigure(i, weight=1)
                ttk.Radiobutton(
                    controls,
                    text=choice,
                    variable=var,
                    value=choice,
                    style="Compression.TRadiobutton",
                    width=40,
                ).grid(row=0, column=i, sticky="w", padx=(0, 6), pady=6)
            return
        if choices:
            widget = ttk.Combobox(controls, textvariable=var, values=choices, state="readonly")
        else:
            widget = ttk.Entry(controls, textvariable=var, show="●" if secret else "")
        # A small natural width lets the shared row shrink; the cell's weight
        # stretches the control to fill whatever room the row has.
        widget.configure(width=70)
        widget.pack(side="left", fill="x", expand=True)
        self.option_widgets[key] = widget
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
        """Lay every visible option out side by side on a single row."""
        visible = []
        n_split = (
            self.tool == "split"
            and self.options.get("split_mode")
            and self.options["split_mode"].get() == "N개 파일로 나누기"
        )
        for key, cell in self.form_cells:
            if key in ("target_mb", "min_dpi", "min_quality") and self.tool == "compress":
                if self.options["compression"].get() != "목표 용량":
                    continue
            if self.tool == "split" and (
                (key == "pages" and n_split)
                or (key in ("split_count", "split_starts") and not n_split)
            ):
                continue
            if self.tool == "upscale" and key in UPSCALE_ADVANCED and not self.show_advanced:
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
            visible.append((key, cell))
        wrap_captions(self.form, visible, width)
        # One row does not depend on the width, so resizes need no new layout.
        signature = tuple(id(cell) for _, cell in visible)
        if signature == getattr(self, "form_signature", None):
            return
        self.form_signature = signature
        previous = getattr(self, "form_columns", 0) or 0
        for col in range(max(previous, len(visible))):
            self.form.columnconfigure(col, weight=0, uniform="", minsize=0)
        # With only a few options, an empty trailing column keeps each one at
        # about a quarter of the row instead of stretching across all of it.
        spare = max(0, 4 - len(visible))
        self.form_columns = len(visible) + 1
        # Tk counts weight 0 as 1 inside a uniform group, so join it only when needed.
        self.form.columnconfigure(
            len(visible), weight=spare, uniform="fields" if spare else "", minsize=0
        )
        for _, cell in self.form_cells:
            cell.grid_forget()
        for i, (key, cell) in enumerate(visible):
            # The five compression levels need roughly three option widths.
            wide = key == "compression"
            self.form.columnconfigure(
                i, weight=3 if wide else 1, uniform="" if wide else "fields", minsize=0
            )
            cell.grid(
                row=0,
                column=i,
                columnspan=1,
                sticky="nsew",
                padx=(0, 10 if i < len(visible) - 1 else 0),
                pady=4,
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
        self.option_widgets = {}
        self.form_cells = []
        self.show_advanced = False
        title, desc = TOOLS[self.tool]
        self.title.config(text=title)
        self.description.config(text=desc)
        self.description.config(foreground=MUTED)
        self.task_icon.configure(fg_color=chip_color(self.tool))
        self.task_icon_label.configure(image=tool_icon(self.tool))
        self.run_button.config(text=CARD_TEXT[self.tool][0] + "  →")
        self.preview_button.config(state="normal")
        if self.tool == "redact":
            self.preview_region_row.pack(side="right", padx=(12, 0), before=self.preview_nav)
        else:
            self.preview_region_row.pack_forget()
        self.output_name.set("합친문서.pdf" if self.tool == "merge" else "이미지문서.pdf")
        if self.tool in ("merge", "images_pdf"):
            self.name_frame.pack(side="right", fill="y", padx=(10, 0), pady=4)
        else:
            self.name_frame.pack_forget()
        if self.tool in ("merge", "images_pdf"):
            self.side_controls.pack(side="right", fill="y", before=self.form)
        else:
            self.side_controls.pack_forget()
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
            self.split_summary.pack(fill="x", pady=(4, 0))
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
            self.field(
                "압축 수준",
                "compression",
                "권장",
                ["무손실", "선명하게", "권장", "작게", "목표 용량"],
            )
            self.field("목표 용량 MB / 파일", "target_mb", "5")
            self.field("최소 이미지 DPI", "min_dpi", "96")
            self.field("최소 JPEG 품질 (30~95)", "min_quality", "50")
            self.options["compression"].trace_add("write", self.compression_note)
        if self.tool == "upscale":
            self.field("확대 배율", "scale", "2")
            # Size limits are rarely needed; they stay behind "advanced options".
            self.field("최대 용량 MB (공란=무제한)", "max_output_mb", "")
            self.field("최소 이미지 DPI", "min_dpi", "96")
            self.field("최소 JPEG 품질 (30~95)", "min_quality", "50")
            self.advanced_toggle_cell()
            self.options["max_output_mb"].trace_add("write", self.update_size_floor_state)
            self.update_size_floor_state()
            self.ai_preview_button.pack(side="left", padx=8)
        if self.tool == "nup":
            self.field("한 장당 쪽수 (1~64)", "nup_count", "4")
            self.field("A4 방향", "nup_orientation", "세로", ["세로", "가로"])
            self.field("가로 칸 수 (0=자동)", "nup_columns", "0")
            self.field(
                "채우기", "nup_fit", "전체 내용 유지", ["전체 내용 유지", "꽉 채우기 (잘림)"]
            )
            self.field("바깥 여백 (mm)", "nup_margin", "0")
            self.field("쪽 사이 간격 (mm)", "nup_gap", "0")
            self.field("배치 순서", "nup_order", "가로 우선", ["가로 우선", "세로 우선"])
            for key in (
                "pages",
                "nup_count",
                "nup_orientation",
                "nup_columns",
                "nup_fit",
                "nup_margin",
                "nup_gap",
                "nup_order",
            ):
                self.options[key].trace_add("write", lambda *_: self.schedule_preview())
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
            # Korean and English language data ship with the program.
            self.field(
                "문서 언어", "language", "한국어 + 영어", ["한국어 + 영어", "한국어", "영어"]
            )
        self.update_blank_option()
        self.security.config(
            text="페이지를 비워 두면 전체 페이지를 처리합니다." if "pages" in self.options else ""
        )
        if "pages" in self.options:
            self.security.pack(anchor="w", pady=(4, 0))
        else:
            self.security.pack_forget()
        self.update_file_summary()
        self.arrange_fields()
        if self.tool == "split":
            self.update_split_preview()
        if self.tool == "compress":
            self.compression_note()
        if self.tool == "upscale":
            self.update_advanced_note()
        if self.tool == "nup":
            self.security.config(
                text="파일별 저장 · 원본의 흰 여백은 유지됩니다. 꽉 채우기는 가장자리를 가리며 영구 삭제하지 않습니다."
            )
            self.security.pack(anchor="w", pady=(4, 0))
        self.update_region_status()
        self.hide_preview(restore=False)
        if self.tool == "extract":
            self.refresh_organizer()
            self.run_button.config(text="정리한 PDF 저장  →")
        elif self.tool == "redact":
            # Distinct from "clear this page's selection" on the preview toolbar.
            self.run_button.config(text="선택 영역 영구 삭제  →")
            self.show_preview()

    def advanced_toggle_cell(self):
        cell = ttk.Frame(self.form, style="Panel.TFrame")
        self.form_cells.append(("advanced", cell))
        self.advanced_button = ttk.Button(
            cell, text="상세 옵션 ▾", command=self.toggle_advanced, width=13
        )
        self.advanced_button.pack(side="bottom", anchor="w")

    def toggle_advanced(self):
        self.show_advanced = not self.show_advanced
        self.advanced_button.config(
            text="상세 옵션 접기 ▴" if self.show_advanced else "상세 옵션 ▾"
        )
        self.arrange_fields()
        self.update_advanced_note()

    def update_advanced_note(self):
        if self.show_advanced:
            self.security.config(
                text="최소 DPI·품질은 최대 용량을 입력했을 때만 사용합니다. 용량을 맞추느라 화질이 낮아질 수 있습니다."
            )
            self.security.pack(anchor="w", pady=(4, 0))
        else:
            self.security.pack_forget()

    def update_size_floor_state(self, *_):
        limited = bool(self.options["max_output_mb"].get().strip())
        for key in ("min_dpi", "min_quality"):
            self.option_widgets[key].configure(state="normal" if limited else "disabled")

    def settings_panel_needed(self):
        """Tools without options (cleaning, redaction) skip the empty panel."""
        return bool(self.form_cells) or self.tool in ("merge", "images_pdf")

    def blank_option_applies(self):
        """Text and image exports have no PDF pages to drop."""
        return self.tool not in ("text", "pdf_images")

    def update_blank_option(self):
        applies = self.blank_option_applies()
        self.blank_check.configure(state="normal" if applies else "disabled")
        if applies and self.remove_blank.get():
            self.blank_badge.pack(side="right", padx=(0, 12), after=self.run_button)
        else:
            self.blank_badge.pack_forget()

    def blank_mode(self):
        """The worker's remove_blank value for the sidebar checkbox."""
        return (
            BLANK_MODE if self.blank_option_applies() and self.remove_blank.get() else "사용 안 함"
        )

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
            "목표 용량": "파일당 상한 · 1 MB=1,000,000바이트 · 최소 DPI·품질로도 맞추지 못하면 결과를 저장하지 않습니다.",
        }
        self.arrange_fields()
        self.security.config(text=notes.get(self.options["compression"].get(), ""))
        self.security.pack(anchor="w", pady=(4, 0))

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
