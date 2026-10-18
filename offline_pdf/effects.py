"""Small Tk-thread hover transitions; no native callback calls into Tcl."""

import time
import tkinter as tk


def mix(a, b, t):
    return "#" + "".join(
        f"{round(int(a[i : i + 2], 16) * (1 - t) + int(b[i : i + 2], 16) * t):02x}"
        for i in (1, 3, 5)
    )


class Tween:
    def __init__(self, widget, paint):
        self.widget = widget
        self.paint = paint
        self.value = 0.0
        self.timer = None

    def to(self, target):
        if self.timer:
            self.widget.after_cancel(self.timer)
            self.timer = None
        start = self.value
        began = time.monotonic()

        def tick():
            self.timer = None
            if not self.widget.winfo_exists():
                return
            t = min(1, (time.monotonic() - began) / 0.16)
            eased = 1 - (1 - t) ** 3
            self.value = start + (target - start) * eased
            self.paint(self.value)
            if t < 1:
                self.timer = self.widget.after(16, tick)

        tick()

    def close(self):
        if self.timer:
            try:
                self.widget.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None
