"""Two complete application palettes, applied to existing widgets without data loss."""

import sys
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from .theme import set_mode

DEFAULT = dict(
    BG="#f4f6fa",
    PANEL="#ffffff",
    INK="#202a3a",
    MUTED="#526078",
    RED="#b3384a",
    LINE="#dfe5ef",
    BLUE="#3759da",
    SOFT="#eaf0ff",
)
DARK = dict(
    BG="#171c25",
    PANEL="#222a36",
    INK="#eff3fa",
    MUTED="#b7c2d2",
    RED="#ff929e",
    LINE="#394557",
    BLUE="#a9bcff",
    SOFT="#303b53",
)
_current = dict(DEFAULT)


def palette():
    return dict(_current)


def apply_theme(root, name):
    global _current
    set_mode(name)
    target = DARK if name == "dark" else DEFAULT
    old = _current
    mapping = {v.lower(): target[k] for k, v in old.items()}
    mapping.update(
        {
            "#15191f": "#15191f" if name == "dark" else "#e9edf4",
            "#e9edf4": "#15191f" if name == "dark" else "#e9edf4",
            "white": target["PANEL"],
            "black": target["INK"],
        }
    )
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("offline_pdf") and module is not None:
            for key, color in target.items():
                if hasattr(module, key) and module_name != __name__:
                    setattr(module, key, color)

    def visit(widget):
        if isinstance(widget, (ctk.CTk, ctk.CTkBaseClass, ctk.CTkScrollableFrame)):
            for child in widget.winfo_children():
                visit(child)
            return
        if not isinstance(widget, ttk.Widget):
            options = {}
            for key in (
                "bg",
                "fg",
                "highlightbackground",
                "highlightcolor",
                "insertbackground",
                "selectbackground",
                "selectforeground",
            ):
                try:
                    color = str(widget.cget(key)).lower()
                    if color in mapping:
                        options[key] = mapping[color]
                except (tk.TclError, ValueError):
                    pass
            if options:
                widget.configure(**options)
        if isinstance(widget, tk.Canvas):
            for item in widget.find_all():
                for key in ("fill", "outline"):
                    try:
                        color = widget.itemcget(item, key).lower()
                        if color in mapping:
                            widget.itemconfigure(item, **{key: mapping[color]})
                    except tk.TclError:
                        pass
        for child in widget.winfo_children():
            visit(child)

    visit(root)
    _current = dict(target)
    from .ui import setup_style

    setup_style(root)
