"""Shared sidebar and fixed-height feedback for the desktop workspace."""

import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from .effects import mix
from .ui import BG, BLUE, FONT, INK, LINE, MUTED, PANEL, RED, SOFT, Tooltip


class FileList(tk.Canvas):
    """File rows with Listbox-compatible selection methods and visible metadata."""

    own_wheel = True

    def __init__(self, master, app):
        super().__init__(
            master, bg=PANEL, highlightthickness=0, width=190, height=150, takefocus=True
        )
        self.app = app
        self.rows = []
        self.selection = set()
        self.row_height = 72
        self.timer = None
        self.flash_rows = set()
        self.flash_value = 0.0
        self.motion_timer = None
        self.motion_rows = []
        self.motion_value = 1.0
        self.motion_kind = None
        self.positions = {}
        self.motion_clock = time.monotonic
        self.drop_hover = 0.0
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self.click)
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<Button-4>", self.wheel)
        self.bind("<Button-5>", self.wheel)
        self.bind("<Up>", lambda e: self.key(-1))
        self.bind("<Down>", lambda e: self.key(1))
        self.name_tooltip = Tooltip(self, "")
        self.tooltip_row = None
        self.bind("<Motion>", self.show_filename)
        self.bind("<Leave>", lambda event: self.name_tooltip.hide())
        self.name_font = tkfont.Font(family=FONT, size=9, weight="bold")

    def show_filename(self, event):
        index = int(self.canvasy(event.y) // self.row_height)
        if index != self.tooltip_row:
            self.tooltip_row = index
            self.name_tooltip.hide()
            if 0 <= index < len(self.rows):
                self.name_tooltip.text = self.rows[index][0]
                self.name_tooltip.schedule()

    def insert(self, index, text):
        self.rows.append((str(text), "", None))
        self.draw()

    def delete(self, first, last=None):
        if last == "end":
            self.rows = []
            self.selection.clear()
        elif self.rows:
            self.rows.pop(int(first))
            self.selection.clear()
        self.draw()

    def size(self):
        return len(self.rows)

    def get(self, index):
        return self.rows[int(index)][0]

    def curselection(self):
        return tuple(sorted(self.selection))

    def selection_clear(self, first, last=None):
        self.selection.clear()
        self.draw()

    def selection_set(self, first, last=None):
        if self.rows:
            end = (
                len(self.rows) - 1
                if last == "end"
                else int(last)
                if last is not None
                else int(first)
            )
            self.selection.update(range(max(0, int(first)), min(len(self.rows) - 1, end) + 1))
            self.draw()

    def set_files(self, files, metadata, animate=False):
        previous = list(self.rows)
        previous_positions = dict(self.positions)
        selected_paths = {self.rows[i][2] for i in self.selection if i < len(self.rows)}
        if self.motion_timer:
            self.after_cancel(self.motion_timer)
            self.motion_timer = None
        self.rows = [(Path(path).name, metadata(path), path) for path in files]
        self.selection = {i for i, row in enumerate(self.rows) if row[2] in selected_paths}
        if self.rows and not self.selection:
            self.selection = {0}
        self.motion_rows = []
        self.motion_kind = None
        self.motion_value = 1.0
        if animate and previous and [row[2] for row in previous] != [row[2] for row in self.rows]:
            old = {row[2]: (i, row) for i, row in enumerate(previous)}
            new_paths = {row[2] for row in self.rows}
            for i, row in enumerate(self.rows):
                old_index = old[row[2]][0] if row[2] in old else i
                start = previous_positions.get(row[2], (old_index * self.row_height, 1.0))[0]
                self.motion_rows.append(
                    (row, start, i * self.row_height, False, row[2] in selected_paths, 1.0)
                )
            for i, row in enumerate(previous):
                if row[2] not in new_paths:
                    start, opacity = previous_positions.get(row[2], (i * self.row_height, 1.0))
                    self.motion_rows.append(
                        (row, start, start, True, row[2] in selected_paths, opacity)
                    )
            self.motion_kind = "remove" if len(self.rows) < len(previous) else "move"
            self.motion_value = 0.0
            began = self.motion_clock()
            duration = 0.28 if self.motion_kind == "remove" else 0.24

            def tick():
                self.motion_timer = None
                if not self.winfo_exists():
                    return
                self.motion_value = min(1, (self.motion_clock() - began) / duration)
                self.draw()
                if self.motion_value < 1:
                    self.motion_timer = self.after(16, tick)
                else:
                    self.motion_rows = []
                    self.motion_kind = None
                    self.draw()

            tick()
        else:
            self.draw()

    def click(self, event):
        if self.app.busy() or self.motion_rows:
            return
        self.focus_set()
        index = int(self.canvasy(event.y) // self.row_height)
        if index >= len(self.rows):
            return
        if event.state & 4:
            if index in self.selection:
                self.selection.remove(index)
            else:
                self.selection.add(index)
        elif event.state & 1 and self.selection:
            self.selection.update(
                range(min(self.selection), index + 1)
                if index >= min(self.selection)
                else range(index, max(self.selection) + 1)
            )
        else:
            self.selection = {index}
        self.draw()
        self.event_generate("<<ListboxSelect>>")

    def key(self, delta):
        if self.app.busy() or self.motion_rows:
            return "break"
        index = max(
            0, min(len(self.rows) - 1, (min(self.selection) if self.selection else 0) + delta)
        )
        self.selection = {index} if self.rows else set()
        self.draw()
        self.event_generate("<<ListboxSelect>>")
        return "break"

    def wheel(self, event):
        step = (
            (-1 if event.num == 4 else 1) if event.num in (4, 5) else (-1 if event.delta > 0 else 1)
        )
        self.yview_scroll(step, "units")
        return "break"

    def draw(self):
        self.delete_items()
        w = max(150, self.winfo_width())
        selected_paths = {self.rows[i][2] for i in self.selection if i < len(self.rows)}
        extent = max(
            [len(self.rows) * self.row_height]
            + [max(start, end) + self.row_height for _, start, end, _, _, _ in self.motion_rows]
        )
        self.configure(scrollregion=(0, 0, w, extent), yscrollincrement=24)
        self.positions = {}
        records = []
        amount = (
            max(0, (self.motion_value - 0.45) / 0.55)
            if self.motion_kind == "remove"
            else self.motion_value
        )
        eased = 1 - (1 - amount) ** 3
        if self.motion_rows:
            for row, start, end, removed, was_selected, opacity in self.motion_rows:
                alpha = opacity * max(0, 1 - 2 * self.motion_value) if removed else 1.0
                if alpha > 0:
                    records.append(
                        (
                            row,
                            start + (end - start) * eased,
                            alpha,
                            was_selected if removed else row[2] in selected_paths,
                        )
                    )
        else:
            records = [
                (row, i * self.row_height, 1.0, row[2] in selected_paths)
                for i, row in enumerate(self.rows)
            ]
        # Draw the moving selected row on top while adjacent rows pass it.
        records.sort(key=lambda record: record[3])
        background = self.cget("bg")
        indices = {row[2]: i for i, row in enumerate(self.rows)}
        for (name, meta, path), y, opacity, selected in records:
            self.positions[path] = (y, opacity)
            full_name = name
            while name and self.name_font.measure(name) > 2 * (w - 25) - 24:
                name = name[:-1]
            if name != full_name:
                name += "…"
            meta = meta.replace("이 도구에서 사용 불가", "사용 불가")
            index = indices.get(path, -1)
            fill = (
                mix(PANEL, SOFT, self.flash_value)
                if index in self.flash_rows
                else SOFT
                if selected
                else BG
            )
            left, top = 3, y + 2
            right, bottom, radius = w - 3, y + self.row_height - 5, 12
            self.create_polygon(
                left + radius,
                top,
                right - radius,
                top,
                right,
                top,
                right,
                top + radius,
                right,
                bottom - radius,
                right,
                bottom,
                right - radius,
                bottom,
                left + radius,
                bottom,
                left,
                bottom,
                left,
                bottom - radius,
                left,
                top + radius,
                left,
                top,
                smooth=True,
                splinesteps=12,
                fill=mix(background, fill, opacity),
                outline=mix(background, BLUE if selected else LINE, opacity),
                width=1,
            )
            self.create_text(
                12,
                y + 13,
                anchor="nw",
                text=name,
                width=w - 25,
                font=(FONT, 9, "bold"),
                fill=mix(background, INK, opacity),
            )
            self.create_text(
                12,
                y + 52,
                anchor="w",
                text=meta,
                width=w - 25,
                font=(FONT, 8),
                fill=mix(background, MUTED, opacity),
            )

    def delete_items(self):
        super().delete("all")

    def flash(self, indices):
        if self.timer:
            self.after_cancel(self.timer)
        self.flash_rows = set(indices)
        start = time.monotonic()

        def tick():
            self.timer = None
            if not self.winfo_exists():
                return
            self.flash_value = max(0, 1 - (time.monotonic() - start) / 1.1)
            self.draw()
            if self.flash_value:
                self.timer = self.after(25, tick)
            else:
                self.flash_rows.clear()

        tick()

    def close(self):
        self.name_tooltip.hide()
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None
        if self.motion_timer:
            self.after_cancel(self.motion_timer)
            self.motion_timer = None
        self.motion_rows = []


class StatusFeedback:
    def __init__(self, app, label):
        self.app = app
        self.label = label
        self.timer = None
        self.serial = 0
        self.count_timer = None
        self.trace = app.status.trace_add("write", self.changed)

    def changed(self, *_):
        self.serial += 1
        text = self.app.status.get()
        warning = any(word in text for word in ("제외", "0개 추가", "선택하세요", "불가"))
        error = any(word in text for word in ("실패", "못했", "오류"))
        dark = PANEL != "#ffffff"
        color = RED if error else ("#ffbf75" if dark else "#965b18") if warning else BLUE
        fill = mix(PANEL, color, 0.14) if warning or error else SOFT
        mark = "!  " if warning or error else "↻  " if self.app.busy() else "✓  "
        self.label.config(text=mark + text, fg=color)
        if self.timer:
            self.label.after_cancel(self.timer)
        start = time.monotonic()

        def tick():
            self.timer = None
            if not self.label.winfo_exists():
                return
            t = min(1, (time.monotonic() - start) / 0.9)
            bg = mix(fill, PANEL, t)
            self.label.config(bg=bg)
            self.label.master.configure(fg_color=bg)
            if t < 1:
                self.timer = self.label.after(25, tick)

        tick()

    def file_added(self, indices):
        self.app.file_list.flash(indices)
        if self.count_timer:
            self.label.after_cancel(self.count_timer)
        self.app.file_count.configure(text_color=BLUE)
        self.count_timer = self.label.after(1100, self.end_count)

    def end_count(self):
        self.count_timer = None
        self.app.file_count.configure(text_color=INK)

    def close(self):
        self.app.status.trace_remove("write", self.trace)
        for timer in (self.timer, self.count_timer):
            if timer:
                try:
                    self.label.after_cancel(timer)
                except tk.TclError:
                    pass


class WindowDropHover:
    """Visual feedback follows native file drag events, never ordinary pointer hover."""

    def __init__(self, app):
        self.app = app
        self.active = False
        self.pointer_inside = False
        self.timer = None
        self.closed = False
        self.notice = tk.Label(
            app.root,
            text="놓으면 파일 목록에 추가됩니다",
            bg=PANEL,
            fg=INK,
            font=(FONT, 14, "bold"),
            padx=24,
            pady=18,
            highlightthickness=2,
            highlightbackground=BLUE,
        )
        self.poll()

    def _pointer(self, inside):
        self.pointer_inside = inside
        self.update_hover(
            bool(getattr(getattr(self.app, "file_drop", None), "_drag_active", False))
        )

    def update_hover(self, active, sidebar_active=False):
        active = bool(active and not self.app.busy())
        if active == self.active and getattr(self, "_last_pointer", None) == self.pointer_inside:
            return
        self.active = active
        self._last_pointer = self.pointer_inside
        # A color change leaves widget geometry stable; changing highlightthickness
        # on pointer entry previously caused the entire layout to jump.
        self.app.host.configure(highlightbackground=BLUE if active or self.pointer_inside else LINE)
        if active:
            self.notice.place(relx=0.5, rely=0.5, anchor="center")
            self.notice.lift()
        else:
            self.notice.place_forget()

    def poll(self):
        self.timer = None
        if self.closed:
            return
        try:
            self.app.root.offline_pdf_busy = self.app.busy()
            native = getattr(self.app, "file_drop", None)
            active = bool(native and getattr(native, "_drag_active", False))
            x, y = self.app.root.winfo_pointerxy()
            left, top = self.app.root.winfo_rootx(), self.app.root.winfo_rooty()
            self.pointer_inside = (
                left <= x < left + self.app.root.winfo_width()
                and top <= y < top + self.app.root.winfo_height()
            )
            self.update_hover(active)
        except tk.TclError:
            pass
        finally:
            if not self.closed:
                self.timer = self.app.root.after(50, self.poll)

    def close(self):
        self.closed = True
        if self.timer:
            self.app.root.after_cancel(self.timer)
        self.notice.destroy()
