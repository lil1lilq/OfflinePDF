"""Tool selection, history and result chaining."""

from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from ..engine import UserError, check_local_path
from ..images import IMAGE_EXTENSIONS
from ..passwords import fingerprint
from ..tools import TOOLS
from ..ui import CARD_TEXT, POPULAR


class NavigationController:
    """Tool selection, history and result chaining."""

    def arrange_cards(self, width, force=False):
        width = max(160, width)
        columns = max(1, min(6, int(width / (195 if self.show_all_tools else 230))))
        available = max(200, self.home.canvas.winfo_height() - 170)
        keys = (
            list(POPULAR) + [key for key in CARD_TEXT if key not in POPULAR]
            if self.show_all_tools
            else list(POPULAR)
        )
        if self.show_all_tools:
            while (
                columns < 6
                and ((len(keys) + columns - 1) // columns) * 66 > available
                and width / (columns + 1) >= 170
            ):
                columns += 1
            rows = (len(keys) + columns - 1) // columns
            height = max(46, min(68, int(available / rows) - 6))
        else:
            height = 142
        layout = (columns, height, self.show_all_tools)
        if layout == self.card_layout and not force:
            return
        self.card_layout = layout
        self.card_columns = columns
        for card in self.cards.values():
            card.grid_forget()
        for col in range(6):
            self.cards_frame.columnconfigure(
                col,
                weight=1 if col < columns else 0,
                uniform="cards" if col < columns else "",
                minsize=0,
            )
        for index, key in enumerate(keys):
            self.cards[key].set_compact(self.show_all_tools, height)
            self.cards[key].grid(
                row=index // columns,
                column=index % columns,
                sticky="ew",
                padx=4,
                pady=(0, 6 if self.show_all_tools else 12),
            )

    def schedule_cards(self):
        if self.card_resize_timer:
            self.root.after_cancel(self.card_resize_timer)

        def resize():
            self.card_resize_timer = None
            if self.home.winfo_ismapped():
                self.arrange_cards(self.cards_frame.winfo_width())

        self.card_resize_timer = self.root.after(50, resize)

    def toggle_tools(self):
        self.show_all_tools = not self.show_all_tools
        self.all_tools_button.config(
            text="기본 카드로 보기  ⌃" if self.show_all_tools else "전체 도구 보기  ⌄"
        )
        self.home_section.config(text="전체 도구" if self.show_all_tools else "자주 쓰는 도구")
        self.arrange_cards(self.cards_frame.winfo_width(), force=True)

    def select_tool(self, key):
        if self.busy() or key not in TOOLS:
            return
        self.close_ai_comparison()
        pending = self.pending_results
        if pending is not None:
            if key not in self.result_input_tools(pending):
                return
            try:
                for path in pending:
                    if not check_local_path(path).is_file():
                        raise UserError("결과 파일을 찾을 수 없습니다. 저장 폴더를 확인하세요.")
            except (UserError, OSError, RuntimeError) as exc:
                messagebox.showinfo("결과 파일 확인", str(exc), parent=self.root)
                return
            # Replace the inputs, never append results to the original sources.
            self.files = list(pending)
            self.regions = {}
            for path in pending:
                if self.result_passwords.get(path):
                    self.password_cache[path] = (fingerprint(path), self.result_passwords[path])
            self.save_mode.set("지정한 폴더")
            self.output.set(self.result_output)
            self.cancel_continue()
        previous = self.tool
        self.tool = key
        self.preview_origin = None
        self.screen = "work"
        if previous != key:
            self.organizer.close_document()
            self.organizer_preview_uid = None
        if previous != key:
            self.regions = {}
        self.home.pack_forget()
        self.work.pack(fill="both", expand=True)
        self.configure_form()
        self.sync_list()
        self.update_activity()
        if pending is not None:
            self.sync_list()
            self.status.set(
                f"이전 작업 결과 {len(self.files)}개를 가져왔습니다. 설정을 확인하고 실행하세요."
            )
        self.root.after_idle(lambda: self.refresh_preview(reset=True))

    def show_home(self):
        if self.busy():
            return
        self.cancel_continue()
        self.work.pack_forget()
        self.home.pack(fill="both", expand=True)
        self.schedule_cards()
        self.screen = "home"
        self.update_back_state()

    def update_back_state(self):
        enabled = not self.busy() and (self.screen != "home" or self.pending_results is not None)
        self.home_button.config(state="normal" if enabled else "disabled")
        self.task_title_row.pack_forget() if self.screen == "home" else self.task_title_row.pack(
            fill="x"
        )

    def go_back(self):
        if self.busy():
            return
        if self.screen == "comparison":
            self.close_ai_comparison()
            return
        if self.pending_results is not None:
            self.cancel_continue()
            self.home.pack_forget()
            self.work.pack(fill="both", expand=True)
            self.screen = self.chain_return_screen
            self.update_back_state()
            return
        if self.screen == "preview":
            self.hide_preview()
        elif self.screen == "work":
            self.show_home()

    def capture_preview_origin(self):
        organizer = self.organizer
        return {
            "selected_paths": [
                self.files[i] for i in self.file_list.curselection() if i < len(self.files)
            ],
            "file_y": self.file_list.yview()[0],
            "page": self.page_index,
            "organizer_uid": self.organizer_preview_uid,
            "organizer_y": organizer.canvas.yview()[0],
            "organizer_model": organizer.model,
            "organizer_path": organizer.path,
            "organizer_fingerprint": organizer.fingerprint,
            "overview_y": self.overview_canvas.yview()[0],
        }

    @staticmethod
    def result_input_tools(paths):
        if not paths:
            return set()
        extensions = {Path(path).suffix.lower() for path in paths}
        if extensions <= IMAGE_EXTENSIONS | {".pdf"}:
            return set(TOOLS)
        return set()

    def cancel_continue(self):
        had_pending = self.pending_results is not None
        self.pending_results = None
        self.home_title.config(text="어떤 작업을 할까요?")
        self.home_description.config(text="왼쪽에서 파일을 확인하고 필요한 도구를 선택하세요.")
        self.chain_cancel_button.pack_forget()
        for card in self.cards.values():
            card.set_enabled(True)
        if had_pending:
            self.sync_list()
        self.update_back_state()

    def continue_with_result(self):
        if self.busy() or not self.result_files:
            return
        allowed = self.result_input_tools(self.result_files)
        if not allowed:
            messagebox.showinfo(
                "다음 작업", "이 결과 형식으로 이어서 할 수 있는 작업이 없습니다.", parent=self.root
            )
            return
        self.chain_return_screen = self.screen
        self.show_home()
        self.pending_results = tuple(self.result_files)
        self.home_title.config(text="다음 작업을 선택하세요")
        title = CARD_TEXT[self.result_tool][0] if self.result_tool else "이전 작업"
        self.home_description.config(
            text=f"{title} 결과 {len(self.pending_results)}개를 다음 작업에 사용합니다."
        )
        self.file_list.set_files(self.pending_results, self.file_metadata)
        self.file_count.config(text=f"작업 결과  {len(self.pending_results)}개")
        self.sidebar_total.set(f"이전 작업 결과 {len(self.pending_results)}개")
        self.feedback.file_added(range(len(self.pending_results)))
        self.chain_cancel_button.pack(anchor="w", pady=(0, 12), before=self.home_section.master)
        for key, card in self.cards.items():
            card.set_enabled(key in allowed)
        # Image results have just one compatible tool; reveal it immediately.
        if "images_pdf" in allowed and not self.show_all_tools:
            self.toggle_tools()
        self.home.canvas.yview_moveto(0)
        self.update_back_state()

    def remember_result(self, folder):
        self.result_folder = folder
        try:
            directory = check_local_path(folder)
            self.result_files = tuple(
                str(path)
                for path in sorted(directory.iterdir())
                if path.is_file() and not path.is_symlink()
            )
        except (UserError, OSError, RuntimeError):
            self.result_files = ()
        self.next_button.config(
            state="normal" if self.result_input_tools(self.result_files) else "disabled"
        )
        self.update_activity()

    def update_activity(self):
        if self.busy():
            self.cancel_button.pack(side="right", padx=8)
            self.progress.pack(fill="x", pady=(8, 0))
            self.result_actions.pack_forget()
        else:
            self.cancel_button.pack_forget()
            self.progress.pack_forget()
            if self.result_files and self.result_tool == self.tool:
                self.result_actions.pack(fill="x", pady=(7, 0))
            else:
                self.result_actions.pack_forget()
