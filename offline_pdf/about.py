"""About dialog: version, AGPL notices and where the licenses and sources are.

AGPL-3.0 section 5(d) asks interactive programs to show "Appropriate Legal
Notices": a copyright notice, that there is no warranty, and how to view the
license. The files it points to are copied next to the executable by the build.
"""

import os
import subprocess
import sys
from pathlib import Path

import customtkinter as ctk

from . import __version__, theme
from . import ctk_widgets as ttk

# Replace with the copyright holder (for example the organization) before release.
COPYRIGHT = "Copyright © 2026 OfflinePDF 개발자"

NOTICE = (
    "이 프로그램은 자유 소프트웨어입니다. GNU Affero 일반 공중 사용 허가서 3판(AGPL-3.0)에 "
    "따라 재배포하거나 수정할 수 있습니다."
)
WARRANTY = (
    "이 프로그램은 유용하게 쓰이기를 바라며 배포되지만, 상품성이나 특정 목적 적합성에 대한 "
    "묵시적 보증을 포함한 어떠한 보증도 제공하지 않습니다. 자세한 내용은 라이선스 전문을 "
    "확인하세요."
)
SOURCES = (
    "함께 사용한 오픈소스 구성요소의 저작권과 라이선스는 '오픈소스 고지'와 licenses 폴더에, "
    "프로그램과 구성요소의 소스 코드는 프로그램 폴더의 CorrespondingSource.zip과 "
    "dependency-sources 폴더에 있습니다."
)


def program_folder():
    """The folder that holds OfflinePDF.exe, or the source tree when not built."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def open_path(path):
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def show_about(app):
    if getattr(app, "about_dialog", None) and app.about_dialog.winfo_exists():
        app.about_dialog.lift()
        return app.about_dialog
    dialog = ctk.CTkToplevel(app.root)
    app.about_dialog = dialog
    dialog.title("OfflinePDF 정보")
    dialog.resizable(False, False)
    dialog.transient(app.root)
    body = ttk.Frame(dialog)
    body.pack(fill="both", expand=True, padx=24, pady=22)
    ttk.Label(body, text="OfflinePDF", font=(theme.BOLD_FAMILY, 20, "bold")).pack(anchor="w")
    ttk.Label(body, text=f"버전 {__version__}", style="Muted.TLabel").pack(anchor="w")
    ttk.Label(body, text=COPYRIGHT).pack(anchor="w", pady=(10, 0))
    for text in (NOTICE, WARRANTY, SOURCES):
        ttk.Label(body, text=text, wraplength=460, justify="left").pack(
            anchor="w", fill="x", pady=(10, 0)
        )
    folder = program_folder()
    links = ttk.Frame(body)
    links.pack(fill="x", pady=(18, 0))
    dialog.links = {}
    for label, target in (
        ("라이선스 전문", folder / "LICENSE"),
        ("오픈소스 고지", folder / "THIRD_PARTY_NOTICES.md"),
        ("소스 코드 폴더", folder),
    ):
        button = ttk.Button(
            links,
            text=label,
            width=13,
            command=lambda target=target: open_path(target),
            state="normal" if target.exists() else "disabled",
        )
        button.pack(side="left", padx=(0, 6))
        dialog.links[label] = target
    ttk.Button(links, text="닫기", command=dialog.destroy, style="Run.TButton", width=8).pack(
        side="right"
    )
    dialog.bind("<Escape>", lambda e: dialog.destroy())
    dialog.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - dialog.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    return dialog
