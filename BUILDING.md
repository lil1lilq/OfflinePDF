# 소스 실행과 빌드

## 개발 환경

- Windows 10·11, x64
- Python 3.12, x64
- PyMuPDF·Pillow·pillow-heif·NumPy·ONNX Runtime 및 PyInstaller: requirements 파일에 고정한 버전
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
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

GUI 검사는 데스크톱 환경이 필요합니다. 탐색기 파일 드롭 통합 검사는 Windows에서 실행합니다.
변경 사항과 검증 내역은 [CHANGELOG.md](CHANGELOG.md)에서 확인할 수 있습니다.

이미지 검사는 지원 형식의 실제 인코딩·디코딩, PDF 변환, 미리보기용 문서, 다중 프레임 순서, 사진 회전, 투명 배경, 원본 보존과 실패 시 결과 취소를 확인합니다.
HEIC 처리는 pillow-heif를 사용하며, 사용자 PC에서 별도 Windows 코덱을 요구하지 않습니다.
Windows 빌드에는 `packaging/hooks/hook-pillow_heif.py`가 배포 휠의 코덱 DLL을 포함합니다. 이 파일도 함께 유지하세요.

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

실행파일의 이름은 유지하고 제품 버전 정보에 0.8.2를 기록합니다.
Windows의 숫자 버전 정보는 0.8.2.0을 사용합니다. 코드서명 인증서는 포함하지 않습니다.

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
Windows의 한글 언어자료 경로는 `GetShortPathNameW`로 ASCII 축약 경로를 얻습니다. 축약 경로가 없으면 로컬 임시 경로·환경변수 경로 중 쓰기 가능한 영문 경로에 언어자료만 복사합니다.
오류나 정상 종료 시 해당 임시 디렉터리를 정리하며 문서는 이곳에 복사하지 않습니다. 모든 후보 경로는 기존 로컬 경로 정책을 적용합니다.

실행파일에는 애플리케이션의 `CorrespondingSource.zip`과 제3자 라이브러리의 `dependency-sources`를 함께 포함합니다.
[LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), `licenses`의 고지를 유지해야 합니다.

## AI 모델

`models` 전체를 소스와 함께 유지합니다. ONNX 모델, 원본 학습 가중치, BSD-3-Clause 고지, SHA256 명세를 포함합니다.
일반 빌드는 `python packaging/prepare_ai_model.py`로 동봉 파일을 검증하며 인터넷에서 모델을 받지 않습니다.
원본 가중치로 ONNX를 다시 만들려면 빌드 의존성을 설치한 뒤 다음을 실행합니다.

```powershell
python packaging/prepare_ai_model.py --convert
```

변환은 NumPy·ONNX만 사용합니다. PyTorch·BasicSR·CUDA는 빌드와 배포본 모두 필요하지 않습니다.
자동 검사는 NumPy로 독립 계산한 결과와 실제 모델 추론의 일치, 타일 경계, 2배·4배 크기, 텍스트 보존, 비교 미리보기와 취소를 확인합니다.
ONNX는 변환·검사용 빌드 의존성이며 사용자 실행파일에서는 제외합니다. 런타임에는 ONNX Runtime CPU와 NumPy를 포함합니다.
AI 텔레메트리는 세션 생성 전에 비활성화하고, 모델은 로컬 동봉 파일만 읽습니다.

## 코드 구조와 형식 검사

App은 세션 상태와 초기화·종료를 관리합니다. GUI 동작은 다음 모듈로 구분합니다.

| 모듈 | 담당 |
| --- | --- |
| controllers/files.py | 파일 추가·선택·암호·변환된 입력 반영 |
| controllers/navigation.py | 도구 선택·뒤로가기·후속 작업 |
| controllers/forms.py | 도구별 입력·설정 |
| controllers/preview.py | 문서·페이지 정리·AI 비교 화면 |
| controllers/jobs.py | 자식 프로세스·진행률·취소·결과 |
| engine.py | PDF 처리와 이미지 자동 변환 트랜잭션 |
| diagnostics.py | 합성 문서 기반 배포본 점검·명시적 네이티브 통신 대조 실험 |

Ruff 0.14.0으로 import·오류·미사용 코드 검사와 포맷을 통일합니다. 빌드에서도 두 검사를 실행합니다.

```powershell
python -m ruff check offline_pdf packaging tests main.py
python -m ruff format --check offline_pdf packaging tests main.py
```

## Windows 배포본·네트워크 검증

GitHub Actions는 빌드 후 packaging/verify_windows_build.ps1을 실행합니다.
이 절차는 관리자 권한의 격리된 Windows 시험 환경에서 수행하며 일반 사용자 실행에는 필요하지 않습니다.
설치형 검사는 실제로 임시 폴더에 설치하고, 검사 후 제거하므로 개발 중인 일반 PC보다 시험 VM을 사용하세요.

1. 포터블 실행파일의 명시적 --network-probe 대조 실험으로 외부 TCP 연결이 가능한지 확인합니다.
2. 실행파일별 아웃바운드 차단 규칙을 추가합니다. Python socket 패치 대신 Winsock 네이티브 호출로 TCP 연결을 재시도하고, Windows 보안 감사의 5157 차단 이벤트까지 확인합니다.
3. 대조 실험 이후 별도 감사 구간에서 --self-test를 실행합니다. 한글 경로, 혼합 입력 변환, 자식 프로세스, 압축, AI, HEIC, OCR, Tk 화면 이동을 합성 자료로 검사합니다.
4. 해당 실행파일과 같은 경로의 자식 프로세스에 대한 연결 허용·차단 이벤트(5156·5157)가 없는지 확인합니다.
5. 설치형도 임시 한글 경로에 설치한 뒤 같은 절차를 실행합니다. 검증 규칙·감사 정책·방화벽 프로필 상태는 종료 시 복원합니다.

기본 TCP 대조 대상은 1.1.1.1:443이며 연결 성립만 검사하고 PDF·파일·HTTP 요청을 보내지 않습니다.
이 연결은 개발용 --network-probe 명령에서만 발생합니다. 일반 실행·--self-test는 네트워크를 요청하지 않습니다.
대조 연결이나 보안 감사가 불가능하면 통과로 처리하지 않고 검증 실패로 보고합니다.

```powershell
# 관리자 권한의 시험 Windows에서 빌드 후 실행
powershell -NoProfile -ExecutionPolicy Bypass -File packaging/verify_windows_build.ps1
```

관리자 권한 없이 실행파일 자체 검사만 할 때는 -SkipFirewall을 명시합니다. 이는 네트워크 검증 통과를 의미하지 않으며 GitHub Actions에서는 사용하지 않습니다.
보고서는 release/validation과 Actions의 OfflinePDF-validation 아티팩트에 있습니다.
이번 검사는 합성 입력과 지정한 실행파일의 연결 이벤트에 한정됩니다. 모든 입력·모든 실행 상황의 무통신이나 외부 DLL의 완전한 격리를 증명하지 않습니다.
Windows 방화벽·보안 감사 검증은 Linux에서 대체할 수 없으며, 실제 결과는 Windows 실행 보고서로 확인해야 합니다.

공식 명령 설명:
- https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule
- https://learn.microsoft.com/windows/security/threat-protection/auditing/event-5157
