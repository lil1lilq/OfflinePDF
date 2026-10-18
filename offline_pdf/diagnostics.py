"""Explicit build diagnostics. Normal GUI startup never makes a network probe.

Self-test documents contain synthetic data and are deleted on completion.
The native TCP probe is used only to validate Windows firewall enforcement.
"""

import ctypes
import json
import multiprocessing as mp
import queue
import tempfile
import time
from pathlib import Path


def native_tcp_probe(address="1.1.1.1", port=443):
    """Use Winsock directly so the Python socket guard cannot fake a block."""
    from ctypes import wintypes as w

    class Address(ctypes.Structure):
        _fields_ = [
            ("family", ctypes.c_short),
            ("port", ctypes.c_ushort),
            ("ip", ctypes.c_ubyte * 4),
            ("padding", ctypes.c_ubyte * 8),
        ]

    class FDSet(ctypes.Structure):
        _fields_ = [("count", ctypes.c_uint), ("sockets", ctypes.c_size_t * 64)]

    class Timeval(ctypes.Structure):
        _fields_ = [("seconds", ctypes.c_long), ("microseconds", ctypes.c_long)]

    ws = ctypes.WinDLL("ws2_32", use_last_error=True)
    ws.WSAStartup.argtypes = [w.WORD, ctypes.c_void_p]
    ws.socket.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    ws.socket.restype = ctypes.c_size_t
    ws.connect.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
    ws.ioctlsocket.argtypes = [ctypes.c_size_t, ctypes.c_long, ctypes.POINTER(ctypes.c_ulong)]
    ws.select.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    ws.getsockopt.argtypes = [
        ctypes.c_size_t,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    ]
    ws.closesocket.argtypes = [ctypes.c_size_t]
    data = ctypes.create_string_buffer(512)
    if ws.WSAStartup(0x202, data):
        raise RuntimeError("Winsock initialization failed")
    handle = ws.socket(2, 1, 6)
    try:
        if handle == ctypes.c_size_t(-1).value:
            raise RuntimeError("Native socket creation failed")
        nonblocking = ctypes.c_ulong(1)
        if ws.ioctlsocket(handle, ctypes.c_long(0x8004667E), ctypes.byref(nonblocking)):
            raise RuntimeError("Native nonblocking setup failed")
        ip = [int(part) for part in address.split(".")]
        target = Address(
            2, int.from_bytes(port.to_bytes(2, "big"), "little"), (ctypes.c_ubyte * 4)(*ip)
        )
        code = ws.connect(handle, ctypes.byref(target), ctypes.sizeof(target))
        if code == 0:
            return {"connected": True, "error": 0}
        error = ws.WSAGetLastError()
        if error not in (10035, 10036):
            return {"connected": False, "error": error}
        write = FDSet()
        write.count = 1
        write.sockets[0] = handle
        exceptions = FDSet()
        exceptions.count = 1
        exceptions.sockets[0] = handle
        timeout = Timeval(5, 0)
        ready = ws.select(
            0, None, ctypes.byref(write), ctypes.byref(exceptions), ctypes.byref(timeout)
        )
        if ready <= 0:
            return {"connected": False, "error": 10060 if ready == 0 else ws.WSAGetLastError()}
        error = ctypes.c_int()
        size = ctypes.c_int(ctypes.sizeof(error))
        if ws.getsockopt(handle, 0xFFFF, 0x1007, ctypes.byref(error), ctypes.byref(size)):
            raise RuntimeError("Native connection status unavailable")
        return {"connected": error.value == 0, "error": error.value}
    finally:
        ws.closesocket(handle)
        ws.WSACleanup()


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
    import tkinter as tk

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
        assert list(run("upscale", [scan], scale="2").glob("*.pdf"))
        checks.append("onnx-cpu-model-worker")
        compare = run("upscale", [scan], scale="2", preview_only=True)
        assert (compare / "before.png").is_file() and (compare / "after.png").is_file()
        checks.append("ai-comparison")
        with Image.new("RGB", (24, 20), "red") as image:
            image.save(root / "사진.heic", format="HEIF")
        assert list(run("images_pdf", [root / "사진.heic"]).glob("*.pdf"))
        checks.append("heic-native-codec")
        # Exercise the bundled OCR engine on a synthetic page.
        tessdata = model_folder().parent / "tessdata"
        assert list(run("ocr", [source], language="eng", tessdata=str(tessdata)).glob("*.pdf"))
        checks.append("ocr-models-worker")
        window = tk.Tk()
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
        result = native_tcp_probe() if command == "--network-probe" else self_test()
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        path.write_text(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 1
