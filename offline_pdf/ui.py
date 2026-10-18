"""Local Tk widgets for the card home and task workspace. No assets or downloads."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#f5f7fb"
PANEL = "#ffffff"
INK = "#202b3d"
MUTED = "#637086"
RED = "#c62828"
LINE = "#e2e7ef"
BLUE = "#285de5"
SOFT = "#edf2ff"
FONT = "맑은 고딕"

POPULAR = ("merge", "split", "extract", "compress", "ocr", "pdf_images")
CARD_TEXT = {
    "merge": ("PDF 합치기", "여러 PDF를 하나로 합칩니다"),
    "split": ("PDF 나누기", "페이지별 또는 N개 파일로 나눕니다"),
    "extract": ("페이지 정리", "필요한 페이지를 고르고 순서를 바꿉니다"),
    "compress": ("용량 줄이기", "PDF 파일 크기를 줄입니다"),
    "upscale": ("AI 업스케일", "흐린 스캔 이미지를 확대·보정합니다"),
    "pdf_images": ("PDF → 이미지", "페이지를 이미지 파일로 저장합니다"),
    "redact": ("영역 영구 삭제", "선택한 영역의 내용을 영구 삭제합니다"),
    "images_pdf": ("이미지 → PDF", "여러 이미지를 하나의 PDF로 만듭니다"),
    "delete": ("페이지 삭제", "지정한 페이지를 문서에서 삭제합니다"),
    "rotate": ("페이지 회전", "페이지 방향을 바꿉니다"),
    "protect": ("암호 설정", "PDF를 열 때 사용할 암호를 설정합니다"),
    "unlock": ("암호 해제", "소유자 암호로 PDF의 암호를 해제합니다"),
    "watermark": ("워터마크", "페이지에 지정한 문구를 넣습니다"),
    "number": ("쪽 번호", "페이지에 쪽 번호를 넣습니다"),
    "stamp": ("서명·직인 이미지", "페이지에 서명이나 직인 이미지를 넣습니다"),
    "crop": ("여백 자르기", "페이지 가장자리의 여백을 조정합니다"),
    "text": ("텍스트 추출", "PDF의 글자를 텍스트 파일로 저장합니다"),
    "clean": ("문서 부가정보 정리", "문서에 포함된 부가정보를 정리합니다"),
    "ocr": ("검색 가능한 PDF", "스캔 문서의 글자를 인식합니다"),
}


def icon(canvas, key, x, y, color=BLUE):
    """Draw small original line icons with Tk primitives (24 by 24 units)."""

    def line(*coords, **kwargs):
        points = [v + (x if i % 2 == 0 else y) for i, v in enumerate(coords)]
        canvas.create_line(
            *points, fill=color, width=1.8, capstyle="round", joinstyle="round", **kwargs
        )

    def box(a, b, c, d):
        canvas.create_rectangle(x + a, y + b, x + c, y + d, outline=color, width=1.7)

    def oval(a, b, c, d):
        canvas.create_oval(x + a, y + b, x + c, y + d, outline=color, width=1.7)

    if key == "upload":
        line(3, 15, 3, 22, 21, 22, 21, 15)
        line(12, 17, 12, 2)
        line(6, 8, 12, 2, 18, 8)
    elif key in ("merge", "images_pdf"):
        box(2, 2, 11, 15)
        box(13, 8, 22, 22)
        line(6, 19, 11, 19, 11, 22)
        line(8, 16, 11, 19, 8, 22)
    elif key == "split":
        oval(2, 2, 8, 8)
        oval(2, 16, 8, 22)
        line(7, 7, 22, 21)
        line(7, 17, 22, 3)
    elif key == "extract":
        box(1, 3, 23, 21)
        line(8, 3, 8, 21)
        line(12, 8, 19, 8)
        line(12, 13, 19, 13)
    elif key == "compress":
        line(2, 2, 9, 9, 3, 9)
        line(9, 9, 9, 3)
        line(22, 22, 15, 15, 21, 15)
        line(15, 15, 15, 21)
    elif key in ("pdf_images", "stamp"):
        box(2, 3, 22, 21)
        oval(14, 6, 18, 10)
        line(3, 19, 9, 12, 15, 18, 18, 15, 22, 20)
    elif key == "redact":
        line(2, 15, 13, 3, 22, 11, 11, 22, 2, 15)
        line(7, 10, 16, 18)
        line(11, 22, 23, 22)
    elif key in ("protect", "unlock"):
        box(4, 10, 21, 23)
        line(8, 10, 8, 4, 12, 1, 17, 4, 17, 10 if key == "protect" else 6)
        oval(11, 14, 14, 17)
        line(12.5, 17, 12.5, 20)
    elif key == "rotate":
        canvas.create_arc(
            x + 3,
            y + 3,
            x + 21,
            y + 21,
            start=45,
            extent=280,
            style="arc",
            outline=color,
            width=1.8,
        )
        line(21, 2, 21, 9, 14, 9)
    elif key == "crop":
        line(1, 6, 18, 6, 18, 23)
        line(6, 1, 6, 18, 23, 18)
    elif key in ("watermark", "text", "number"):
        if key == "number":
            line(8, 2, 6, 22)
            line(17, 2, 15, 22)
            line(2, 9, 22, 9)
            line(1, 16, 21, 16)
        else:
            line(3, 6, 3, 3, 21, 3, 21, 6)
            line(12, 3, 12, 21)
            line(7, 21, 17, 21)
    elif key == "delete":
        box(4, 2, 20, 22)
        line(8, 12, 16, 12)
    elif key == "clean":
        box(3, 2, 21, 22)
        line(7, 12, 11, 16, 18, 8)
    else:
        line(8, 2, 2, 2, 2, 8)
        line(16, 2, 22, 2, 22, 8)
        line(2, 16, 2, 22, 8, 22)
        line(16, 22, 22, 22, 22, 16)
        line(6, 9, 18, 9)
        line(6, 14, 18, 14)


class ScrollPane(ttk.Frame):
    """A bounded native scroller; wheel events apply only while hovered."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._scroll_state)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._content_size)
        self.canvas.bind("<Configure>", self._viewport_size)
        self.wheel_ids = []
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.wheel_ids.append(
                (sequence, self.winfo_toplevel().bind(sequence, self._wheel, add="+"))
            )
        self.bind("<Destroy>", self._destroy, add="+")

    def _destroy(self, event):
        if event.widget is self:
            for sequence, binding in self.wheel_ids:
                self.winfo_toplevel().unbind(sequence, binding)

    def _content_size(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _scroll_state(self, first, last):
        self.bar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.bar.pack_forget()
        elif not self.bar.winfo_manager():
            self.bar.pack(side="right", fill="y", before=self.canvas)

    def _viewport_size(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def _wheel(self, event):
        if not self.winfo_ismapped():
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not str(widget).startswith(str(self)):
            return
        # Native lists and entries keep their own wheel behavior.
        if isinstance(widget, (tk.Listbox, ttk.Combobox, tk.Text)) or getattr(
            widget, "own_wheel", False
        ):
            return
        if self.inner.winfo_height() <= self.canvas.winfo_height():
            return
        step = (
            (-1 if event.num == 4 else 1)
            if event.num in (4, 5)
            else -int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        )
        self.canvas.yview_scroll(step * 3, "units")


class Tooltip:
    """Show explanations below the pointer, within the owning app window."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.timer = None
        self.window = None

    def schedule(self):
        self.hide()
        self.timer = self.widget.after(450, self.show)

    def show(self):
        self.timer = None
        if not self.widget.winfo_ismapped():
            return
        owner = self.widget.winfo_toplevel()
        left, top = owner.winfo_rootx(), owner.winfo_rooty()
        right = left + owner.winfo_width()
        bottom = top + owner.winfo_height()
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        tk.Label(
            self.window,
            text=self.text,
            wraplength=min(330, max(80, owner.winfo_width() - 40)),
            justify="left",
            bg=INK,
            fg=PANEL,
            padx=12,
            pady=9,
            font=(FONT, 10),
        ).pack()
        self.window.update_idletasks()
        pointer_x, pointer_y = self.widget.winfo_pointerxy()
        if not (
            self.widget.winfo_rootx()
            <= pointer_x
            < self.widget.winfo_rootx() + self.widget.winfo_width()
            and self.widget.winfo_rooty()
            <= pointer_y
            < self.widget.winfo_rooty() + self.widget.winfo_height()
        ):
            # Keyboard focus also exposes the explanation without moving the pointer.
            pointer_x = self.widget.winfo_rootx() + 12
            pointer_y = self.widget.winfo_rooty() + self.widget.winfo_height()
        width, height = self.window.winfo_reqwidth(), self.window.winfo_reqheight()
        x, y = self.position(pointer_x, pointer_y, width, height, (left, top, right, bottom))
        # A literal '+' before a negative coordinate keeps it an absolute desktop
        # coordinate. A bare '-' would make Tk measure from the opposite edge.
        self.window.geometry(f"+{x}+{y}")

    @staticmethod
    def position(pointer_x, pointer_y, width, height, bounds):
        left, top, right, bottom = bounds
        x = max(left + 8, min(pointer_x + 12, right - width - 8))
        y = pointer_y + 18
        if y + height > bottom - 8:
            y = pointer_y - height - 12
        y = max(top + 8, min(y, bottom - height - 8))
        return x, y

    def hide(self):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        if self.window:
            self.window.destroy()
            self.window = None


class ToolCard(tk.Canvas):
    def __init__(self, master, key, command):
        super().__init__(master, height=168, width=220, bg=BG, highlightthickness=0, takefocus=True)
        self.key = key
        self.command = command
        self.active = False
        self.enabled = True
        self.hover_amount = 0
        self.compact = False
        self.tooltip = Tooltip(self, CARD_TEXT[key][1])
        from .effects import Tween

        self.tween = Tween(self, self.animate)
        self.bind("<Destroy>", lambda e: self.tween.close() if e.widget is self else None, add="+")
        self.bind("<Configure>", lambda e: self.paint())
        self.bind("<Enter>", lambda e: self.highlight(True))
        self.bind("<Leave>", lambda e: self.highlight(False))
        self.bind("<FocusIn>", lambda e: self.highlight(True))
        self.bind("<FocusOut>", lambda e: self.highlight(False))
        self.bind("<ButtonRelease-1>", lambda e: self.activate())
        self.bind("<Return>", lambda e: self.activate())
        self.bind("<space>", lambda e: self.activate())
        self.bind("<Unmap>", lambda e: self.tooltip.hide(), add="+")
        self.bind("<Destroy>", lambda e: self.tooltip.hide() if e.widget is self else None, add="+")

    def activate(self):
        self.tooltip.hide()
        if self.enabled:
            self.command(self.key)

    def set_compact(self, compact, height):
        self.compact = compact
        self.configure(height=height, width=170 if compact else 220)
        self.paint()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(takefocus=enabled)
        self.paint()

    def highlight(self, active):
        self.active = active
        self.tween.to(1 if active and self.enabled else 0)
        if active and self.enabled:
            self.tooltip.schedule()
        else:
            self.tooltip.hide()

    def animate(self, value):
        self.hover_amount = value
        self.paint()

    def paint(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        r = 13
        ph = h - 5
        points = [
            r,
            1,
            w - r,
            1,
            w - 1,
            1,
            w - 1,
            r,
            w - 1,
            ph - r,
            w - 1,
            ph - 1,
            w - r,
            ph - 1,
            r,
            ph - 1,
            1,
            ph - 1,
            1,
            ph - r,
            1,
            r,
            1,
            1,
        ]
        from .effects import mix

        lift = round(3 * self.hover_amount) if self.enabled else 0
        points = [v + 4 - lift if i % 2 else v for i, v in enumerate(points)]
        self.create_polygon(
            points,
            smooth=True,
            fill=PANEL if self.enabled else BG,
            outline=mix(LINE, BLUE, self.hover_amount) if self.enabled else LINE,
            width=1.5,
        )
        if self.compact:
            y = h / 2
            self.create_rectangle(10, y - 16, 42, y + 16, fill=SOFT, outline=SOFT)
            icon(self, self.key, 14, y - 12, BLUE if self.enabled else MUTED)
            title, description = CARD_TEXT[self.key]
            self.create_text(
                52,
                y,
                anchor="w",
                text=title,
                font=(FONT, 10, "bold"),
                fill=INK if self.enabled else MUTED,
                width=max(75, w - 62),
            )
            return
        self.create_rectangle(20, 20, 60, 60, fill=SOFT, outline=SOFT)
        icon(self, self.key, 28, 28, BLUE if self.enabled else MUTED)
        self.create_line(w - 33, 31, w - 23, 21, w - 23, 29, fill=MUTED, width=1.5)
        self.create_line(w - 23, 21, w - 31, 21, fill=MUTED, width=1.5)
        title, description = CARD_TEXT[self.key]
        self.create_text(
            20,
            78,
            anchor="nw",
            text=title,
            font=(FONT, 13, "bold"),
            fill=INK if self.enabled else MUTED,
            width=max(100, w - 40),
        )
        self.create_text(
            20,
            112,
            anchor="nw",
            text=description if self.enabled else "현재 결과의 파일 형식은 지원하지 않습니다",
            font=(FONT, 9),
            fill=MUTED,
            width=max(100, w - 40),
        )
        if lift:
            for item in self.find_all()[1:]:
                self.move(item, 0, -lift)


def setup_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=INK, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Panel.TLabel", background=PANEL)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT, 9))
    style.configure("Title.TLabel", font=(FONT, 20, "bold"))
    style.configure("Task.TLabel", font=(FONT, 16, "bold"))
    style.configure("Section.TLabel", font=(FONT, 10, "bold"), background=PANEL)
    style.configure(
        "TButton",
        padding=(12, 8),
        background=PANEL,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
        borderwidth=1,
        relief="solid",
    )
    style.map(
        "TButton",
        background=[("active", SOFT)],
        bordercolor=[("active", "#b8c9ed"), ("disabled", LINE)],
        foreground=[("disabled", MUTED)],
    )
    style.configure(
        "Quiet.TButton",
        background=PANEL,
        borderwidth=1,
        relief="solid",
        bordercolor=LINE,
        foreground=INK,
    )
    style.configure(
        "Back.TButton",
        background=SOFT,
        foreground=BLUE,
        font=(FONT, 12, "bold"),
        padding=(20, 12),
        borderwidth=2,
        bordercolor="#b7caf7",
        lightcolor="#b7caf7",
        darkcolor="#b7caf7",
    )
    style.map(
        "Back.TButton",
        background=[("disabled", BG), ("active", SOFT)],
        bordercolor=[("disabled", LINE), ("active", BLUE)],
        foreground=[("disabled", MUTED), ("active", BLUE)],
    )
    style.configure(
        "Run.TButton",
        font=(FONT, 11, "bold"),
        padding=(22, 12),
        background=BLUE,
        foreground=PANEL,
        bordercolor=BLUE,
    )
    style.map(
        "Run.TButton",
        background=[("disabled", "#ccd5e8"), ("active", "#1e4fc9")],
        foreground=[("disabled", MUTED), ("!disabled", PANEL)],
    )
    style.configure(
        "TEntry",
        fieldbackground=PANEL,
        padding=7,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
    )
    style.configure("TCombobox", fieldbackground=PANEL, padding=7, bordercolor=LINE, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)])
    style.configure("TCheckbutton", background=PANEL)
    # Explicit tick images avoid the Clam theme's cross-shaped indicator.
    from PIL import Image, ImageDraw, ImageTk

    images = []
    size = max(16, round(12 * float(root.tk.call("tk", "scaling"))))
    for selected in (False, True):
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (1, 1, size - 2, size - 2),
            radius=2,
            fill=BLUE if selected else PANEL,
            outline=BLUE if selected else MUTED,
        )
        if selected:
            draw.line(
                [
                    (size * 0.23, size * 0.51),
                    (size * 0.43, size * 0.70),
                    (size * 0.78, size * 0.29),
                ],
                fill=PANEL,
                width=max(2, size // 8),
            )
        images.append(ImageTk.PhotoImage(image, master=root))
        image.close()
    root.checkbox_images = images
    style.element_create(
        "OfflineCheck.indicator", "image", images[0], ("selected", images[1]), sticky=""
    )
    style.layout(
        "TCheckbutton",
        [
            (
                "Checkbutton.padding",
                {
                    "sticky": "nswe",
                    "children": [
                        ("OfflineCheck.indicator", {"side": "left", "sticky": ""}),
                        ("Checkbutton.label", {"side": "left", "sticky": "nswe"}),
                    ],
                },
            )
        ],
    )
    style.configure(
        "Compression.TRadiobutton",
        background=PANEL,
        foreground=INK,
        padding=9,
        borderwidth=1,
        relief="solid",
    )
    style.map(
        "Compression.TRadiobutton",
        background=[("selected", SOFT), ("active", SOFT)],
        foreground=[("selected", BLUE)],
    )
    style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor=LINE, borderwidth=0)
    return style
