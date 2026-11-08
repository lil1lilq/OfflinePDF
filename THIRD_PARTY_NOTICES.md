# 오픈소스 구성요소

이 프로젝트의 소스는 AGPL-3.0-or-later로 제공합니다. 전체 문구는 LICENSE에 있습니다.
PyMuPDF의 오픈소스 라이선스에 맞춰 프로그램의 대응 소스와 빌드 자료를 배포 파일과 같은 곳에서
`OfflinePDF-<버전>-source.zip`으로 함께 제공합니다(SOURCE_CODE.txt 참고).
제3자 구성요소의 권리는 각 저작권자에게 있습니다.

| 구성요소 | 용도 | 라이선스 안내 |
| --- | --- | --- |
| PyMuPDF 1.26.7 및 포함 MuPDF 1.26.12 | PDF 렌더링·처리 | AGPL-3.0 계열 오픈소스 경로 사용, Pro·상용 키 없음 |
| Pillow 13.0.0 | 이미지 읽기·쓰기·회전 정보 처리 | MIT-CMU 및 포함 이미지 라이브러리 고지 |
| NumPy 2.2.6 | AI 이미지 배열 처리 | BSD-3-Clause 및 OpenBLAS 등 포함 구성요소 고지 |
| ONNX Runtime 1.24.2 CPU | 오프라인 AI 추론 | MIT 및 ThirdPartyNotices |
| Real-ESRGAN realesr-general-x4v3 | AI 업스케일 가중치 | BSD-3-Clause, 원본 고지는 models/Real-ESRGAN-LICENSE.txt |
| ONNX 1.17.0 | 모델 변환·검사 전용 | Apache-2.0, 사용자 실행파일에는 제외 |
| Python 3.12 | 실행 환경 | PSF 및 포함 구성요소 고지 |
| Tcl/Tk | 한글 데스크톱 화면 | Tcl/Tk 고지 및 조건 |
| CustomTkinter 5.2.2 | 데스크톱 화면 위젯 | MIT, licenses/customtkinter 및 배포 소스 참조 |
| Lucide Icons (lucide-static 1.70.0) | 도구 카드 아이콘 | ISC, assets/lucide/LICENSE |
| Pretendard 1.3.9 | 화면 글꼴 | SIL OFL 1.1, assets/fonts/LICENSE |
| PyInstaller 6.16.0 | 실행파일 패키징 | GPL 계열과 bootloader 예외, 일부 Apache-2.0 |
| Tesseract OCR·tessdata | OCR 선택 기능 | Apache-2.0, 추가한 엔진·언어자료의 원본 고지 포함 필요 |

OCR은 PyMuPDF 빌드에 포함된 OCR 지원과 로컬 tessdata를 사용합니다.
별도 Tesseract 실행파일을 실행하거나 다운로드하지 않습니다.
AI 가중치 원본은 models/source에, 변환된 ONNX와 SHA256은 models에 포함합니다.
런타임 의존성인 flatbuffers·protobuf·sympy·mpmath·packaging의 고지도 licenses에 함께 수집합니다.
한국어·영어 모델과 Apache-2.0 고지를 tessdata에 포함했으며 원본 커밋·해시는 models.json에 있습니다.

이미지 변환에는 오픈소스 Pillow만 사용합니다. HEVC 코덱(HEIC·HEIF)은 특허 문제로 포함하지 않습니다.
Pillow 배포 휠에 포함된 이미지 라이브러리의 고지는 licenses/Pillow의 LICENSE에 있습니다.

공식 근거:
- https://pymupdf.readthedocs.io/en/latest/about.html
- https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html
- https://docs.python.org/3/license.html
- https://www.tcl-lang.org/software/tcltk/license.html
- https://pyinstaller.org/en/stable/license.html
- https://github.com/tesseract-ocr/tesseract
- https://github.com/tesseract-ocr/tessdata_fast
- https://pillow.readthedocs.io/en/stable/about.html

Windows 빌드는 packaging/collect_licenses.py로 설치된 패키지의 실제 라이선스·메타데이터를
licenses에 복사합니다. 배포자는 DLL을 포함한 최종 산출물의 고지를 검토해야 합니다.
GitHub 업로드만으로 모든 제3자 라이선스 의무가 자동 충족된다고 가정하지 않습니다.
