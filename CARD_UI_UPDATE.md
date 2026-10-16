# 카드형 UI 업데이트

## 적용 방법

1. ZIP 파일을 압축 해제합니다.
2. 기존 GitHub 프로젝트의 `main.py`가 있는 폴더에 압축 해제한 내용을 덮어씁니다. `offline_pdf`와 `tests` 폴더를 새 하위 폴더로 넣지 말고 기존 폴더와 합칩니다.
3. 아래 명령으로 변경 내용을 올립니다.

```sh
git status --short
git add offline_pdf/app.py offline_pdf/engine.py offline_pdf/layout.py offline_pdf/ui.py offline_pdf/windows_drop.py tests/test_app.py tests/test_engine.py tests/test_windows_drop.py CARD_UI_UPDATE.md
git commit -m "Add card home and PDF task workspace"
git push origin main
```

4. GitHub의 Actions에서 새 커밋으로 빌드합니다. 수동 실행이면 `Build Windows x64 → Run workflow → main`을 선택합니다.
5. 새 빌드 결과를 다운로드해 설치하거나 압축을 풀어 실행합니다. 기존 실행파일은 소스를 덮어써도 바뀌지 않습니다.

이 ZIP은 소스 업데이트입니다. Windows EXE는 포함하지 않습니다. 기존 `.github/workflows` 파일, 릴리스 게시 설정, requirements, 빌드 스크립트는 바꾸지 않습니다. 추가 라이브러리 설치는 필요 없습니다.

`git status`에 아무것도 나오지 않는다면 현재 위치를 확인합니다.

```sh
git rev-parse --show-toplevel
git diff -- offline_pdf/app.py offline_pdf/engine.py
```

프로젝트 루트의 `offline_pdf/layout.py`와 `offline_pdf/ui.py`가 새로 추가되어 있어야 합니다. 두 파일이 빠지면 실행할 수 없습니다.

## 변경 내용

- 시작 화면에 자주 쓰는 도구 6개를 카드로 배치합니다.
- '전체 도구 보기'를 누르면 나머지 12개도 같은 크기와 모양의 카드로 표시합니다. '접기'로 되돌립니다.
- 카드를 누르면 파일 목록과 작업 설정 화면으로 이동합니다. '모든 도구'로 돌아갑니다.
- 창 너비에 맞춰 카드 열 수를 조정하고, 도구가 많으면 스크롤합니다. Tab과 Enter 또는 Space로도 카드를 선택할 수 있습니다.
- 기존 PDF 기능 18개와 Windows 파일 드래그앤드롭을 유지합니다. 이전 드래그앤드롭 빌드 오류 수정도 포함합니다.
- 파일 목록의 '미리보기 펼치기'로 미리보기를 확인합니다. 영역 영구 삭제에서는 미리보기가 자동으로 열립니다.
- 실행·취소·결과 폴더 버튼은 아래쪽에 고정되어 스크롤해도 사용할 수 있습니다.
- 저장 위치는 첫 번째 원본 파일의 폴더 또는 직접 지정한 폴더 중에서 선택합니다. 결과는 그 안에 새 `PDF결과_날짜시간_식별자` 폴더로 저장합니다.
- PDF 합치기와 이미지 → PDF에서 결과 파일 이름을 지정할 수 있습니다. 나머지 도구는 기존 파일 이름 규칙을 유지합니다.
- '완료 후 저장 폴더 열기' 선택 시 작업 완료 후 결과 폴더를 엽니다.
- 홈과 작업 화면의 '이 PC에서 처리' 등 안내 문구를 제거합니다.

## 포함 파일

```text
offline_pdf/app.py
offline_pdf/engine.py
offline_pdf/layout.py
offline_pdf/ui.py
offline_pdf/windows_drop.py
tests/test_app.py
tests/test_engine.py
tests/test_windows_drop.py
CARD_UI_UPDATE.md
```

## 검증 결과

2026-10-16, Python 실행 환경과 X 가상 화면에서 자동 검사 41건 중 40건 통과, Windows 전용 Shell 통합 검사 1건은 실행 환경이 달라 제외했습니다. 해당 검사는 삭제하지 않았으며 기존 Windows Actions에서 실행합니다.

카드 6개/18개 전환, 동일 카드 크기, 작업 화면 이동, 처리 중 이동 방지, PDF/이미지 도구 전환, 미리보기 펼침, 작은 창에서 실행 버튼 노출, 실제 PDF 회전·이름 지정 병합·자동 폴더 열기 호출을 확인했습니다. 기존 암호·영역 삭제·OCR·작업 취소·드래그앤드롭 큐 검사도 통과했습니다.

1180×850과 900×650 화면에서 18개 도구의 주요 입력란과 버튼에 가로 잘림이 없는지 확인했습니다. Windows EXE 빌드와 실제 탐색기 드래그앤드롭은 이 환경에서 실행하지 않았습니다.

```sh
python -m unittest discover -s tests -v
```

새 모듈과 아이콘은 Python 기본 Tkinter로 작성했습니다. 외부 폰트·아이콘·테마를 다운로드하지 않습니다. 기존 오프라인 처리와 AGPL-3.0-or-later 라이선스를 유지합니다.
