# OfflinePDF

[한국어](README.md) | **English**

A Windows desktop program for merging, splitting and editing PDFs.
Documents are processed on your PC. Files are never uploaded to an external conversion server.

## [Download](https://github.com/lil1lilq/OfflinePDF/releases/latest)

| File | How to run |
| --- | --- |
| OfflinePDF-Setup-Windows-x64.exe | Installer (recommended) |
| OfflinePDF-Windows-x64-portable.zip | Portable version. Extract it and run `OfflinePDF.exe` inside the folder |
| OfflinePDF-1.2.2-source.zip | Source code of the program and its components (AGPL-3.0). Not needed to run it |
| SHA256SUMS.txt | Hashes for verifying file integrity. Not needed to run the program |

Two downloads are available: an installer, and a portable ZIP that needs no installation. Windows 10 and 11, 64-bit, are supported. Everything the program needs is included, so Python does not have to be installed.
Keep the portable version's folder together with the executable.

The current source version is **1.2.3**. Check the version shown on Releases for the downloaded files.
Features or fixes added to the source may not be in earlier releases.

## Program screenshots

| Feature | Screenshot |
| :--- | :--- |
| **Main screen** | <img width="900" alt="OfflinePDF main screen" src="https://github.com/user-attachments/assets/35c46ec9-970c-49ee-a867-6230f96e3f31" /> |
| **Windows Explorer context menu** | <img width="650" alt="Windows Explorer context menu" src="https://github.com/user-attachments/assets/3d4e7733-67ce-4f52-9772-8d189e6aac42" /> |
| **PDF redaction** | <img width="1000" alt="Before and after redacting personal information in a PDF" src="https://github.com/user-attachments/assets/af76e58a-3bc9-4315-8c75-2a9cdf5f2f43" /><br><sub>**Before (left)** → **After (right)**: Personal information removed from the selected area</sub> |

## Features

| Feature | Description |
| --- | --- |
| Merge PDF · Split PDF | Merge several files, split per page, or split at chosen start pages |
| Organize pages | Drag thumbnails to reorder; delete or rotate selected pages |
| A4 handouts | Place 1 to 64 pages on one A4 sheet; set orientation, margins and gaps |
| Compress PDF | Lossless, High quality, Recommended or Small, or a target size in MB per file |
| PDF to images · Images to PDF | Save PDF pages as images, or turn images into A4 PDFs |
| Password | Set or remove a PDF opening password |
| Text and image overlay · Page numbers | Add text, signature or stamp images, and page numbers |
| Crop margins · Redact | Cover page edges; permanently delete the content of selected areas |
| Extract text · Scan OCR | Save text; recognize Korean and English text in scanned documents |
| AI enhancement | Sharpen scanned images at the same size, or upscale them 1.5x or 2x (4x under advanced options); compare a before/after detail |
| Clean metadata | Clean document properties, attachments and similar data |

Tick **Remove plain white pages** in the sidebar to drop blank pages from PDF results. It is off every time the program starts. Pages with any text, shapes, annotations, form fields or image traces are kept.
Target and maximum sizes are limits per file. If they cannot be met even at the minimum image DPI and quality, that job's results are not saved. Size limits may lower the quality of AI-enhanced images.

Image input supports JPG, PNG, BMP, GIF, TIFF and WebP. HEIC/HEIF (iPhone photos) is not supported because of codec patent issues; convert such photos to JPG first.
PDF pages can be exported as JPG, PNG, BMP, GIF, TIFF or WebP.
Word, Excel, PowerPoint and HWP conversion is not supported.

## How to use

1. Click **Add files**, or drag files from File Explorer onto the window.
2. Choose a tool on the start screen. In a small window, scroll to see the other tools.
3. Set the page range, the tool's options and the save folder, then run.
4. Use **Open result folder** to see the saved files.

Original files are never overwritten. Results are saved in a `PDF결과_…` folder under the chosen location.
After a job, **Use results for next operation** continues with the result files in another tool.

Leave the page field empty to process every page. `1-3,5` means pages 1 to 3 and page 5; `3-1` means reverse order.
Images you add are converted to PDF automatically before the selected job.

Use **Settings** at the bottom of the window to choose Korean or English and the Default or Dark mode theme. Both are kept for the next start.
**About** shows the version, the license and where the source code is.

## Before you rely on the results

- **Crop margins** and A4 handouts' **Fill (crop edges)** only cover content. The covered information may remain in the document.
- **Redact** applies to the areas you select. It does not find and remove personal information across the whole document, so check the result.
- OCR can misread text. AI enhancement can change the shape of small letters, numbers and signatures; compare with the original.
- Adding a signature or stamp image is not a certificate-based digital signature. Editing a PDF that already has a digital signature can change its verification status.
- Network drives and known sync folders are restricted. Keep working files and results in local folders.

## Source and license

[Running and building from source (Korean)](BUILDING.md) · [Changelog (Korean)](CHANGELOG.md)

The source code is provided under [AGPL-3.0-or-later](LICENSE).
Notices for third-party components and models are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Explorer context menu

**Add Explorer PDF menu** is checked by default during installation. Uncheck it if you do not want it.
On Windows 11, find it under **Show more options → OfflinePDF**. It uses the same icon as the program.

- **Quick run**: Processes files automatically in a compact progress window. Merging uses file-name order, splitting creates one file per page, compression uses Recommended quality, and AI enhancement uses 1.5x. Password protection/removal asks only for the passwords it needs.
- **Open in OfflinePDF**: Opens the task screen so you can review file order and settings before running.

Files from the same folder are saved in a result folder under that folder. If the files come from different folders, you are asked to choose an output location.
Originals are preserved. The quick-run window shows cancellation, errors and completion.
When merging PDFs with different passwords, you are asked to set a new password for the result.
File requests are briefly collected into batches. Files arriving after processing starts may be handled as a separate job.
Progress reflects the current processing phase and does not guarantee the total remaining time.
In the full app, splitting at specified start pages applies to the selected file only; per-page splitting applies to the whole list.

Portable users can register the current-user menu with `Register-Explorer.cmd` and remove it with `Unregister-Explorer.cmd`.
Unregister before moving the folder and register again at the new location. Do not register installed and portable copies at the same time.
The command-line flags `--register-explorer` and `--unregister-explorer` are also supported.
