# Windows 드롭 시험 충돌 수정

GitHub Actions의 test_h_native_windows_drop_message 실행 중 Python 프로세스가 비정상 종료되는 문제에 대한 수정 파일입니다.

## 변경

기존 Windows 콜백은 파일을 받으면서 Tk의 after_idle을 호출했습니다.
네이티브 메시지 처리 중 Tk에 다시 진입하는 경로가 생기므로 해당 호출을 제거했습니다.
이제 Windows 콜백은 파일 경로를 Python 큐에 보관하고 반환합니다.
화면과 파일 목록 갱신은 Tk가 실행하는 75ms 주기의 타이머에서 처리합니다.

Windows 네이티브 시험은 그대로 유지합니다. 시험을 건너뛰어 빌드를 통과시키는 변경은 포함하지 않습니다.

## 적용

1. 기존 프로젝트의 main.py가 있는 폴더에 ZIP을 풀고 같은 이름의 파일을 덮어씁니다.
2. 아래 파일을 GitHub main 브랜치에 커밋·푸시합니다.
   - offline_pdf/windows_drop.py
   - tests/test_windows_drop.py
3. Actions → Build Windows x64 → Run workflow에서 main을 선택해 새 빌드를 실행합니다.

기존 실패 실행의 Re-run jobs는 이전 커밋을 사용하므로 이번 수정이 적용되지 않습니다.

## 검증

Linux Python 3.12와 가상 디스플레이에서 기존 기능 및 수정 관련 자동 시험 34개 통과.
Windows 전용 네이티브 연동 시험 1개는 이 환경에서 실행하지 못했습니다.
Windows 콜백이 Tk API를 호출하지 않는지, 전달 순서와 파일명 보존, 종료 시 대기 자료 정리를 확인했습니다.

실제 Windows 충돌이 해결됐는지는 새 커밋의 Windows 빌드 결과로 확인해야 합니다.
