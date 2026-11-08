"""Translate presentation text at the Tk boundary; processing values stay canonical."""

import json
import re
import tkinter as tk
import weakref
from pathlib import Path

_LANGUAGE = "ko"
_CATALOG = json.loads((Path(__file__).with_name("translations.json")).read_text(encoding="utf-8"))
_TEXT = weakref.WeakKeyDictionary()
_TITLES = weakref.WeakKeyDictionary()
_CHOICES = weakref.WeakSet()
_INSTALLED = False
_PATTERNS = []
for _source, _target in _CATALOG.items():
    if re.search(r"\{\d+\}", _source):
        _parts = re.split(r"(\{\d+\})", _source)
        _pattern = "".join("(.*?)" if re.fullmatch(r"\{\d+\}", p) else re.escape(p) for p in _parts)
        _PATTERNS.append((re.compile("^" + _pattern + "$", re.S), _target))

_PATTERNS.sort(key=lambda item: len(item[0].pattern.replace("(.*?)", "")), reverse=True)


def language():
    return _LANGUAGE


def tr(text):
    if _LANGUAGE == "ko" or not isinstance(text, str):
        return text
    if text in _CATALOG:
        return _CATALOG[text]
    for prefix in ("✓  ", "!  ", "↻  "):
        if text.startswith(prefix):
            return prefix + tr(text[len(prefix) :])
    if text.endswith("  →"):
        return tr(text[: -len("  →")]) + "  →"
    if "  /  " in text:
        return "  /  ".join(tr(part) for part in text.split("  /  "))
    for pattern, target in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return target.format(*(tr(v) for v in match.groups()))
    if " · " in text:
        return " · ".join(tr(part) for part in text.split(" · "))
    return text


class DisplayVar(tk.StringVar):
    __hash__ = object.__hash__

    def __init__(self, *args, value="", **kwargs):
        self._source = value
        super().__init__(*args, value=tr(value), **kwargs)
        _CHOICES.add(self)

    def get(self):
        return self._source

    def set(self, value):
        self._source = value
        super().set(tr(value))

    def refresh(self):
        self.set(self._source)


class ChoiceVar(tk.StringVar):
    """English display values with unchanged Korean worker/API values."""

    def __init__(self, *args, choices=(), **kwargs):
        self.choices = tuple(choices)
        super().__init__(*args, **kwargs)
        _CHOICES.add(self)
        self.refresh()

    __hash__ = object.__hash__

    def get(self):
        value = super().get()
        for choice in self.choices:
            if value == _CATALOG.get(choice, choice):
                return choice
        return value

    def set(self, value):
        super().set(tr(value))

    def refresh(self):
        self.set(self.get())


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_options = tk.Misc._options
    original_title = tk.Wm.wm_title
    original_delete = tk.Canvas.delete
    original_create = tk.Canvas.create_text
    original_itemconfigure = tk.Canvas.itemconfigure

    def options(self, cnf, kw=None):
        values = dict(tk._cnfmerge((cnf, kw)) if kw else cnf)
        if not isinstance(self, tk.Canvas) and "text" in values:
            _TEXT[self] = values["text"]
            values["text"] = tr(values["text"])
        for key in ("title", "message", "detail"):
            if key in values:
                values[key] = tr(values[key])
        if "filetypes" in values:
            values["filetypes"] = [
                (tr(name), extensions) for name, extensions in values["filetypes"]
            ]
        if "values" in values:
            self._canonical_values = tuple(values["values"])
            values["values"] = tuple(tr(v) for v in values["values"])
        return original_options(self, values)

    def title(self, value=None):
        if value is not None:
            _TITLES[self] = value
            value = tr(value)
        return original_title(self, value)

    def create_text(self, *args, **kwargs):
        source = kwargs.get("text", "")
        kwargs["text"] = tr(source)
        item = original_create(self, *args, **kwargs)
        if not hasattr(self, "_localized_text"):
            self._localized_text = {}
        self._localized_text[item] = source
        return item

    def itemconfigure(self, tag, cnf=None, **kwargs):
        if "text" in kwargs:
            if not hasattr(self, "_localized_text"):
                self._localized_text = {}
            self._localized_text[tag] = kwargs["text"]
            kwargs["text"] = tr(kwargs["text"])
        return original_itemconfigure(self, tag, cnf, **kwargs)

    def delete(self, *tags):
        for tag in tags:
            for item in self.find_withtag(tag):
                getattr(self, "_localized_text", {}).pop(item, None)
        return original_delete(self, *tags)

    tk.Canvas.delete = delete
    tk.Misc._options = options
    tk.Wm.wm_title = tk.Wm.title = title
    tk.Canvas.create_text = create_text
    tk.Canvas.itemconfigure = tk.Canvas.itemconfig = itemconfigure


def apply_language(root, value):
    global _LANGUAGE
    _LANGUAGE = value if value in ("ko", "en") else "ko"
    active_variables = set()

    def collect(widget):
        for option in ("variable", "textvariable"):
            try:
                active_variables.add(str(widget.cget(option)))
            except (tk.TclError, ValueError):
                pass
        for child in widget.winfo_children():
            collect(child)

    collect(root)
    for var in list(_CHOICES):
        try:
            if var._tk is not root.tk:
                continue
            if var.trace_info() and str(var) not in active_variables:
                continue
            var.refresh()
        except tk.TclError:
            pass
    for widget, source in list(_TEXT.items()):
        try:
            if widget.tk is not root.tk:
                continue
            widget.configure(text=source)
        except tk.TclError:
            pass
    for widget, source in list(_TITLES.items()):
        try:
            if widget.tk is not root.tk:
                continue
            widget.title(source)
        except tk.TclError:
            pass

    def visit(widget):
        if hasattr(widget, "source_text"):
            # Some wrappers record whatever text they receive as their source.
            # Keep the canonical Korean text so repeated switches never mix languages.
            source = widget.source_text
            translates = getattr(widget, "translates_text", False)
            widget.configure(text=source if translates else tr(source))
            widget.source_text = source
        if hasattr(widget, "_canonical_values"):
            widget.configure(values=widget._canonical_values)
        if isinstance(widget, tk.Canvas):
            for item, source in list(getattr(widget, "_localized_text", {}).items()):
                if widget.type(item):
                    widget.itemconfigure(item, text=source)
                else:
                    widget._localized_text.pop(item, None)
        for child in widget.winfo_children():
            visit(child)

    visit(root)
