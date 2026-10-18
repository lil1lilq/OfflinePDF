# 소스 실행과 빌드

## 개발 환경

- Windows 10·11, x64
- Python 3.12, x64
- PyMuPDF 및 PyInstaller: requirements 파일에 고정한 버전
- 설치파일 생성: Inno Setup 6.x

## 소스 실행

프로젝트 루트에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 자동 검사

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GUI 검사는 데스크톱 환경이 필요합니다. 탐색기 파일 드롭 통합 검사는 Windows에서 실행합니다.
변경 사항과 검증 내역은 [CHANGELOG.md](CHANGELOG.md)에서 확인할 수 있습니다.

## Windows 실행파일 생성

Inno Setup 6.x를 설치한 뒤 프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Python .\.venv\Scripts\python.exe
```

스크립트는 자동 검사, 라이선스 수집, 의존성 대응 소스 수집, PyInstaller 패키징과 Inno Setup 컴파일을 순서대로 수행합니다.
Inno Setup이 없으면 포터블 ZIP만 생성합니다. Windows 실행파일은 Windows 환경에서 빌드합니다.

| 출력 파일 | 내용 |
| --- | --- |
| `release/OfflinePDF-Setup-Windows-x64.exe` | 설치파일 |
| `release/OfflinePDF-Windows-x64-portable.zip` | 압축 실행형 |
| `release/SHA256SUMS.txt` | 배포 파일의 SHA256 검증값 |

실행파일의 이름은 유지하고 제품 버전 정보에 1.2를 기록합니다.
Windows의 숫자 버전 정보는 1.2.0.0을 사용합니다. 코드서명 인증서는 포함하지 않습니다.

## GitHub Actions

저장소에 포함된 **Build Windows x64** 워크플로를 수동 실행하거나 `v*` 태그로 실행할 수 있습니다.
완료된 실행의 **Artifacts → OfflinePDF-Windows-x64**에서 결과를 확인합니다.
Releases 공개 여부는 해당 저장소의 게시 설정에 따릅니다.

## 인터넷 없는 빌드 환경

동일한 Windows x64·Python 3.12 환경에서 의존성을 미리 준비합니다.

```powershell
python -m pip download -r requirements-build.txt --only-binary=:all: -d wheelhouse
python packaging/prepare_dependency_sources.py
```

프로젝트, `wheelhouse`, `dependency-sources`, Python과 Inno Setup의 설치본을 오프라인 환경으로 옮깁니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Offline -Python .\.venv\Scripts\python.exe
```

대응 소스 자료의 SHA256과 파일 구성을 빌드 중 확인합니다.

## OCR과 라이선스

`tessdata`의 한국어·영어 모델을 빌드 시 포함하며, 프로그램 실행 중 다운로드하지 않습니다.
모델 출처·SHA256은 `tessdata/models.json`, 고지는 `tessdata/LICENSE`에서 확인할 수 있습니다.

실행파일에는 애플리케이션의 `CorrespondingSource.zip`과 제3자 라이브러리의 `dependency-sources`를 함께 포함합니다.
[LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), `licenses`의 고지를 유지해야 합니다.
