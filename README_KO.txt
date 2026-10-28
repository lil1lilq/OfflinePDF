OfflinePDF 0.8.3 Windows 빌드 오류 수정

원인
추가한 모아찍기 테스트가 결과 폴더를 경로 문자열로 비교했습니다.
Windows의 RUNNER~1(짧은 경로)과 runneradmin(긴 경로)은 같은 폴더를 가리킬 수 있지만 문자열은 달라 테스트가 실패했습니다.
결과 폴더가 정확히 한 개만 남았는지 확인한 뒤 samefile()로 실제 동일 폴더인지 비교하도록 수정했습니다.
실패 시 전체 결과 취소 검사는 유지됩니다. 버전은 0.8.3 그대로입니다.

적용 방법 (이미 0.8.3 패치를 적용한 저장소용)
1. 이 압축파일의 tests/test_nup.py로 저장소의 tests/test_nup.py를 교체합니다.
2. GitHub에 커밋한 뒤 Actions에서 Build Windows x64를 다시 실행합니다.
   GitHub 웹에서는 tests/test_nup.py → 편집 → 파일 내용 전체 교체 → Commit changes로 적용할 수 있습니다.

Git으로 적용하려면 저장소 루트에서 다음 두 명령을 사용합니다.
 git apply --check "수정패치폴더/OfflinePDF-0.8.3-build-fix.patch"
 git apply "수정패치폴더/OfflinePDF-0.8.3-build-fix.patch"
파일 교체와 git apply 중 한 가지 방법만 사용하세요.

이 파일은 0.8.2 → 0.8.3 전체 기능 패치를 대신하지 않습니다.
0.8.3 패치 적용 후 발생한 테스트 오류를 수정하는 추가 패치입니다.
Windows Actions 재실행 결과는 아직 확인하지 못했습니다.
