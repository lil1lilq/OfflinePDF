# 소스 실행과 빌드

이 문서는 OfflinePDF를 소스에서 실행하거나 Windows 배포본을 만드는 개발자를 위한 안내입니다.
프로그램 다운로드와 기본 사용법은 [README](README.md), 조작 방법은 [사용 안내](USER_GUIDE_KO.txt)에 있습니다.

## 개발 환경

- Windows 10·11, x64
- Python 3.12, x64

실행 의존성은 `requirements.txt`, 빌드·검사 도구는 `requirements-build.txt`에 버전이 고정되어 있습니다.
Windows 실행파일은 Windows에서 빌드합니다.

## 소스 실행

저장소 루트에서 PowerShell로 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 검사

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m ruff check offline_pdf packaging tests main.py
.\.venv\Scripts\python.exe -m ruff format --check offline_pdf packaging tests main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GUI 검사는 사용 가능한 데스크톱이 필요하며, 탐색기 파일 드롭 통합 검사는 Windows에서 실행됩니다.
화면을 사용할 수 없는 환경에서는 GUI 검사 클래스가 제외될 수 있습니다.
제외된 검사는 성공한 검사와 구분해서 확인해야 합니다.

## Windows 배포본 생성

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Python .\.venv\Scripts\python.exe
```

빌드 스크립트는 다음 순서로 실행됩니다.

1. Python 버전·아키텍처와 AI 모델 파일 확인
2. 코드·형식 검사와 자동 검사
3. 구성요소 고지와 의존성 소스 수집
4. PyInstaller 포터블 프로그램 생성
5. 포터블 ZIP 압축 및 SHA256 기록

배포 결과물은 포터블 ZIP과 SHA256 목록입니다. Inno Setup은 필요하지 않습니다.

| 출력 | 파일 |
| --- | --- |
| 포터블 | `release/OfflinePDF-Windows-x64-portable.zip` |
| 해시 목록 | `release/SHA256SUMS.txt` |

빌드는 `README.md`, `USER_GUIDE_KO.txt`, `CHANGELOG.md`, `BUILDING.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`를 배포본에 복사합니다.
`README.md`는 PyInstaller 데이터에도 포함됩니다.
사용 안내는 포터블 폴더의 `USER_GUIDE_KO.txt`에서 확인할 수 있습니다.

버전은 다음 위치에서 관리합니다.

| 위치 | 값의 형식 |
| --- | --- |
| `offline_pdf/__init__.py` | 앱 표시 버전, 예: `0.8.7` |
| `packaging/windows-version.txt` | 실행파일 제품·파일 버전, 숫자 버전은 4자리 |

소스 버전을 바꿀 때 관련 검사와 문서의 버전 표기도 함께 갱신합니다.

## GitHub Actions와 릴리스

**Actions → Build Windows x64 → Run workflow**에서 수동 실행하거나 `v*` 태그를 푸시하면 빌드가 시작됩니다.
워크플로는 포터블 ZIP을 압축 해제해 검사하고 다음 아티팩트를 업로드합니다.

- `OfflinePDF-Windows-x64`: 배포 파일
- `OfflinePDF-validation`: 검증 보고서

현재 워크플로는 GitHub Release를 자동 게시하지 않습니다.
공개 배포 시 검증을 마친 버전의 태그로 Release를 만들고 포터블 ZIP과 SHA256 파일을 첨부합니다.
소스의 버전과 사용자가 내려받는 Release의 버전은 별도로 확인해야 합니다.

## 오프라인 빌드

인터넷이 되는 Windows x64·Python 3.12 환경에서 의존성을 준비합니다.

```powershell
.\.venv\Scripts\python.exe -m pip download -r requirements-build.txt --only-binary=:all: -d wheelhouse
.\.venv\Scripts\python.exe packaging/prepare_dependency_sources.py
```

저장소, `wheelhouse`, `dependency-sources`, Python 설치본을 오프라인 빌드 환경으로 옮긴 뒤 실행합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Offline -Python .\.venv\Scripts\python.exe
```

## 모델과 구성요소

| 위치 | 내용 |
| --- | --- |
| `models/realesr-general-x4v3.onnx` | 실행 중 사용하는 AI 모델 |
| `models/source/realesr-general-x4v3.pth` | ONNX 재생성과 빌드 검증에 사용하는 원본 가중치 |
| `models/manifest.json` | 모델 출처와 SHA256 |
| `tessdata/eng.traineddata`, `tessdata/kor.traineddata` | OCR 언어자료 |
| `tessdata/models.json` | OCR 자료 출처·커밋·SHA256 |
| `packaging/hooks/hook-pillow_heif.py` | Windows 이미지 코덱 DLL 수집 |

일반 빌드는 포함된 AI 모델을 검증합니다. 모델 재생성이 필요한 경우 다음 명령을 사용합니다.

```powershell
.\.venv\Scripts\python.exe packaging/prepare_ai_model.py --convert
```

변환에는 NumPy·ONNX를 사용합니다. 실행 프로그램은 ONNX Runtime CPU를 사용하며 PyTorch·CUDA를 요구하지 않습니다.
AI·OCR 모델은 배포본에 포함되며 문서 처리 중 다운로드하지 않습니다.

배포본에는 앱 소스인 `CorrespondingSource.zip`, 구성요소 고지인 `licenses`, 의존성 소스인 `dependency-sources`가 포함됩니다.
라이선스 원문과 구성요소별 안내는 [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.

## Windows 배포본 검사

GitHub Actions는 빌드 후 `packaging/verify_windows_build.ps1`을 실행합니다.
이 검사는 포터블 ZIP을 한글 임시 경로에 압축 해제한 뒤 실행합니다. 방화벽·보안 감사 설정을 사용하므로 관리자 권한의 격리된 Windows 시험 환경을 대상으로 합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/verify_windows_build.ps1
```

검사 항목은 다음과 같습니다.

- 합성 문서의 PDF 처리, 이미지 변환, AI·OCR, 자식 프로세스와 화면 이동
- 포터블 ZIP에서 추출한 실행파일의 동작
- 방화벽 차단 상태의 처리와 지정 실행파일의 연결 이벤트

`--network-probe`는 일반 문서 처리와 분리된 개발용 통신 검사입니다.
기본 대상 `1.1.1.1:443`에 TCP 연결을 시도하며 문서나 HTTP 요청은 보내지 않습니다.
검사에서 추가한 방화벽 규칙과 변경한 감사 설정은 종료 시 복원합니다.

관리자 권한 없이 자체 검사만 실행할 때는 `-SkipFirewall`을 지정할 수 있습니다.
이 경우 네트워크 검증은 수행되지 않습니다. 보고서는 `release/validation`에 저장됩니다.
검사 결과는 지정 실행파일과 합성 입력에 대한 결과이며 모든 입력이나 실행 상황을 보장하지 않습니다.

## 코드 구조

| 위치 | 역할 |
| --- | --- |
| `offline_pdf/app.py` | 앱 초기화와 종료 |
| `offline_pdf/controllers/` | 파일·화면·설정·작업 진행 제어 |
| `offline_pdf/engine.py` | PDF 처리와 결과 저장 |
| `offline_pdf/nup.py` | A4 모아찍기와 미리보기 배치 |
| `offline_pdf/enhance.py` | AI 이미지 보정 |
| `offline_pdf/images.py`, `offline_pdf/ocr.py` | 이미지·OCR 처리 |
| `offline_pdf/diagnostics.py` | 배포본 자체 검사와 개발용 통신 검사 |
| `packaging/` | 모델 검증·구성요소 수집·Windows 패키징 |
| `tests/` | 기능·회귀 검사 |

## 완료된 빌드 파일의 악성코드 검사

**Actions → Scan Windows artifact → Run workflow**에서 기존 빌드의 포터블 ZIP과 내부 파일을 검사할 수 있습니다.
`build_run_id`를 비우면 `windows-build.yml`의 최신 성공 실행을 선택합니다. 다른 빌드를 검사하려면 실행 URL의 `/actions/runs/` 다음 숫자를 입력합니다.
보관 기간이 지나 아티팩트가 삭제된 실행은 검사할 수 없습니다.

워크플로는 Microsoft Defender 보안 정보를 갱신하고 포터블 ZIP과 압축을 푼 파일을 검사합니다.
대상 프로그램을 설치하거나 실행하지 않습니다. 결과는 `OfflinePDF-antivirus-report` 아티팩트에 저장됩니다.

- `summary.json`: 완료 여부와 검사 종료 코드
- `portable-zip.log`, `portable-files.log`: 실제 검사 출력과 탐지 정보
- `portable-signature.json`: 포터블 실행파일의 코드 서명 상태
- `artifact-sha256.csv`, `portable-files-sha256.csv`: 파일별 SHA256
- `build-run.json`, `defender-status.json`: 검사 대상 빌드와 검사 엔진 정보

검사 중 탐지 또는 오류가 있으면 실행이 실패 상태로 끝나며 결과 로그는 보관됩니다.
종료 코드 2는 악성코드 탐지뿐 아니라 검사 오류일 수도 있으므로 원본 로그를 확인해야 합니다.
엔진·서비스·보안 정보 갱신을 사용할 수 없으면 `incomplete_or_unavailable`로 기록합니다.
`no_detection_reported`는 해당 Defender 검사에서 탐지가 보고되지 않았다는 뜻이며 안전 보증이나 Chrome Safe Browsing 차단 해제를 의미하지 않습니다.
기존 빌드·배포 워크플로는 이 검사와 별도로 실행됩니다.
