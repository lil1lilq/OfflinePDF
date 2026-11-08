"""Local Tk widgets for the card home and task workspace."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from . import theme
from .theme import (
    BUTTON_RADIUS,
    CARD_GROUP,
    CARD_PADDING,
    CARD_RADIUS,
    colors,
    resource_path,
)
from .tools import TOOLS

BG = "#f4f6fa"
PANEL = "#ffffff"
INK = "#111827"
MUTED = "#374151"
RED = "#b3384a"
LINE = "#dfe5ef"
BLUE = "#3759da"
SOFT = "#eaf0ff"
FONT = "맑은 고딕"

# Card heights sized for 16:9 desktop windows: all 16 tools fit on one screen.
CARD_MIN_HEIGHT = 140
CARD_MAX_HEIGHT = 168
POPULAR = ("merge", "split", "extract", "compress", "ocr", "pdf_images")
# Titles share one source; compact summaries fit the basic cards.
CARD_SUMMARIES = {
    "merge": "여러 파일을 하나의 PDF로 합칩니다",
    "split": "페이지별 또는 N개 파일로 나눕니다",
    "extract": "페이지 순서·삭제·회전을 편집합니다",
    "nup": "A4 한 장에 원하는 쪽수만큼 배치합니다",
    "compress": "압축 수준을 선택해 용량을 줄입니다",
    "upscale": "스캔 이미지를 AI로 확대·보정합니다",
    "pdf_images": "PDF 페이지를 이미지로 저장합니다",
    "images_pdf": "이미지를 PDF로 변환합니다",
    "protect": "PDF 암호를 설정하거나 제거합니다",
    "watermark": "문구 또는 서명·직인 이미지를 넣습니다",
    "number": "페이지에 쪽 번호를 넣습니다",
    "crop": "페이지 가장자리의 여백을 조정합니다",
    "text": "PDF 글자를 TXT로 저장합니다",
    "redact": "선택 영역의 내용을 영구 삭제합니다",
    "clean": "문서에 포함된 부가정보를 정리합니다",
    "ocr": "스캔 문서의 글자를 인식합니다",
}
CARD_TEXT = {key: (title, CARD_SUMMARIES[key]) for key, (title, _) in TOOLS.items()}


def chip_color(key):
    """Light/dark background of a tool's icon chip, by its card group."""
    group = CARD_GROUP[key]
    return colors("default")[group][0], colors("dark")[group][0]


_TINTED_ICONS = {}


def tool_icon(key, size=24):
    """The tool's bundled Lucide icon, tinted for light and dark themes.

    The tinted pictures are cached; each caller gets its own CTkImage, which
    binds to the Tk interpreter that first draws it.
    """
    if key not in _TINTED_ICONS:
        group = CARD_GROUP[key]
        light, dark = colors("default")[group][1], colors("dark")[group][1]
        with Image.open(resource_path("lucide", f"{key}.png")) as image:
            mask = image.getchannel("A")

            def tinted(color):
                rgb = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
                result = Image.new("RGBA", image.size, (*rgb, 0))
                result.putalpha(mask)
                return result

            _TINTED_ICONS[key] = tinted(light), tinted(dark)
    light_image, dark_image = _TINTED_ICONS[key]
    return ctk.CTkImage(light_image=light_image, dark_image=dark_image, size=(size, size))


class ScrollPane(ctk.CTkScrollableFrame):
    """Scrollable home with a canvas alias for navigation and native drop routing."""

    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=("#f4f6fa", "#171c25"),
            corner_radius=0,
            scrollbar_button_color=("#8390a4", "#8793a5"),
            scrollbar_button_hover_color=("#374151", "#d5dce6"),
            **kwargs,
        )
        self.inner = self
        self.canvas = self._parent_canvas

    def winfo_ismapped(self):
        return self._parent_frame.winfo_ismapped()

    def winfo_manager(self):
        return self._parent_frame.winfo_manager()


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


class ToolCard(ctk.CTkFrame):
    """Accessible, entirely clickable CTk card with a bundled Lucide image."""

    def __init__(self, master, key, command):
        super().__init__(
            master,
            width=220,
            height=CARD_MIN_HEIGHT,
            corner_radius=CARD_RADIUS,
            border_width=1,
            fg_color=("#ffffff", "#222a36"),
            border_color=("#dfe5ef", "#394557"),
        )
        self.key = key
        self.command = command
        self.active = False
        self.pressed = False
        self.hover_amount = 0.0
        self.enabled = True
        self.compact = False
        self.pack_propagate(False)
        self.tooltip = Tooltip(self, TOOLS[key][1])
        self.chip = ctk.CTkFrame(
            self,
            width=40,
            height=40,
            corner_radius=10,
            fg_color=chip_color(key),
        )
        self.chip.pack(anchor="w", padx=CARD_PADDING, pady=(14, 0))
        self.chip.pack_propagate(False)
        self.icon_image = tool_icon(key)
        self.icon = ctk.CTkLabel(self.chip, text="", image=self.icon_image, width=24, height=24)
        self.icon.place(relx=0.5, rely=0.5, anchor="center")
        title, description = CARD_TEXT[key]
        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            anchor="w",
            justify="left",
            height=0,
            text_color=("#111827", "#f8fafc"),
            font=(theme.BOLD_FAMILY, 16, "bold"),
        )
        self.title_label.pack(fill="x", anchor="w", padx=CARD_PADDING, pady=(10, 0))
        self.description_label = ctk.CTkLabel(
            self,
            text=description,
            anchor="nw",
            justify="left",
            height=0,
            text_color=("#374151", "#d5dce6"),
            font=(FONT, 13),
        )
        self.description_label.pack(fill="x", anchor="w", padx=CARD_PADDING, pady=(4, 10))
        self.bind("<Configure>", self._resize_text, add="+")
        self._bind_tree(self)
        self.bind("<Unmap>", lambda e: self.tooltip.hide(), add="+")
        self.bind("<Destroy>", lambda e: self.tooltip.hide() if e.widget is self else None, add="+")

    def _bind_tree(self, widget):
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress-1>", self._press, add="+")
        widget.bind("<ButtonRelease-1>", self._release, add="+")
        widget.bind("<Return>", lambda e: self.activate(), add="+")
        widget.bind("<space>", lambda e: self.activate(), add="+")
        for child in widget.winfo_children():
            self._bind_tree(child)
        if widget is self:
            widget._canvas.configure(takefocus=True)

    def _pointer_inside(self):
        x, y = self.winfo_pointerxy()
        return (
            self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height()
        )

    def _press(self, event):
        self.pressed = True

    def _release(self, event):
        # Only a click that started on this card opens it. A release left over
        # from a button in a dialog that just closed above the card is ignored.
        pressed, self.pressed = self.pressed, False
        if pressed and self._pointer_inside():
            self.activate()

    def _enter(self, event):
        self.highlight(True)

    def _leave(self, event):
        # Child-to-child crossings should not flash the border.
        if not self._pointer_inside():
            self.highlight(False)

    def highlight(self, active):
        self.active = active and self.enabled
        self.hover_amount = float(self.active)
        self.paint()
        if self.active:
            self.tooltip.schedule()
        else:
            self.tooltip.hide()

    def _resize_text(self, event=None):
        width = max(60, self.winfo_width() - 2 * CARD_PADDING - 4)
        if width == getattr(self, "_text_wrap_width", None):
            return
        self._text_wrap_width = width
        self.title_label.configure(wraplength=width)
        self.description_label.configure(wraplength=width)

    def activate(self):
        # The card is hidden while its tool opens, so no <Leave> event arrives.
        # Clear the hover state now so it is not still shown on return.
        self.pressed = False
        self.highlight(False)
        if self.enabled:
            self.command(self.key)

    def set_compact(self, compact, height):
        self.compact = compact
        if self.cget("height") != height:
            self.configure(height=height)
        self._resize_text()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.paint()

    def paint(self):
        self.configure(
            border_color=("#3759da", "#a9bcff")
            if self.active and self.enabled
            else ("#dfe5ef", "#394557")
        )
        self.title_label.configure(
            text_color=("#111827", "#f8fafc") if self.enabled else ("#374151", "#d5dce6")
        )
        self.description_label.configure(
            text=CARD_TEXT[self.key][1]
            if self.enabled
            else "현재 결과의 파일 형식은 지원하지 않습니다"
        )


def setup_style(root):
    from .effects import mix

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=INK, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Panel.TLabel", background=PANEL)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=(FONT, 9))
    style.configure("Title.TLabel", font=(theme.BOLD_FAMILY, 20, "bold"))
    style.configure("Task.TLabel", font=(theme.BOLD_FAMILY, 16, "bold"))
    style.configure("Section.TLabel", font=(theme.BOLD_FAMILY, 10, "bold"), background=PANEL)
    # Image elements are stretched through their centre, preserving 10px corners.
    # Retain the PhotoImage references for the entire lifetime of the window.
    if not hasattr(root, "button_images"):
        root.button_images = []
    dark = PANEL.lower() != "#ffffff"
    variants = {
        "Secondary": (PANEL, LINE, SOFT),
        "Ghost": (PANEL, PANEL, SOFT),
        "Primary": (
            ("#a9bcff" if dark else "#3759da"),
            ("#a9bcff" if dark else "#3759da"),
            ("#c3d0ff" if dark else "#2948c3"),
        ),
    }
    for kind, (base, border, hover) in variants.items():
        images = []
        for state in ("normal", "active", "pressed", "disabled"):
            fill = (
                mix(base, BG, 0.55)
                if state == "disabled"
                else mix(hover, base, 0.35)
                if state == "pressed"
                else hover
                if state == "active"
                else base
            )
            image = Image.new("RGB", (52, 36), PANEL)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (1, 1, 50, 34),
                radius=BUTTON_RADIUS,
                fill=fill,
                outline=border if state != "disabled" else LINE,
            )
            photo = ImageTk.PhotoImage(image, master=root)
            root.button_images.append(photo)
            images.append(photo)
        element = f"Offline{kind}{'Dark' if dark else 'Light'}.border"
        if element not in style.element_names():
            style.element_create(
                element,
                "image",
                images[0],
                ("disabled", images[3]),
                ("pressed", images[2]),
                ("active", images[1]),
                border=(12, 12, 12, 12),
                sticky="nswe",
            )
        for style_name in (
            ("TButton", "Back.TButton")
            if kind == "Secondary"
            else ("Quiet.TButton",)
            if kind == "Ghost"
            else ("Run.TButton",)
        ):
            style.layout(
                style_name,
                [
                    (
                        element,
                        {
                            "sticky": "nswe",
                            "children": [
                                (
                                    "Button.padding",
                                    {
                                        "sticky": "nswe",
                                        "children": [("Button.label", {"sticky": "nswe"})],
                                    },
                                )
                            ],
                        },
                    )
                ],
            )
            fg = "#ffffff" if kind == "Primary" and not dark else INK
            if kind == "Primary" and dark:
                fg = "#172135"
            style.configure(
                style_name,
                padding=(14, 9),
                background=PANEL,
                foreground=fg,
                font=(FONT, 10),
                borderwidth=1,
            )
            style.map(style_name, foreground=[("disabled", MUTED), ("!disabled", fg)])
    style.configure("Back.TButton", padding=(20, 12), font=(theme.BOLD_FAMILY, 11, "bold"))
    style.configure("Run.TButton", padding=(22, 12), font=(theme.BOLD_FAMILY, 11, "bold"))
    style.configure(
        "TEntry",
        fieldbackground=PANEL,
        foreground=INK,
        insertcolor=INK,
        padding=7,
        bordercolor=LINE,
        lightcolor=LINE,
        darkcolor=LINE,
    )
    style.configure("Settings.TRadiobutton", background=BG, foreground=INK)
    style.map("Settings.TRadiobutton", background=[("active", SOFT)])
    style.configure("TRadiobutton", background=PANEL, foreground=INK)
    style.map("TRadiobutton", background=[("active", SOFT)])
    # A 16px thumb-only vertical scrollbar, without Clam's arrow elements.
    thumb = Image.new("RGBA", (16, 40), (0, 0, 0, 0))
    ImageDraw.Draw(thumb).rounded_rectangle((2, 1, 13, 38), radius=6, fill=MUTED)
    thumb_photo = ImageTk.PhotoImage(thumb, master=root)
    root.button_images.append(thumb_photo)
    thumb_element = f"OfflineScroll{'Dark' if dark else 'Light'}.thumb"
    if thumb_element not in style.element_names():
        style.element_create(
            thumb_element, "image", thumb_photo, border=(6, 10, 6, 10), sticky="nswe"
        )
    style.layout(
        "Vertical.TScrollbar",
        [
            (
                "Vertical.Scrollbar.trough",
                {"sticky": "ns", "children": [(thumb_element, {"expand": "1", "sticky": "nswe"})]},
            )
        ],
    )
    style.configure(
        "Vertical.TScrollbar",
        width=16,
        background=MUTED,
        troughcolor=BG,
        bordercolor=BG,
        lightcolor=MUTED,
        darkcolor=MUTED,
        relief="flat",
        borderwidth=0,
    )
    style.map("Vertical.TScrollbar", background=[("active", BLUE), ("pressed", BLUE)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK)
    style.configure("TCombobox", fieldbackground=PANEL, padding=7, bordercolor=LINE, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)])
    style.configure("TCheckbutton", background=PANEL)
    # Explicit tick images avoid the Clam theme's cross-shaped indicator.
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
                fill="#ffffff",
                width=max(2, size // 8),
            )
        images.append(ImageTk.PhotoImage(image, master=root))
        image.close()
    root.checkbox_images = images
    element = "OfflineCheck" + PANEL.replace("#", "") + ".indicator"
    if not hasattr(root, "all_checkbox_images"):
        root.all_checkbox_images = []
    root.all_checkbox_images.extend(images)
    if element not in style.element_names():
        style.element_create(element, "image", images[0], ("selected", images[1]), sticky="")
    style.layout(
        "TCheckbutton",
        [
            (
                "Checkbutton.padding",
                {
                    "sticky": "nswe",
                    "children": [
                        (element, {"side": "left", "sticky": ""}),
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
