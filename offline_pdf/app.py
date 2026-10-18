"""Application session and lifecycle. GUI behavior lives in controllers/."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from . import __version__
from .controllers.files import FileController
from .controllers.forms import FormController
from .controllers.jobs import JobController
from .controllers.navigation import NavigationController
from .controllers.preview import PreviewController
from .engine import disable_network
from .tools import TOOLS
from .windows_drop import NativeFileDrop


class App(NavigationController, FileController, FormController, PreviewController, JobController):
    def __init__(self, root):
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
        self.converted_count = 0
        self.screen = "home"
        self.preview_origin = None
        self.chain_return_screen = "work"
        from .layout import build

        build(self)
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
        self.root.destroy()

    def help(self):
        messagebox.showinfo(
            "사용 안내",
            "① 작업 선택 → ② 파일 추가 → ③ 설정 → ④ 실행\n\n"
            "Windows 탐색기에서 파일을 창 안으로 끌어놓아 추가할 수 있습니다.\n"
            "여러 파일을 한 번에 추가할 수 있으며 중복은 제외합니다.\n"
            "왼쪽 사이드바에서 파일을 확인할 수 있으며 도구를 바꿔도 파일은 유지됩니다.\n"
            "전체 도구 보기는 간략 카드로 전환하며 창 크기에 맞춰 정렬됩니다.\n"
            "N개 나누기: 다음 파일의 시작 쪽을 쉼표로 구분합니다. 예: 5,8\n"
            "페이지 공란은 전체 페이지입니다. 예: 1-3,5 / 역순: 3-1\n"
            "합치기는 목록 순서입니다. 파일을 선택하고 위로·아래로 이동하세요.\n"
            "결과는 선택한 폴더 안에 새 PDF결과 폴더로 저장됩니다.\n"
            "완료 후 “결과로 다음 작업”을 누르면 결과 파일로 다른 작업을 이어갑니다.\n"
            "기존 파일을 덮어쓰지 않으며 실패한 작업 결과는 정리합니다.\n\n"
            "영구 삭제: 미리보기에서 드래그 → 실행 → 결과를 검색·복사·추출해 확인\n"
            "OCR: 배포 담당자가 준비한 kor/eng.traineddata 폴더를 선택\n"
            "Word·Excel·PPT·HWP·PDF/A 변환은 이 버전에 포함하지 않습니다.\n\n"
            "외부 통신·자동 업데이트·사용기록 수집이 없습니다.\n"
            "OneDrive 등 자동 동기화 폴더는 저장 위치로 사용하지 마세요.\n"
            "강제 전원 종료 후 .offline-pdf- 임시폴더가 남으면 직접 삭제하세요.\n\n"
            f"버전 {__version__} · AGPL-3.0-or-later · PyMuPDF / Python Tkinter",
            parent=self.root,
        )


def main():
    disable_network()
    root = tk.Tk()
    App(root)
    root.mainloop()
