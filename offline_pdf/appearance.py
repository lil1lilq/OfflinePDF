"""Two complete application palettes, applied to existing widgets without data loss."""

import sys
import tkinter as tk
from tkinter import ttk

DEFAULT = dict(
    BG="#f5f7fb",
    PANEL="#ffffff",
    INK="#202b3d",
    MUTED="#637086",
    RED="#c62828",
    LINE="#e2e7ef",
    BLUE="#285de5",
    SOFT="#edf2ff",
)
DARK = dict(
    BG="#1c2027",
    PANEL="#292e37",
    INK="#edf1f7",
    MUTED="#abb8cb",
    RED="#ff8585",
    LINE="#485263",
    BLUE="#82aaff",
    SOFT="#303f59",
)
_current = dict(DEFAULT)


def palette():
    return dict(_current)


def apply_theme(root, name):
    global _current
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
                except tk.TclError:
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
