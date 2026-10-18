"""Session-only per-file credentials and on-demand modal prompts."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .engine import UserError, open_pdf
from .ui import FONT, RED


def fingerprint(path):
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns


def ask_password(app, path=None, *, output=False, explanation=""):
    result = None
    dialog = tk.Toplevel(app.root)
    dialog.title("결과 PDF 암호 설정" if output else "PDF 암호 입력")
    dialog.transient(app.root)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=24)
    body.pack(fill="both", expand=True)
    ttk.Label(
        body, text="결과 PDF 암호 설정" if output else "PDF 암호 입력", font=(FONT, 13, "bold")
    ).pack(anchor="w")
    ttk.Label(
        body,
        text=explanation
        or ("새 암호를 입력하세요." if output else "이 문서를 열려면 암호가 필요합니다."),
        wraplength=350,
    ).pack(anchor="w", pady=(8, 10))
    if path:
        ttk.Label(body, text=Path(path).name, wraplength=350).pack(anchor="w", pady=(0, 10))
    var = tk.StringVar()
    confirm = tk.StringVar()
    show = tk.BooleanVar()
    entry = ttk.Entry(body, textvariable=var, show="●", width=38)
    entry.pack(fill="x")
    entries = [entry]
    if output:
        ttk.Label(body, text="암호 다시 입력").pack(anchor="w", pady=(10, 3))
        second = ttk.Entry(body, textvariable=confirm, show="●")
        second.pack(fill="x")
        entries.append(second)

    def reveal():
        for item in entries:
            item.config(show="" if show.get() else "●")

    ttk.Checkbutton(body, text="암호 표시", variable=show, command=reveal).pack(anchor="w", pady=8)
    error = ttk.Label(body, text="", foreground=RED, wraplength=350)
    error.pack(anchor="w")
    if not output:
        ttk.Label(
            body, text="파일 제거·프로그램 종료 시 입력한 암호를 잊습니다.", wraplength=350
        ).pack(anchor="w", pady=(5, 8))
    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(10, 0))

    def close():
        var.set("")
        confirm.set("")
        dialog.destroy()

    def submit(*_):
        nonlocal result
        password = var.get()
        try:
            if not password:
                raise UserError("암호를 입력해 주세요.")
            if output:
                if len(password) > 40:
                    raise UserError("저장 암호는 40자 이하로 입력하세요.")
                if password != confirm.get():
                    raise UserError("두 암호가 다릅니다.")
            else:
                doc, _ = open_pdf(
                    path, password, extraction=app.tool in ("text", "pdf_images", "ocr")
                )
                try:
                    if app.tool == "unlock" and not doc.authenticate(password) & 4:
                        raise UserError("암호 해제에는 소유자 암호가 필요합니다.")
                finally:
                    doc.close()
            result = password
            close()
        except UserError as exc:
            error.config(text=str(exc))
            entry.focus_set()
            entry.selection_range(0, "end")

    ttk.Button(actions, text="취소", command=close).pack(side="right")
    ttk.Button(
        actions, text="암호 설정" if output else "문서 열기", command=submit, style="Run.TButton"
    ).pack(side="right", padx=8)
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Return>", submit)
    dialog.bind("<Escape>", lambda e: close())
    dialog.update_idletasks()
    x = app.root.winfo_rootx() + max(0, (app.root.winfo_width() - dialog.winfo_reqwidth()) // 2)
    y = app.root.winfo_rooty() + max(0, (app.root.winfo_height() - dialog.winfo_reqheight()) // 2)
    dialog.geometry(f"+{x}+{y}")
    dialog.grab_set()
    entry.focus_set()
    app.root.wait_window(dialog)
    return result


def cached_password(app, path):
    if not path:
        return ""
    record = app.password_cache.get(str(path))
    if record:
        try:
            if record[0] == fingerprint(path):
                return record[1]
        except OSError:
            pass
        app.password_cache.pop(str(path), None)
    return ""


def ensure_password(app, path):
    if not path or Path(path).suffix.lower() != ".pdf":
        return True
    try:
        with __import__("pymupdf").open(path) as probe:
            encrypted = probe.needs_pass or bool((probe.metadata or {}).get("encryption"))
        if not encrypted:
            return True
        password = cached_password(app, path)
        if password:
            try:
                doc, _ = open_pdf(
                    path, password, extraction=app.tool in ("text", "pdf_images", "ocr")
                )
                try:
                    valid = app.tool != "unlock" or bool(doc.authenticate(password) & 4)
                finally:
                    doc.close()
                if valid:
                    return True
            except UserError:
                pass
        password = ask_password(app, path)
        if password is None:
            return False
        app.password_cache[str(path)] = (fingerprint(path), password)
        app.metadata_cache.clear()
        return True
    except (RuntimeError, OSError):
        return True  # Normal file validation reports damage.
