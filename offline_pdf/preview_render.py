"""Bounded preview cache and process-isolated, viewport-only PDF rendering.

Every input updates the view immediately. Generations cancel obsolete raster
work, never wheel events. No Tk objects or document handles cross processes.
"""

from __future__ import annotations

import math
import multiprocessing as mp
import queue
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import pymupdf as pdf
from PIL import Image

BASE_PIXELS = 750_000


def visible_pixels(size, origin, viewport):
    width, height = size
    left = max(0, min(math.floor(origin[0] - 12), math.ceil(width) - 1))
    top = max(0, min(math.floor(origin[1] - 12), math.ceil(height) - 1))
    return (
        left,
        top,
        max(left + 1, min(math.ceil(width), left + max(1, viewport[0]))),
        max(top + 1, min(math.ceil(height), top + max(1, viewport[1]))),
    )


def raster_view(page, scale, pixels):
    clip = pdf.Rect(*(value / scale for value in pixels))
    pix = page.get_pixmap(
        matrix=pdf.Matrix(scale, scale), clip=clip, alpha=False, colorspace=pdf.csRGB
    )
    return pix.x, pix.y, pix.width, pix.height, pix.samples


@dataclass
class PreparedPage:
    token: int
    document: object
    base: object = None
    payload: bytes | None = None

    @property
    def page(self):
        return self.document[0]

    def thumbnail(self):
        if self.base is None:
            page = self.page
            scale = min(1.0, math.sqrt(BASE_PIXELS / (page.rect.width * page.rect.height)))
            pix = page.get_pixmap(
                matrix=pdf.Matrix(scale, scale), alpha=False, colorspace=pdf.csRGB
            )
            self.base = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return self.base

    def serialized(self):
        if self.payload is None:
            self.payload = self.document.tobytes()
        return self.payload

    def close(self):
        if self.base is not None:
            self.base.close()
        if not self.document.is_closed:
            self.document.close()


class PreviewCache:
    def __init__(self):
        self.source = None
        self.identity = None
        self.entries = OrderedDict()
        self.serial = 0

    def document(self, path, password):
        from .engine import open_pdf
        from .images import open_image_document

        location = Path(path)
        stat = location.stat()
        identity = (str(location.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ino, password)
        if identity != self.identity or self.source is None or self.source.is_closed:
            self.close()
            self.source = (
                open_pdf(path, password, extraction=True)[0]
                if location.suffix.lower() == ".pdf"
                else open_image_document(path)
            )
            self.identity = identity
        return self.source

    def prepared(self, index, angle=0, number_options=None, nup_options=None, selected=None):
        options = number_options if number_options is not None else nup_options
        key = (
            index,
            angle,
            "number"
            if number_options is not None
            else "nup"
            if nup_options is not None
            else "page",
            tuple(sorted(options.items())) if options is not None else (),
        )
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key]
        if nup_options is not None:
            from .nup import make_nup

            doc = make_nup(self.source, selected, nup_options, sheet=index)
        else:
            doc = pdf.open()
            try:
                doc.insert_pdf(self.source, from_page=index, to_page=index)
                if number_options is not None:
                    from .engine import pages
                    from .numbering import draw_number

                    chosen = pages(number_options.get("pages", ""), self.source.page_count)
                    if index in chosen:
                        draw_number(doc[0], chosen.index(index), number_options)
                page = doc[0]
                page.set_rotation((page.rotation + angle) % 360)
            except Exception:
                doc.close()
                raise
        self.serial += 1
        entry = PreparedPage(self.serial, doc)
        self.entries[key] = entry
        while len(self.entries) > 2:
            _, old = self.entries.popitem(last=False)
            old.close()
        return entry

    def close(self):
        for entry in self.entries.values():
            entry.close()
        self.entries.clear()
        if self.source is not None and not self.source.is_closed:
            self.source.close()
        self.source = None
        self.identity = None


def _deliver(results, generation, revision, raster):
    while revision == generation.value:
        try:
            results.put((revision, raster), timeout=0.05)
            return
        except queue.Full:
            try:
                results.get_nowait()
            except queue.Empty:
                pass


def _render_worker(requests, results, generation):
    from .engine import disable_network

    disable_network()
    document, token, display = None, None, None
    try:
        while True:
            task = requests.get()
            if task is None:
                return
            revision, page_token, payload, scale, pixels = task
            try:
                # Install page data even for cancelled work: later requests for
                # that page intentionally reuse the worker's document cache.
                if payload is not None:
                    display = None
                    if document is not None:
                        document.close()
                    pdf.TOOLS.store_shrink(100)
                    document = pdf.open(stream=payload, filetype="pdf")
                    token = page_token
                    display = document[0].get_displaylist()
                if revision != generation.value:
                    continue
                if token != page_token or document is None:
                    raise ValueError("Preview page cache unavailable")
                raster = raster_view(display, scale, pixels)
                _deliver(results, generation, revision, raster)
            except Exception:
                _deliver(results, generation, revision, None)
    finally:
        if document is not None:
            document.close()


class ViewportRenderer:
    def __init__(self):
        context = mp.get_context("spawn")
        self.generation = context.Value("q", 0)
        self.requests = context.Queue()
        self.results = context.Queue(maxsize=2)
        self.process = context.Process(
            target=_render_worker, args=(self.requests, self.results, self.generation), daemon=True
        )
        self.sent_token = None
        self.pending = False
        self.closed = False

    def invalidate(self):
        with self.generation.get_lock():
            self.generation.value += 1
        self.pending = False

    def submit(self, entry, scale, pixels):
        if self.closed:
            return
        if self.process.pid is None:
            self.process.start()
        self.invalidate()
        revision = self.generation.value
        payload = entry.serialized() if entry.token != self.sent_token else None
        self.requests.put((revision, entry.token, payload, scale, pixels))
        self.sent_token = entry.token
        self.pending = True
        return revision

    def poll(self):
        latest = None
        while True:
            try:
                revision, raster = self.results.get_nowait()
            except queue.Empty:
                break
            if revision == self.generation.value:
                self.pending = False
                latest = (revision, raster)
        if self.pending and self.process.pid is not None and not self.process.is_alive():
            self.pending = False
            latest = (self.generation.value, None)
        return latest

    def close(self):
        if self.closed:
            return
        self.invalidate()
        self.closed = True
        if self.process.pid is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
        for channel in (self.requests, self.results):
            channel.cancel_join_thread()
            channel.close()
