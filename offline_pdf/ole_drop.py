"""Windows IDropTarget bridge. COM callbacks only enqueue Python data, never Tk calls.

Microsoft IDropTarget, FORMATETC, STGMEDIUM and RegisterDragDrop contracts.
"""

import ctypes as c
import uuid


class OleDrop:
    def __init__(self, owner):
        from ctypes import wintypes as w

        self.owner = owner
        self.handles = set()
        self.closed = False
        self.refs = 1
        self.accepted = False
        self.allowed = True
        self.ole = c.OleDLL("ole32")
        self.ole.OleInitialize.argtypes = [c.c_void_p]
        self.ole.OleInitialize.restype = c.c_long
        hr = self.ole.OleInitialize(None)
        if hr not in (0, 1):
            raise OSError("OLE initialization unavailable")
        self.initialized = True
        HRESULT, ULONG, PTR = c.c_long, w.ULONG, c.c_void_p

        class Point(c.Structure):
            _fields_ = [("x", w.LONG), ("y", w.LONG)]

        class Format(c.Structure):
            _fields_ = [
                ("cfFormat", w.WORD),
                ("ptd", PTR),
                ("dwAspect", w.DWORD),
                ("lindex", w.LONG),
                ("tymed", w.DWORD),
            ]

        class Medium(c.Structure):
            _fields_ = [("tymed", w.DWORD), ("handle", PTR), ("pUnkForRelease", PTR)]

        self.format = Format(15, None, 1, -1, 1)  # CF_HDROP / CONTENT / HGLOBAL
        self.Medium = Medium
        self.ole.ReleaseStgMedium.argtypes = [c.POINTER(Medium)]
        self.ole.ReleaseStgMedium.restype = None
        qi = c.WINFUNCTYPE(HRESULT, PTR, PTR, c.POINTER(PTR))
        ref = c.WINFUNCTYPE(ULONG, PTR)
        enter = c.WINFUNCTYPE(HRESULT, PTR, PTR, w.DWORD, Point, c.POINTER(w.DWORD))
        over = c.WINFUNCTYPE(HRESULT, PTR, w.DWORD, Point, c.POINTER(w.DWORD))
        leave = c.WINFUNCTYPE(HRESULT, PTR)
        self.query_data = c.WINFUNCTYPE(HRESULT, PTR, c.POINTER(Format))
        self.get_data = c.WINFUNCTYPE(HRESULT, PTR, c.POINTER(Format), c.POINTER(Medium))
        self.accept_iids = {
            uuid.UUID(s).bytes_le
            for s in (
                "00000000-0000-0000-C000-000000000046",
                "00000122-0000-0000-C000-000000000046",
            )
        }

        def query(this, iid, out):
            out[0] = None
            if c.string_at(iid, 16) not in self.accept_iids:
                return -2147467262  # E_NOINTERFACE
            out[0] = c.addressof(self.interface)
            self.refs += 1
            return 0

        def addref(this):
            self.refs += 1
            return self.refs

        def release(this):
            self.refs = max(0, self.refs - 1)
            return self.refs

        def drag_enter(this, data, keys, point, effect):
            try:
                self.accepted = not self.closed and self.allowed and self.can_read(data)
                effect[0] = 1 if self.accepted and effect[0] & 1 else 0
                self.owner._drag_active = bool(effect[0])
            except Exception:
                effect[0] = 0
                self.owner._drag_active = False
            return 0

        def drag_over(this, keys, point, effect):
            effect[0] = (
                1 if self.accepted and self.allowed and effect[0] & 1 and not self.closed else 0
            )
            self.owner._drag_active = bool(effect[0])
            return 0

        def drag_leave(this):
            self.accepted = False
            self.owner._drag_active = False
            return 0

        def drop(this, data, keys, point, effect):
            try:
                effect[0] = 0
                if not self.closed and self.allowed and self.accepted:
                    medium = Medium()
                    method = self.get_data(self.method(data, 3))
                    if method(data, c.byref(self.format), c.byref(medium)) == 0:
                        try:
                            from .windows_drop import read_drop_paths

                            if medium.tymed == 1 and medium.handle:
                                paths = read_drop_paths(self.owner._shell, medium.handle)
                                if paths:
                                    self.owner._queue_files(paths)
                                    effect[0] = 1
                        finally:
                            self.ole.ReleaseStgMedium(c.byref(medium))
            except Exception:
                effect[0] = 0
            self.accepted = False
            self.owner._drag_active = False
            return 0

        self.callbacks = [
            qi(query),
            ref(addref),
            ref(release),
            enter(drag_enter),
            over(drag_over),
            leave(drag_leave),
            enter(drop),
        ]
        self.vtable = (PTR * 7)(*[c.cast(cb, PTR).value for cb in self.callbacks])

        class Interface(c.Structure):
            _fields_ = [("vtable", c.POINTER(PTR))]

        self.interface = Interface(self.vtable)
        self.ole.RegisterDragDrop.argtypes = [w.HWND, PTR]
        self.ole.RegisterDragDrop.restype = HRESULT
        self.ole.RevokeDragDrop.argtypes = [w.HWND]
        self.ole.RevokeDragDrop.restype = HRESULT

    @staticmethod
    def method(data, index):
        return c.cast(data, c.POINTER(c.POINTER(c.c_void_p))).contents[index]

    def can_read(self, data):
        return bool(data) and self.query_data(self.method(data, 5))(data, c.byref(self.format)) == 0

    def register(self, hwnd):
        if hwnd and hwnd not in self.handles:
            # OleDLL raises on failure; leave existing owners' registrations intact.
            if self.ole.RegisterDragDrop(hwnd, c.byref(self.interface)) == 0:
                self.handles.add(hwnd)
                self.owner._shell.DragAcceptFiles(hwnd, False)

    def unregister(self, hwnd):
        if hwnd in self.handles:
            try:
                self.ole.RevokeDragDrop(hwnd)
            except OSError:
                pass
            self.handles.discard(hwnd)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.owner._drag_active = False
        for hwnd in tuple(self.handles):
            self.unregister(hwnd)
        self.handles.clear()
        if self.initialized:
            self.ole.OleUninitialize()
            self.initialized = False
