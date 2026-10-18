"""Offline image decoding shared by conversion and preview."""
from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import pymupdf as pdf

register_heif_opener(thumbnails=False)

IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.bmp', '.gif',
                              '.tif', '.tiff', '.webp', '.heic', '.heif'})
IMAGE_LABEL = 'JPG·PNG·BMP·GIF·TIF·TIFF·WebP·HEIC·HEIF'
IMAGE_PATTERN = ' '.join('*' + ext for ext in sorted(IMAGE_EXTENSIONS))
EXPORT_FORMATS = ('JPG', 'PNG', 'BMP', 'GIF', 'TIFF', 'WEBP')
MAX_IMAGE_PIXELS = 60_000_000


class ImageReadError(Exception):
    pass


def iter_frames(path, check=lambda: None):
    """Yield oriented RGB frames; never write decoded images to disk."""
    if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
        raise ImageReadError('지원하지 않는 이미지 확장자입니다.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {'JPEG', 'PNG', 'BMP', 'GIF', 'TIFF', 'WEBP', 'HEIF'}:
                    raise ImageReadError('지원하지 않는 이미지 형식입니다.')
                for index in range(getattr(source, 'n_frames', 1)):
                    check()
                    source.seek(index)
                    if source.width * source.height > MAX_IMAGE_PIXELS:
                        raise ImageReadError('이미지가 너무 큽니다. 가로·세로 크기를 줄인 뒤 다시 시도하세요.')
                    with ImageOps.exif_transpose(source) as oriented:
                        rgba = oriented.convert('RGBA')
                    try:
                        frame = Image.new('RGB', rgba.size, 'white')
                        with rgba.getchannel('A') as alpha:
                            frame.paste(rgba, mask=alpha)
                    finally:
                        rgba.close()
                    try:
                        yield frame
                    finally:
                        frame.close()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageReadError('이미지가 너무 큽니다. 가로·세로 크기를 줄인 뒤 다시 시도하세요.') from None
    except (OSError, SyntaxError, ValueError, EOFError):
        raise ImageReadError('이미지를 읽지 못했습니다. 파일 손상 여부와 이미지 형식을 확인하세요.') from None


def png_bytes(frame):
    with BytesIO() as output:
        frame.save(output, format='PNG', compress_level=1)
        return output.getvalue()


def open_image_document(path):
    """Create a temporary in-memory PDF for the existing preview controls."""
    doc = pdf.open()
    try:
        for frame in iter_frames(path):
            page = doc.new_page(width=frame.width, height=frame.height)
            page.insert_image(page.rect, stream=png_bytes(frame))
        return doc
    except BaseException:
        doc.close()
        raise


def save_pixmap(pixmap, destination, image_format):
    image_format = image_format.upper()
    if image_format == 'JPEG': image_format = 'JPG'
    if image_format == 'TIF': image_format = 'TIFF'
    if image_format not in EXPORT_FORMATS:
        raise ImageReadError('JPG·PNG·BMP·GIF·TIFF·WebP 중 저장 형식을 선택하세요.')
    with Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples) as image:
        options = {'dpi': (pixmap.xres, pixmap.yres)}
        if image_format in {'JPG', 'WEBP'}: options['quality'] = 90
        if image_format == 'TIFF': options['compression'] = 'tiff_deflate'
        image.save(destination, format='JPEG' if image_format == 'JPG' else image_format, **options)
