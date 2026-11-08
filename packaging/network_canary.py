"""BUILD VERIFICATION ONLY: a native TCP canary for the Windows firewall check.

It is never imported by the application and is not part of the executable.
verify_windows_build.ps1 runs it with the build Python to prove that the
firewall audit really records native connections before trusting the
application's zero-connection result. It sends nothing: TCP handshake only.

Usage: python packaging/network_canary.py REPORT.json
"""

import ctypes
import json
import sys
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


def main():
    report = Path(sys.argv[1])
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = native_tcp_probe()
    except Exception as exc:
        report.write_text(json.dumps({"ok": False, "error": str(exc)}), encoding="utf-8")
        return 1
    report.write_text(json.dumps(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
