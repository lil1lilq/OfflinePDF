import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import pymupdf as pdf

from offline_pdf.engine import Cancelled, UserError, execute
from offline_pdf.images import EXPORT_FORMATS, iter_frames, open_image_document


class ImageFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / '한글 경로'
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, tool, paths, **options):
        return execute({'tool': tool, 'files': [str(p) for p in paths],
                        'output': str(self.root), 'options': options})

    def test_input_formats_preview_and_original_preservation(self):
        formats = [('jpg', 'JPEG'), ('jpeg', 'JPEG'), ('png', 'PNG'), ('bmp', 'BMP'),
                   ('gif', 'GIF'), ('tif', 'TIFF'), ('tiff', 'TIFF'),
                   ('webp', 'WEBP'), ('heic', 'HEIF'), ('heif', 'HEIF')]
        for extension, image_format in formats:
            with self.subTest(extension=extension):
                source = self.root / ('사진.' + extension.upper())
                with Image.new('RGB', (80, 40), (220, 35, 20)) as im:
                    im.save(source, format=image_format)
                before = hashlib.sha256(source.read_bytes()).hexdigest()
                folder = self.run_tool('images_pdf', [source])
                with pdf.open(next(folder.glob('*.pdf'))) as doc:
                    self.assertEqual(doc.page_count, 1)
                    self.assertEqual(tuple(doc[0].rect), (0, 0, 595, 842))
                    self.assertEqual(len(doc[0].get_images()), 1)
                with open_image_document(source) as preview:
                    self.assertEqual(tuple(preview[0].rect), (0, 0, 80, 40))
                self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())

    def test_multiframe_order_and_transparent_background(self):
        for ext, fmt in [('gif', 'GIF'), ('tiff', 'TIFF'), ('webp', 'WEBP')]:
            with self.subTest(format=fmt):
                source = self.root / ('여러 장.' + ext)
                with Image.new('RGB', (30, 20), 'red') as first, Image.new('RGB', (30, 20), 'blue') as second:
                    first.save(source, format=fmt, save_all=True, append_images=[second], duration=100, lossless=True)
                folder = self.run_tool('images_pdf', [source])
                with pdf.open(next(folder.glob('*.pdf'))) as doc:
                    self.assertEqual(doc.page_count, 2)
                    colors = [p.get_pixmap().pixel(297, 421) for p in doc]
                    self.assertGreater(colors[0][0], colors[0][2])
                    self.assertGreater(colors[1][2], colors[1][0])
        transparent = self.root / '투명.png'
        with Image.new('RGBA', (10, 10), (0, 0, 0, 0)) as im: im.save(transparent)
        for frame in iter_frames(transparent): self.assertEqual(frame.getpixel((0, 0)), (255, 255, 255))

    def test_exif_orientation(self):
        source = self.root / '회전.jpg'
        with Image.new('RGB', (80, 40), 'green') as im:
            exif = Image.Exif(); exif[274] = 6
            im.save(source, exif=exif)
        with open_image_document(source) as doc:
            self.assertEqual(tuple(doc[0].rect), (0, 0, 40, 80))

    def test_output_formats_default_and_roundtrip(self):
        source = self.root / '문서.pdf'
        with pdf.open() as doc:
            p = doc.new_page(width=100, height=120)
            p.insert_text((10, 25), 'FORMAT TEST', fontsize=8)
            doc.save(source)
        default = self.run_tool('pdf_images', [source], dpi='72')
        self.assertEqual(len(list(default.glob('*.jpg'))), 1)
        for fmt in EXPORT_FORMATS:
            with self.subTest(format=fmt):
                folder = self.run_tool('pdf_images', [source], dpi='72', format=fmt)
                output = next(folder.iterdir())
                self.assertEqual(output.suffix, '.' + fmt.lower())
                with Image.open(output) as im:
                    im.load()
                    self.assertEqual(im.format, 'JPEG' if fmt == 'JPG' else fmt)
                    self.assertEqual(im.size, (100, 120))
                result = self.run_tool('images_pdf', [output])
                with pdf.open(next(result.glob('*.pdf'))) as doc: self.assertEqual(len(doc), 1)

    def test_bad_image_rolls_back_whole_batch(self):
        good = self.root / '정상.bmp'
        with Image.new('RGB', (10, 10), 'red') as im: im.save(good)
        bad = self.root / '손상.heic'; bad.write_bytes(b'not a HEIC file')
        with self.assertRaises(UserError): self.run_tool('images_pdf', [good, bad])
        self.assertFalse(list(self.root.glob('.offline-pdf-*')))
        self.assertFalse(list(self.root.glob('PDF결과_*')))

    def test_cancel_between_frames(self):
        source = self.root / '취소.tiff'
        with Image.new('RGB', (10, 10), 'red') as im:
            im.save(source, save_all=True, append_images=[im])
        count = 0
        def check():
            nonlocal count
            count += 1
            if count == 2: raise Cancelled()
        frames = iter_frames(source, check)
        next(frames)
        with self.assertRaises(Cancelled): next(frames)


if __name__ == '__main__': unittest.main()
