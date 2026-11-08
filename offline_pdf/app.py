"""Application session and lifecycle. GUI behavior lives in controllers/."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .controllers.files import FileController
from .controllers.forms import FormController
from .controllers.jobs import JobController
from .controllers.navigation import NavigationController
from .controllers.preview import PreviewController
from .engine import disable_network
from .theme import avoid_native_titlebar_updates
from .tools import TOOLS
from .windows_drop import NativeFileDrop

avoid_native_titlebar_updates()  # Called before either application or test creates a CTk root.


class App(NavigationController, FileController, FormController, PreviewController, JobController):
    def __init__(self, root):
        from .appearance import apply_theme
        from .localization import apply_language, install
        from .preferences import load_preferences

        install()
        self.preferences = load_preferences()
        apply_language(root, self.preferences["language"])
        self.root = root
        self.files = []
        self.regions = {}
        self.tool = "merge"
        self.page_index = 0
        self.preview_scale = 1
        self.preview_rect = None
        self.preview_photo = None
        self.process = None
        self.events = None
        self.cancel = None
        self.cancel_at = None
        self.stage = None
        self.result_folder = None
        self.drag_start = None
        self.drag_id = None
        self.options = {}
        self.result_files = ()
        self.result_output = None
        self.result_tool = None
        self.pending_results = None
        self.preview_mode = "width"
        self.preview_zoom = 1.0
        self.organizer_preview_uid = None
        self.metadata_cache = {}
        self.split_updating = False
        self.password_cache = {}
        self.result_passwords = {}
        self.job_passwords = {}
        self.preview_job = False
        self.comparison_folder = None
        self.screen = "home"
        self.preview_origin = None
        self.chain_return_screen = "work"
        from .layout import build

        build(self)
        apply_theme(root, self.preferences["theme"])
        for card in self.cards.values():
            card.paint()
        self.file_drop = None
        try:
            self.file_drop = NativeFileDrop(
                root,
                self.on_files_drop,
                (
                    self.host,
                    self.sidebar,
                    self.home.canvas,
                    self.cards_frame,
                    *self.cards.values(),
                    self.file_list,
                    self.canvas,
                    self.add_button,
                    self.organizer.canvas,
                ),
            )
        except (OSError, AttributeError):
            self.status.set("파일 추가 버튼으로 PDF·이미지를 선택하세요.")
        root.protocol("WM_DELETE_WINDOW", self.close)
        for key, card in self.cards.items():
            card.tooltip.text = TOOLS[key][1]
        self.configure_form()
        root.after(150, self.poll)
        self.update_back_state()

    def busy(self):
        return self.process is not None

    def close(self):
        if self.process:
            if not messagebox.askokcancel(
                "종료", "실행 중인 작업을 취소하고 종료하시겠습니까?", parent=self.root
            ):
                return
            self.cancel.set()
            self.process.join(timeout=0.5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
            self.cleanup_stage()
        self.close_ai_comparison()
        if self.file_drop:
            self.file_drop.close()
        self.feedback.close()
        self.file_list.close()
        self.window_drop_hover.close()
        if self.card_resize_timer:
            self.root.after_cancel(self.card_resize_timer)
        self.organizer.close_document()
        if self.preview_timer:
            try:
                self.root.after_cancel(self.preview_timer)
            except tk.TclError:
                pass
        self.password_cache.clear()
        self.result_passwords.clear()
        self.job_passwords.clear()
        # Cancel every queued UI callback before destroying its Tcl commands.
        for timer in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", timer)
        self.root.destroy()


def main():
    disable_network()
    from .theme import register_fonts

    register_fonts()
    root = ctk.CTk()
    App(root)
    root.mainloop()
