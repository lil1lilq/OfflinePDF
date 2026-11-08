"""Explicit build self-test. It makes no network connection.

Self-test documents contain synthetic data and are deleted on completion.
The firewall canary lives in packaging/network_canary.py and is not shipped.
"""

import json
import multiprocessing as mp
import queue
import tempfile
import time
from pathlib import Path


def worker_result(job):
    from .engine import worker

    context = mp.get_context("spawn")
    events = context.Queue()
    cancel = context.Event()
    process = context.Process(target=worker, args=(job, events, cancel))
    process.start()
    deadline = time.monotonic() + 90
    try:
        while time.monotonic() < deadline:
            try:
                event = events.get(timeout=0.2)
            except queue.Empty:
                continue
            if event["type"] == "done":
                return Path(event["folder"])
            if event["type"] == "error":
                raise RuntimeError(event["message"])
        raise RuntimeError("Frozen worker self-test timed out")
    finally:
        process.join(timeout=2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        events.close()


def self_test():
    """Exercise the frozen executable, child workers, native UI and AI/OCR."""
    import socket

    import pymupdf as pdf
    from PIL import Image

    from . import __version__
    from .app import TOOLS, App
    from .engine import disable_network
    from .enhance import model_folder

    disable_network()
    for call in (lambda: socket.socket(), lambda: socket.getaddrinfo("example.invalid", 443)):
        try:
            call()
        except PermissionError:
            pass
        else:
            raise AssertionError("Python network guard failed")
    checks = ["python-network-guard"]
    with tempfile.TemporaryDirectory(prefix="OfflinePDF-") as temp:
        root = Path(temp) / "한글 경로"
        root.mkdir()
        scan = root / "입력.png"
        with Image.new("RGB", (40, 32), "lightgray") as image:
            image.save(scan)
        source = root / "문서.pdf"
        with pdf.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 80), "SYNTHETIC SELF TEST")
            doc.save(source)

        def run(tool, files, **options):
            return worker_result(
                {
                    "tool": tool,
                    "files": [str(p) for p in files],
                    "output": str(root),
                    "options": options,
                }
            )

        merged = run("merge", [source, scan])
        merged_pdf = next(merged.glob("*.pdf"))
        with pdf.open(merged_pdf) as doc:
            assert len(doc) == 2 and "SYNTHETIC" in doc[0].get_text()
        checks.append("unicode-mixed-image-import-worker")
        for level in ("무손실", "권장"):
            assert list(run("compress", [merged_pdf], compression=level).glob("*.pdf"))
        checks.append("compression")
        imposed = run("nup", [merged_pdf], nup_count="2", nup_orientation="가로")
        with pdf.open(next(imposed.glob("*.pdf"))) as doc:
            assert len(doc) == 1 and tuple(doc[0].rect) == (0, 0, 842, 595)
            assert "SYNTHETIC" in doc[0].get_text()
        checks.append("a4-nup-worker")
        assert list(run("upscale", [scan], scale="2").glob("*.pdf"))
        checks.append("onnx-cpu-model-worker")
        compare = run("upscale", [scan], scale="2", preview_only=True)
        assert (compare / "before.png").is_file() and (compare / "after.png").is_file()
        checks.append("ai-comparison")
        with Image.new("RGB", (24, 20), "red") as image:
            image.save(root / "사진.webp", format="WEBP")
        assert list(run("images_pdf", [root / "사진.webp"]).glob("*.pdf"))
        checks.append("webp-native-codec")
        # Exercise the bundled OCR engine on a synthetic page.
        tessdata = model_folder().parent / "tessdata"
        assert list(run("ocr", [source], language="eng", tessdata=str(tessdata)).glob("*.pdf"))
        checks.append("ocr-models-worker")
        import customtkinter as ctk

        window = ctk.CTk()
        app = App(window)
        app.auto_open.set(False)
        try:
            window.geometry("900x650")
            window.update()
            assert str(app.home_button.cget("state")) == "disabled"
            for tool in TOOLS:
                app.select_tool(tool)
                window.update()
                assert app.run_button.winfo_ismapped()
            app.add_paths([str(source)])
            app.show_preview()
            window.update()
            app.go_back()
            assert app.screen == "work"
            checks.append("native-ui-tools-navigation")
        finally:
            app.close()
    return {"ok": True, "version": __version__, "checks": checks}


def run_diagnostic(command, report):
    """Write reports because Windows windowed executables have no stdout."""
    path = Path(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = self_test()
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        path.write_text(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1
