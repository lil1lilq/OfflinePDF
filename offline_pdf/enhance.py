"""CPU-only tiled inference. No model downloads and no document disk cache."""

import hashlib
import json
import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from .engine import UserError, check_cancel

MAX_OUTPUT_PIXELS = 40_000_000
# Output size relative to the scan. The model always enlarges 4x; smaller
# factors resize its result down, so "1" keeps the size and only sharpens.
SCALES = {"1": 1.0, "1.5": 1.5, "2": 2.0, "4": 4.0}
JPEG_QUALITY = 90


def output_scale(options):
    """The chosen factor; the advanced "4x" checkbox overrides the main choice."""
    if options.get("scale4") in (True, "1", "True", "true"):
        return 4.0
    value = str(options.get("scale", "1.5")).strip()
    if value not in SCALES:
        raise UserError("AI 보정 배율을 원본 크기·1.5배·2배·4배 중에서 선택하세요.")
    return SCALES[value]


def model_folder():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "models"


class Upscaler:
    def __init__(self):
        import onnxruntime as ort

        ort.disable_telemetry_events()
        folder = model_folder()
        path = folder / "realesr-general-x4v3.onnx"
        try:
            expected = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))["sha256"][
                path.name
            ]
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError()
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            self.session = ort.InferenceSession(
                str(path), options, providers=["CPUExecutionProvider"]
            )
        except Exception:
            raise UserError(
                "AI 모델을 불러오지 못했습니다. 배포파일을 다시 압축 해제하세요."
            ) from None

    def image(self, image, scale=2, cancel=None, progress=lambda value, total: None):
        import numpy as np

        if float(scale) not in SCALES.values():
            raise UserError("AI 보정 배율을 원본 크기·1.5배·2배·4배 중에서 선택하세요.")
        scale = float(scale)
        w, h = image.size
        # The model works tile by tile, so only the finished image's size matters.
        if w * h * scale * scale > MAX_OUTPUT_PIXELS:
            raise UserError(
                "AI 보정 결과가 너무 큽니다. 더 작은 배율을 선택하거나 이미지 해상도를 줄이세요."
            )

        def at(value):
            # Shared rounding keeps neighbouring tiles edge to edge at 1.5x.
            return round(value * scale)

        tile, pad = 128, 40
        result = Image.new("RGB", (at(w), at(h)))
        total = ((w + tile - 1) // tile) * ((h + tile - 1) // tile)
        done = 0
        try:
            for y in range(0, h, tile):
                for x in range(0, w, tile):
                    check_cancel(cancel)
                    x1, y1 = max(0, x - pad), max(0, y - pad)
                    x2, y2 = min(w, x + tile), min(h, y + tile)
                    with image.crop((x1, y1, min(w, x2 + pad), min(h, y2 + pad))) as crop:
                        array = np.asarray(crop, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
                        output = self.session.run(
                            ["output"], {"input": np.ascontiguousarray(array)}
                        )[0]
                    check_cancel(cancel)
                    output = np.clip(np.rint(output[0].transpose(1, 2, 0) * 255), 0, 255).astype(
                        np.uint8
                    )
                    with Image.fromarray(output) as enlarged:
                        region = enlarged.crop(
                            ((x - x1) * 4, (y - y1) * 4, (x2 - x1) * 4, (y2 - y1) * 4)
                        )
                    try:
                        if scale != 4:
                            reduced = region.resize(
                                (at(x2) - at(x), at(y2) - at(y)), Image.Resampling.LANCZOS
                            )
                            region.close()
                            region = reduced
                        result.paste(region, (at(x), at(y)))
                    finally:
                        region.close()
                    done += 1
                    progress(done, total)
            return result
        except BaseException:
            result.close()
            raise


def images_to_enhance(doc):
    """Use opaque embedded images; leave text, vectors, masks and forms intact."""
    found = {}
    for page in doc:
        for image in page.get_images(full=True):
            xref, mask, width, height, bits = image[:5]
            if xref > 0 and not mask and width >= 16 and height >= 16 and bits > 1:
                found.setdefault(xref, page.number)
    return found


def read_image(doc, xref, details=None):
    """Decode an embedded image as RGB; details gets its stored format and mode."""
    data = doc.extract_image(xref)
    if data["width"] * data["height"] > MAX_OUTPUT_PIXELS:
        raise UserError("이미지가 너무 큽니다. 작은 문서로 다시 시도하세요.")
    with Image.open(BytesIO(data["image"])) as image:
        if details is not None:
            details.update(ext=data.get("ext", ""), mode=image.mode)
        return image.convert("RGB")


def encode(image, details):
    """Store the result like its source: a JPEG scan stays JPEG, which keeps the
    file several times smaller than PNG at no visible cost; a lossless source
    (PNG, etc.) stays lossless. Grayscale sources stay grayscale."""
    stream = BytesIO()
    gray = details.get("mode") in ("L", "LA", "I", "I;16")
    out = image.convert("L") if gray else image
    try:
        if details.get("ext") in ("jpeg", "jpg"):
            out.save(stream, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        else:
            out.save(stream, format="PNG", optimize=True)
    finally:
        if out is not image:
            out.close()
    return stream.getvalue()


def enhance_pdf(doc, options, emit, cancel):
    scale = output_scale(options)
    found = images_to_enhance(doc)
    if not found:
        raise UserError(
            "보정할 스캔 이미지를 찾지 못했습니다. 텍스트·도형·투명·흑백 1비트 이미지는 보정하지 않습니다."
        )
    upscaler = Upscaler()
    for i, (xref, page_num) in enumerate(found.items()):
        check_cancel(cancel)
        details = {}
        with read_image(doc, xref, details) as original:

            def progress(value, total):
                emit(
                    {
                        "type": "progress",
                        "current": i + value / total,
                        "total": len(found),
                        "label": f"AI 이미지 {i + 1}/{len(found)} · 영역 {value}/{total}",
                    }
                )

            with upscaler.image(original, scale, cancel, progress) as improved:
                doc[page_num].replace_image(xref, stream=encode(improved, details))


def comparison(doc, stage, options, emit, cancel):
    found = images_to_enhance(doc)
    if not found:
        raise UserError("보정할 스캔 이미지가 없습니다.")
    xref = next(iter(found))
    with read_image(doc, xref) as image:
        # Compare an actual small centre crop, not a fabricated sample.
        w, h = image.size
        x = max(0, (w - 160) // 2)
        y = max(0, (h - 160) // 2)
        with image.crop((x, y, min(w, x + 160), min(h, y + 160))) as crop:
            scale = output_scale(options)
            size = (round(crop.width * scale), round(crop.height * scale))
            crop.resize(size, Image.Resampling.NEAREST).save(stage / "before.png")
            with Upscaler().image(crop, scale, cancel) as after:
                after.save(stage / "after.png")
