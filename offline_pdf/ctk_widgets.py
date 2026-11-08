"""Small ttk-shaped presentation adapters; processing controllers keep their API."""

from __future__ import annotations

import customtkinter as ctk

from . import theme
from .localization import tr
from .theme import colors


def _palette():
    return colors("default"), colors("dark")


def _pair(name):
    light, dark = _palette()
    return (light[name], dark[name])


def _semantic_color(color):
    light, dark = _palette()
    for name in ("BG", "PANEL", "INK", "MUTED", "RED", "LINE", "BLUE", "SOFT"):
        if color == light[name]:
            return (light[name], dark[name])
    return color


def _style(name):
    return "panel" if name and ("Panel" in name or "Section" in name) else "background"


class _Text:
    def configure(self, **kwargs):
        if "foreground" in kwargs:
            kwargs["text_color"] = _semantic_color(kwargs.pop("foreground"))
        if "text" in kwargs:
            self.source_text = kwargs["text"]
            kwargs["text"] = tr(kwargs["text"])
        return super().configure(**kwargs)

    config = configure


class Frame(ctk.CTkFrame):
    def __init__(self, master, style=None, padding=None, **kwargs):
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("fg_color", _pair("PANEL") if _style(style) == "panel" else "transparent")
        super().__init__(master, **kwargs)
        self.padding = padding

    config = ctk.CTkFrame.configure


class Label(_Text, ctk.CTkLabel):
    def __init__(self, master, style=None, foreground=None, width=None, font=None, **kwargs):
        self.source_text = kwargs.get("text", "")
        kwargs["text"] = tr(self.source_text)
        kwargs.setdefault(
            "text_color",
            _semantic_color(foreground)
            if foreground
            else (_pair("MUTED") if style and "Muted" in style else _pair("INK")),
        )
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("height", 0)
        if width is not None:
            kwargs["width"] = max(0, width * 8)
        if font is not None:
            kwargs["font"] = font
        else:
            kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        super().__init__(master, **kwargs)


class Button(_Text, ctk.CTkButton):
    def __init__(self, master, style=None, width=None, **kwargs):
        self.source_text = kwargs.get("text", "")
        kwargs["text"] = tr(self.source_text)
        kwargs.setdefault("height", 36)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        if width is not None:
            kwargs["width"] = max(36, width * 10)
        else:
            kwargs.setdefault("width", 105)
        if style == "Run.TButton":
            kwargs.setdefault("fg_color", _pair("BLUE"))
            kwargs.setdefault("hover_color", ("#2948c3", "#c3d0ff"))
            kwargs.setdefault("text_color", ("#ffffff", "#172135"))
            kwargs.setdefault("border_color", _pair("BLUE"))
        else:
            kwargs.setdefault("fg_color", _pair("PANEL"))
            kwargs.setdefault("hover_color", _pair("SOFT"))
            kwargs.setdefault("text_color", _pair("INK"))
            kwargs.setdefault("border_color", _pair("LINE"))
        super().__init__(master, **kwargs)


class Entry(ctk.CTkEntry):
    def __init__(self, master, width=None, **kwargs):
        if width is not None:
            kwargs["width"] = max(90, width * 10)
        kwargs.setdefault("height", 36)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        kwargs.setdefault("corner_radius", 9)
        kwargs.setdefault("fg_color", _pair("PANEL"))
        kwargs.setdefault("border_color", _pair("LINE"))
        kwargs.setdefault("text_color", _pair("INK"))
        super().__init__(master, **kwargs)

    config = ctk.CTkEntry.configure

    def selection_range(self, start, end):
        return self._entry.selection_range(start, end)


class Combobox(ctk.CTkComboBox):
    def __init__(self, master, textvariable=None, width=None, values=(), **kwargs):
        if width is not None:
            kwargs["width"] = max(110, width * 10)
        kwargs.setdefault("height", 36)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        kwargs.setdefault("corner_radius", 9)
        kwargs.setdefault("fg_color", _pair("PANEL"))
        kwargs.setdefault("border_color", _pair("LINE"))
        kwargs.setdefault("text_color", _pair("INK"))
        self._canonical_values = tuple(values)
        super().__init__(
            master,
            variable=textvariable,
            values=[tr(v) for v in values],
            command=lambda value: self._entry.event_generate("<<ComboboxSelected>>"),
            **kwargs,
        )

    def configure(self, **kwargs):
        if "values" in kwargs:
            self._canonical_values = tuple(kwargs["values"])
            kwargs["values"] = [tr(v) for v in kwargs["values"]]
        return super().configure(**kwargs)

    config = configure


class Radiobutton(_Text, ctk.CTkRadioButton):
    def __init__(self, master, style=None, **kwargs):
        self.source_text = kwargs.get("text", "")
        kwargs["text"] = tr(self.source_text)
        kwargs.setdefault("text_color", _pair("INK"))
        kwargs.setdefault("fg_color", _pair("BLUE"))
        kwargs.setdefault("width", 105)
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        super().__init__(master, **kwargs)


class Checkbutton(_Text, ctk.CTkCheckBox):
    def __init__(self, master, style=None, **kwargs):
        self.source_text = kwargs.get("text", "")
        kwargs["text"] = tr(self.source_text)
        kwargs.setdefault("text_color", _pair("INK"))
        kwargs.setdefault("fg_color", _pair("BLUE"))
        kwargs.setdefault("font", (theme.FONT_FAMILY, 12))
        super().__init__(master, **kwargs)


class Progressbar(ctk.CTkProgressBar):
    def __init__(self, master, mode="determinate", **kwargs):
        kwargs.setdefault("progress_color", _pair("BLUE"))
        super().__init__(master, mode=mode, **kwargs)

    def __setitem__(self, key, value):
        if key == "value":
            self.set(float(value) / 100)
        else:
            super().__setitem__(key, value)


class Scrollbar(ctk.CTkScrollbar):
    def __init__(self, master, **kwargs):
        if "orient" in kwargs:
            kwargs["orientation"] = kwargs.pop("orient")
        kwargs.setdefault("width", 16)
        kwargs.setdefault("button_color", ("#8390a4", "#8793a5"))
        kwargs.setdefault("button_hover_color", _pair("MUTED"))
        super().__init__(master, **kwargs)


class Scale(ctk.CTkSlider):
    def __init__(self, master, from_=0, to=100, variable=None, **kwargs):
        if "length" in kwargs:
            kwargs["width"] = kwargs.pop("length")
        super().__init__(master, from_=from_, to=to, variable=variable, **kwargs)
