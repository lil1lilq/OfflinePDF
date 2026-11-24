"""Import-time recovery prompt and cancellable, isolated structure validation."""

import multiprocessing as mp
import queue
import tempfile
from pathlib import Path

import customtkinter as ctk

from . import ctk_widgets as ttk
from .dialogs import dialog_parent, filedialog, messagebox, place_dialog
from .engine import UserError, check_local_path
from .repair import REPAIR_FAILED, needs_repair, publish_repaired, repair_worker


def _run_repair(parent, source, destination):
    """Keep parsing off Tk's thread and clean staging even on native worker failure."""
    owner = dialog_parent(parent)
    context = mp.get_context("spawn")
    events, cancel = context.Queue(), context.Event()
    result = None
    timer = None
    dialog = ctk.CTkToplevel(owner)
    dialog.title("PDF 구조 복구")
    dialog.transient(owner)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog)
    body.pack(fill="both", expand=True, padx=24, pady=20)
    ttk.Label(
        body, text="PDF 구조를 복구하고 모든 페이지를 확인하고 있습니다…", wraplength=400
    ).pack()
    progress = ctk.CTkProgressBar(body, mode="indeterminate")
    progress.pack(fill="x", pady=16)
    progress.start()

    def stop():
        cancel.set()
        dialog.destroy()

    ttk.Button(body, text="취소", command=stop).pack(anchor="e")
    dialog.protocol("WM_DELETE_WINDOW", stop)
    dialog.bind("<Escape>", lambda event: stop())
    place_dialog(dialog, owner)
    previous = owner.grab_current()
    dialog.grab_set()
    process = None
    try:
        with tempfile.TemporaryDirectory(
            prefix=".offlinepdf-recovery-", dir=destination.parent
        ) as folder:
            staged = Path(folder) / "repaired.pdf"
            process = context.Process(
                target=repair_worker, args=(str(source), str(staged), events, cancel)
            )

            def poll():
                nonlocal result, timer
                timer = None
                try:
                    result = events.get_nowait()
                except queue.Empty:
                    if process.is_alive():
                        timer = dialog.after(80, poll)
                        return
                    # Queue feeder can flush immediately after is_alive changes.
                    try:
                        result = events.get(timeout=0.1)
                    except queue.Empty:
                        result = ("error", REPAIR_FAILED)
                dialog.destroy()

            try:
                process.start()
                timer = dialog.after(80, poll)
                owner.wait_window(dialog)
            finally:
                if timer is not None:
                    owner.after_cancel(timer)
                cancel.set()
                if process.pid is not None:
                    process.join(timeout=0.2)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=2)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=2)
                if dialog.winfo_exists():
                    dialog.destroy()
            if result is None or result[0] == "cancelled":
                return None
            if result[0] != "done":
                raise UserError(result[1])
            return publish_repaired(staged, destination)
    finally:
        progress.stop()
        if dialog.winfo_exists():
            dialog.destroy()
        events.close()
        events.join_thread()
        if previous is not None and previous.winfo_exists():
            previous.grab_set()


def prepare_pdf_import(app, path):
    """Return the original or verified recovery copy; None means skip this input."""
    try:
        if not needs_repair(path):
            return path
        app._repairing = True
        if not messagebox.askyesno(
            "PDF 구조 복구",
            f"{Path(path).name}\n\nPDF 구조에 문제가 있습니다. 복구본을 만들어 열까요?\n"
            "원본은 보존하며, 모든 페이지를 확인한 뒤 별도 파일로 저장합니다.\n"
            "암호화 정보 오류와 전자서명 문서는 복구하지 않습니다.",
            parent=app.root,
        ):
            return None
        target = filedialog.asksaveasfilename(
            parent=app.root,
            title="복구 PDF 저장",
            initialdir=str(Path(path).parent),
            initialfile=f"{Path(path).stem}_복구.pdf",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            confirmoverwrite=False,
        )
        if not target:
            return None
        destination = check_local_path(target)
        if destination == Path(path) or destination.exists():
            raise UserError("이미 있는 파일은 덮어쓰지 않습니다. 다른 파일명을 선택하세요.")
        result = _run_repair(app.root, path, destination)
        if result:
            messagebox.showinfo(
                "PDF 구조 복구",
                "복구본을 저장했습니다. 원본은 보존했습니다. 복구본의 내용을 확인하세요.",
                parent=app.root,
            )
        return result
    except UserError as exc:
        messagebox.showerror("PDF 구조 복구", str(exc), parent=app.root)
    except OSError:
        messagebox.showerror(
            "PDF 구조 복구",
            "파일을 읽거나 저장할 수 없습니다. 파일 위치와 읽기·쓰기 권한을 확인하세요.",
            parent=app.root,
        )
    except Exception:
        messagebox.showerror("PDF 구조 복구", REPAIR_FAILED, parent=app.root)
    finally:
        app._repairing = False
    return None
