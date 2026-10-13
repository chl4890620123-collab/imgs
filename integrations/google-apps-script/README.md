# Google Drive → Google Sheets 사석 GPU 작업 현황

`imgs`에서 이미 사용 중인 `SASEOK_GPU_QUEUE/jobs/{queued,running,done,failed,cancelled}/*.json`을 **읽기 전용**으로 정리합니다.

**기존 영상 생성기, Drive 작업 큐, Colab GPU 워커의 실행 로직은 변경하지 않습니다.** 스프레드시트는 모니터링 화면일 뿐 작업 실행을 대신하지 않습니다.

## 사용 방법

1. Google Drive에서 Colab/Studio가 공유하는 `SASEOK_GPU_QUEUE` 폴더를 확인합니다.
2. 해당 폴더를 열었을 때 주소의 `/folders/<ID>`에서 폴더 ID를 복사합니다. (`jobs` 하위 폴더가 아니라 **큐 최상위 폴더**)
3. 별도의 Google 스프레드시트를 만들고 **확장 프로그램 → Apps Script**를 엽니다.
4. [Code.gs](./Code.gs)를 바인딩된 스크립트의 `Code.gs`에 복사하고 저장합니다.
5. Apps Script **프로젝트 설정 → 스크립트 속성**에 `SASEOK_QUEUE_FOLDER_ID`를 설정합니다. ID를 소스코드에 하드코딩하지 마세요.
6. 스프레드시트를 새로고침한 뒤 **사석 렌더 현황 → 작업 현황 새로고침**을 선택하고 권한을 승인합니다.
7. 확인 후 필요할 때 **1시간마다 자동 새로고침 설정**을 선택합니다. 사용하지 않을 때는 **자동 새로고침 중지**를 선택합니다.

## 출력 항목

`렌더작업` 탭에 다음 열을 표시합니다.

- 작업 ID / 프로젝트 / 장면 / 컷
- 상태(queued, running, done, failed, cancelled) / 단계 / 진행률 / 최종 갱신
- 출력 파일 상대경로 / 에러 메시지 / Google Drive 원본 JSON 링크

중복된 job_id가 둘 이상 존재하면 JSON의 `updated_at`이 최신인 쪽을 표시합니다.

## 운영상의 제약

- **이 스크립트는 Drive JSON을 수정·삭제·생성하지 않습니다.** 현재 사용자의 Drive 접근 권한이 필요합니다.
- 작업 JSON이 500개를 넘거나 1개 파일이 100KB보다 크면 오류로 중단하고 **기존 대시보드를 유지**합니다. 대규모 이력이 쌓이면 아카이빙 또는 페이지 분리가 필요합니다.
- JSON 파일 손상, Drive 동기화 지연, 사용자 권한 부족도 오류 원인이 될 수 있습니다.
- Drive의 폴더 이름과 `studio/remote_jobs.py`·`colab/drive_worker.py`에서 사용하는 큐 구조가 같아야 합니다.
- Google Apps Script는 GPU 워커를 실행하거나 Colab 세션을 자동으로 켜 주지 않습니다. Colab 무료 GPU도 지속 실행을 보장하지 않습니다.
- Google Sheets와 Drive 원본 JSON의 공유 권한을 제한하세요. 오류 메시지·프롬프트 등 민감한 메타데이터가 포함될 수 있습니다.
- GitHub에 이 파일을 병합하는 것만으로 본인의 Google 계정에 Apps Script가 자동 설치되지는 않습니다.
