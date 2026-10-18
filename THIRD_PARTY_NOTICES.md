# 오픈소스 구성요소

이 프로젝트의 소스는 AGPL-3.0-or-later로 제공합니다. 전체 문구는 LICENSE에 있습니다.
PyMuPDF의 오픈소스 라이선스에 맞춰 프로그램의 대응 소스와 빌드 자료를 함께 배포합니다.
제3자 구성요소의 권리는 각 저작권자에게 있습니다.

| 구성요소 | 용도 | 라이선스 안내 |
| --- | --- | --- |
| PyMuPDF 1.26.6 및 포함 MuPDF | PDF 렌더링·처리 | AGPL-3.0 계열 오픈소스 경로 사용, Pro·상용 키 없음 |
| Pillow 13.0.0 | 이미지 읽기·쓰기·회전 정보 처리 | MIT-CMU 및 포함 이미지 라이브러리 고지 |
| pillow-heif 1.8.1 | HEIC·HEIF 읽기 | BSD-3-Clause. 바이너리에 포함된 libheif·libde265·x265 등의 별도 라이선스도 적용 |
| Python 3.12 | 실행 환경 | PSF 및 포함 구성요소 고지 |
| Tcl/Tk | 한글 데스크톱 화면 | Tcl/Tk 고지 및 조건 |
| PyInstaller 6.16.0 | 실행파일 패키징 | GPL 계열과 bootloader 예외, 일부 Apache-2.0 |
| Inno Setup 6 | 설치파일 생성 | Inno Setup License, 배포 시 해당 버전 조건 확인 |
| Tesseract OCR·tessdata | OCR 선택 기능 | Apache-2.0, 추가한 엔진·언어자료의 원본 고지 포함 필요 |

OCR은 PyMuPDF 빌드에 포함된 OCR 지원과 로컬 tessdata를 사용합니다.
별도 Tesseract 실행파일을 실행하거나 다운로드하지 않습니다.
한국어·영어 모델과 Apache-2.0 고지를 tessdata에 포함했으며 원본 커밋·해시는 models.json에 있습니다.

이미지 변환에는 오픈소스 Pillow와 pillow-heif를 사용합니다. HEIC는 PyMuPDF의 Pro 기능을 사용하지 않습니다.
pillow-heif 배포 휠에는 libheif(LGPLv3), libde265(LGPLv3), x265(GPLv2 계열)와 Windows 런타임 등이 포함됩니다.
실제 배포 휠의 LICENSE.txt와 LICENSES_bundled.txt를 licenses에 복사하고 이미지 라이브러리의 소스도 dependency-sources에 포함합니다.

공식 근거:
- https://pymupdf.readthedocs.io/en/latest/about.html
- https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html
- https://docs.python.org/3/license.html
- https://www.tcl-lang.org/software/tcltk/license.html
- https://pyinstaller.org/en/stable/license.html
- https://jrsoftware.org/files/is/license.txt
- https://github.com/tesseract-ocr/tesseract
- https://github.com/tesseract-ocr/tessdata_fast
- https://pillow.readthedocs.io/en/stable/about.html
- https://github.com/bigcat88/pillow_heif

Windows 빌드는 packaging/collect_licenses.py로 설치된 패키지의 실제 라이선스·메타데이터를
licenses에 복사합니다. 배포자는 DLL을 포함한 최종 산출물의 고지를 검토해야 합니다.
GitHub 업로드만으로 모든 제3자 라이선스 의무가 자동 충족된다고 가정하지 않습니다.
