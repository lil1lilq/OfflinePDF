"""Compact option controls whose expanded choices do not resize the document."""

from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk

from . import ctk_widgets as ttk
from .dialogs import monitor_work_area
from .localization import tr
from .overlays import POSITIONS


def picker_position(anchor, size, bounds):
    """Prefer below the button; flip and clamp within its monitor's work area."""
    left, top, right, bottom = bounds
    width, height = size
    x = max(left, min(anchor[0], right - width))
    y = anchor[3]
    if y + height > bottom:
        y = anchor[1] - height
    return x, max(top, min(y, bottom - height))


class ChoicePopup(ttk.Button):
    """One-line selection with a transient, keyboard-accessible visual picker."""

    def __init__(self, master, variable, kind="position"):
        self.variable = variable
        self.kind = kind
        self.popup = None
        self.outside_binding = None
        super().__init__(master, command=self.open_picker, cursor="hand2", width=12)
        self.trace = variable.trace_add("write", self.refresh)
        self.refresh()
        self._text_label.configure(takefocus=True)
        self.bind("<Return>", lambda event: self.open_picker())
        self.bind("<space>", lambda event: self.open_picker())

    def refresh(self, *_):
        value = self.variable.get()
        self.configure(text=f"{value} ▾")

    def close_picker(self):
        root = self.winfo_toplevel()
        if self.outside_binding is not None:
            root.unbind("<ButtonPress-1>", self.outside_binding)
            self.outside_binding = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None

    def choose(self, value):
        self.variable.set(value)
        self.close_picker()
        self.focus_set()

    def open_picker(self):
        if str(self.cget("state")) == "disabled":
            return
        if self.popup is not None:
            self.close_picker()
            return
        root = self.winfo_toplevel()
        previous = getattr(root, "_option_picker", None)
        if previous:
            previous.close_picker()
        root._option_picker = self
        popup = self.popup = ctk.CTkToplevel(root)
        popup.withdraw()
        popup.transient(root)
        popup.overrideredirect(True)
        popup.bind("<Escape>", lambda event: self.close_picker())
        body = ttk.Frame(popup, padding=8)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        choices = (
            sorted(POSITIONS, key=lambda name: POSITIONS[name][::-1])
            if self.kind == "position"
            else ("1", "2", "4", "6", "8", "9", "16")
        )
        selected = None
        for i, value in enumerate(choices):
            text = value if self.kind == "position" else f"{value}쪽"
            if self.kind == "nup":
                count = int(value)
                columns = math.ceil(math.sqrt(count))
                rows = math.ceil(count / columns)
                text = (
                    "\n".join(
                        " ".join("□" if r * columns + c < count else " " for c in range(columns))
                        for r in range(rows)
                    )
                    + "\n"
                    + tr(text)
                )
            button = ttk.Button(
                body,
                text=text,
                width=9,
                height=64 if self.kind == "nup" else 42,
                cursor="hand2",
                command=lambda value=value: self.choose(value),
                style="Run.TButton" if value == self.variable.get() else None,
            )
            button.grid(row=i // 3, column=i % 3, padx=3, pady=3, sticky="nsew")
            button._text_label.configure(takefocus=True)
            button.bind("<Return>", lambda event, value=value: self.choose(value))
            button.bind("<space>", lambda event, value=value: self.choose(value))
            if value == self.variable.get():
                selected = button
        if self.kind == "nup":
            ttk.Label(body, text="직접 입력 (1~64)").grid(row=3, column=0, pady=(6, 0))
            entry = ttk.Entry(body, textvariable=self.variable, width=10)
            entry.grid(row=3, column=1, padx=3, pady=(6, 0))
            entry.bind("<Return>", lambda event: self.choose(self.variable.get()))
            ttk.Button(body, text="확인", width=7, command=self.close_picker).grid(
                row=3, column=2, pady=(6, 0)
            )
        popup.update_idletasks()
        self.position_picker()
        # Crossing monitors can change CTk's DPI scaling and the popup size.
        popup.bind("<Configure>", self.position_picker)
        popup.deiconify()
        popup.lift()
        (selected or button).focus_set()
        popup.bind("<FocusOut>", lambda event: root.after_idle(self.dismiss_if_outside))
        self.outside_binding = root.bind("<ButtonPress-1>", self.outside_click, add="+")

    def position_picker(self, event=None):
        popup = self.popup
        if popup is None or (event is not None and event.widget is not popup):
            return
        x, y = self.winfo_rootx(), self.winfo_rooty()
        anchor = (x, y, x + self.winfo_width(), y + self.winfo_height())
        bounds = monitor_work_area(anchor)
        if bounds is None:
            owner = self.winfo_toplevel()
            left, top = owner.winfo_rootx(), owner.winfo_rooty()
            bounds = (left, top, left + owner.winfo_width(), top + owner.winfo_height())
        x, y = picker_position(anchor, (popup.winfo_reqwidth(), popup.winfo_reqheight()), bounds)
        if (popup.winfo_rootx(), popup.winfo_rooty()) != (x, y):
            # '+-1200' is an absolute negative coordinate; '-1200' is edge-relative.
            popup.geometry(f"+{x}+{y}")

    def outside_click(self, event):
        if not str(event.widget).startswith(str(self) + ".") and event.widget != self:
            self.close_picker()

    def dismiss_if_outside(self):
        if self.popup is not None:
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() != self.popup:
                self.close_picker()

    def destroy(self):
        self.close_picker()
        root = self.winfo_toplevel()
        if getattr(root, "_option_picker", None) is self:
            root._option_picker = None
        self.variable.trace_remove("write", self.trace)
        super().destroy()


class PercentOpacity(ttk.Frame):
    """Display 0–100 percent while keeping the worker's 0–1 option unchanged."""

    def __init__(self, master, variable):
        super().__init__(master, style="Panel.TFrame")
        self.variable = variable
        self.percent = tk.DoubleVar(master=self, value=float(variable.get()) * 100)
        self.label = ttk.Label(self, text="", width=5)
        self.label.pack(side="right", padx=(4, 0))
        self.slider = ttk.Scale(
            self,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.percent,
            command=lambda value: variable.set(f"{round(value) / 100:g}"),
            width=100,
        )
        self.slider.pack(side="left", fill="x", expand=True, pady=9)
        self.trace = variable.trace_add("write", self.refresh)
        self.refresh()

    def refresh(self, *_):
        try:
            value = float(self.variable.get())
            if not 0 <= value <= 1:
                return
        except ValueError:
            return
        self.percent.set(value * 100)
        self.label.configure(text=f"{value:.0%}")

    def destroy(self):
        self.variable.trace_remove("write", self.trace)
        super().destroy()
