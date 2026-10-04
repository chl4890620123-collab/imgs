# Saseok Studio v0.1

《사석》 전용 로컬 영상 편집/성우 교체 MVP입니다. 대본을 다시 생성하지 않고 기존 1화 대본을 타임라인으로 가져옵니다.

## 현재 구현

- 캐릭터별 독립 음성 트랙
- 캐릭터 전체 AI 음성 ON/OFF
- 특정 대사만 음소거 / AI / 친구 녹음으로 교체
- 친구 WAV/MP3/M4A 선택 → 앞뒤 무음 제거 + 음량 정규화
- 캐릭터별 Gemini TTS 모델/Voice/나이감/음역/속도/감정/힘/거리감/자유 지시 조절
- AI 음성을 삭제하지 않고 유지한 채 친구 녹음을 우선 사용
- 기존 `colab/saseok_episode.py`에서 15개 장면/대사를 프로젝트로 자동 생성
- 장면별 이미지/영상 소스 + 자막 + 대사 믹스를 FFmpeg로 MP4 렌더

## 실행

Python 3.11 또는 3.12와 FFmpeg가 필요합니다.

```bash
python -m pip install -r studio/requirements.txt
python studio/bootstrap.py
python studio/app.py saseok_studio_project.json
```

Gemini 성우를 사용할 때만 API 키가 필요합니다.

Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
python studio/app.py saseok_studio_project.json
```

친구가 맡을 캐릭터는 우측에서 **친구 녹음 우선**으로 바꾸면 됩니다. 해당 인물의 AI 성우는 최종 믹스에서 빠지고, 녹음이 들어온 대사만 사용됩니다. AI 파일은 삭제하지 않으므로 언제든 복구할 수 있습니다.

## 영상 추론 백엔드

생성형 영상은 편집기와 분리된 플러그인 구조로 붙입니다.

1. **LTX-Video 2B Distilled** — 한국 빌드의 기본/고화질/시네마틱 백엔드 후보
2. **Wan 2.2 TI2V-5B** — 24GB+ GPU에서 최종 고품질 컷 후보

HunyuanVideo 계열과 HunyuanVideo 가중치에 의존하는 FramePack은 대한민국에서 해당 모델 라이선스 적용 범위 문제 때문에 한국 빌드의 실행 선택지에서 제외합니다.

20분 전체를 생성형 모델로 매번 다시 만들지 않고, 편집기는 즉시 작업하고 필요한 컷만 생성 후 교체하는 방식이 목표입니다.


## 영상 생성 설계 원칙

영상 쪽은 **쉽게 / 퀄리티 높게 / AI 호출 적게 / 세부설정은 깊게**를 기본 원칙으로 합니다.

### 쉬운 모드
장면별로 기본 화면에는 아래 세 가지만 먼저 보입니다.

- 품질: 빠르게 / 고화질 / 시네마틱
- AI 호출 예산: 장면당 몇 번까지 생성할지
- 장면 선택

기본값인 **고화질**은 장면당 2회 생성 슬롯을 사용합니다. 15장면 전체라면 최대 30회의 생성 슬롯입니다.

### 고급 모드
고급 설정을 펼치면 다음을 직접 조절할 수 있습니다.

- 추론 엔진
- 생성 해상도
- 한 번 생성 길이
- Steps / Guidance / Seed
- 동작 강도
- 캐릭터 일관성
- 카메라 지시
- 네거티브 프롬프트
- 로컬 업스케일 / 프레임 보간

### 호출을 줄이는 방식
생성형 모델 호출이 필요한 값과 로컬 편집 값을 분리합니다.

다음 변경은 기존 AI 영상을 재사용합니다.

- 자막
- 성우 교체
- BGM / 효과음
- 색감
- 줌 / 패닝
- 흔들림
- 속도
- 프레임 보간
- 업스케일

반대로 모델, seed, Steps, Guidance, 동작 강도, 캐릭터 참조 등 실제 추론 결과에 영향을 주는 값이 바뀔 때만 새 영상 생성 슬롯이 필요합니다.

`호출 계획 보기`를 누르면 현재 캐시로 재사용 가능한 컷과 새로 생성해야 할 컷의 개수를 먼저 보여줍니다.


## 감독 프롬프트

앱 상단의 **감독 프롬프트**에 자연어로 지시할 수 있습니다.

예:

```text
장면 9에서 리아가 더 빠르게 진우를 밀치고,
카메라는 낮은 각도로 따라가.
캐릭터 일관성 90, 선명도 75, 1080p.
서진우는 친구 녹음으로.
```

먼저 **변경 미리보기**로 어떤 설정이 바뀌는지 확인한 뒤 **프롬프트 적용**을 누릅니다.

알아듣는 설정은 구조화해서 적용하고, 나머지 대화/행동/연기/장면 지시는 버리지 않고
해당 장면의 `creative_prompt`에 원문 그대로 보존합니다. 이후 LTX/Hunyuan 등 영상 백엔드가
이 값을 실제 생성 지시로 사용하도록 연결할 수 있습니다.

## MCP 연결

Saseok Studio는 공식 MCP Python SDK v2 기반의 로컬 MCP 서버를 제공합니다.
MCP에서는 프로젝트 상태를 리소스로 읽고, 장면 지시/품질/성우/호출계획을 도구로 제어할 수 있습니다.

노출되는 주요 도구:

- `get_project_state`
- `preview_instruction`
- `apply_instruction`
- `set_scene_prompt`
- `set_scene_quality`
- `set_voice_mode`
- `get_generation_plan`

리소스:

- `saseok://project`
- `saseok://scene/{scene_id}`

실행:

```bash
python -m pip install -r studio/requirements.txt
python studio/bootstrap.py
python studio/mcp_server.py
```

기본 transport는 로컬 MCP 클라이언트에 적합한 stdio입니다.

다른 위치의 프로젝트 파일을 제어할 경우:

Windows PowerShell:

```powershell
$env:SASEOK_PROJECT="C:\\work\\imgs\\saseok_studio_project.json"
python studio/mcp_server.py
```

MCP 클라이언트에서는 `studio/mcp.example.json`의 command/args를 실제 저장소 경로에 맞춰 사용합니다.


## 무료 사용 기준과 라이선스

Saseok Studio 자체 편집/렌더 파이프라인은 로컬 실행을 우선합니다.

- **LTX-Video 0.9.8 weights**: 코드 저장소는 Apache-2.0이지만 모델 가중치는 **LTXV Open Weights License 0.X**. 연매출 1천만 달러 미만 개인/소규모 프로젝트는 로열티 없는 사용 범위가 있으나 사용 제한 조항을 따라야 함. 한국 프로젝트의 기본 영상 생성 후보.
- **Wan 2.2**: 모델이 Apache-2.0. 충분한 VRAM이 있을 때 고품질 컷 후보.
- **FramePack**: 코드 자체는 Apache-2.0이지만 공식 구현이 Tencent HunyuanVideo 모델 구성요소를 사용함. HunyuanVideo 모델 라이선스가 대한민국을 적용 지역에서 제외하므로 한국 빌드에서는 제외.
- **HunyuanVideo / HunyuanVideo-1.5**: Tencent Hunyuan Community License가 대한민국을 적용 지역에서 제외하므로 한국 빌드의 선택 목록에서 제외.
- **Gemini 3.8 Flash-Lite TTS**: 현재 API 무료 등급이 있으나 무료 한도/정책은 서비스 제공자가 바꿀 수 있음.
- **FFmpeg / PySide6 / MCP SDK**: 로컬 소프트웨어 구성요소. 배포 시 각 라이선스 의무는 별도 확인.

무료 모델이라고 해도 GPU 전기비, 로컬 하드웨어, Colab 무료 자원 제한은 별개입니다.
Colab 무료 GPU는 종류/시간/사용량이 보장되지 않으므로 장시간 렌더의 상시 무료 실행 환경으로 간주하지 않습니다.

## 캐릭터 / 대사 품질

`studio/character_bible.py`에 서진우, 리아, 테오, 카르만의 외형 고정점, 말투, 행동 습관,
감정 표현 규칙과 피해야 할 표현을 분리해 두었습니다. 영상 프롬프트와 대사 연출은 이 정보를 공유해야
장면마다 캐릭터가 다른 사람처럼 변하는 것을 줄일 수 있습니다.

`studio/dialogue_audit.py`는 전체 길이 대비 대사 수와 무대사/대사 희박 장면을 검사합니다.
영상의 대화량을 무작정 늘리기보다, 캐릭터가 필요한 순간에만 말하고 각 인물의 말투가 겹치지 않도록
검수하는 용도입니다.


## 연기 중심 Shot 파이프라인

Saseok Studio는 이제 장면 전체를 하나의 영상으로 늘려 쓰지 않고 **Shot 단위**로 관리합니다.
기존 15개 장면 / 120개 쇼트 정의는 프로젝트를 처음 만들 때 실제 `Shot` 타임라인으로 변환됩니다.
이전 버전 프로젝트도 열면 장면의 `shot_prompts`를 기준으로 자동 마이그레이션합니다.

대사는 자막 타이밍만 쓰지 않습니다. `studio/performance.py`가 각 대사에 대해:

- 말하기 전 시선/호흡/몸 준비
- 실제 발화와 입 움직임
- 말이 끝난 뒤 표정과 몸의 잔동작
- 다음 화자의 무언 반응

을 시간축 이벤트로 만듭니다. 이 이벤트와 캐릭터 바이블, 쇼트 행동, 감독 프롬프트,
카메라 지시를 합쳐 쇼트별 LTX 프롬프트를 190단어 이내로 구성합니다.

호출 수를 줄이기 위해 장면의 모든 쇼트를 무조건 다시 생성하지 않습니다.
`AI 호출 예산/장면`만큼 대사와 중요한 행동이 겹치는 쇼트를 우선 선택하고,
완료된 쇼트에는 품질 점수와 오류 플래그를 저장해 **얼굴 드리프트/신체 오류/립싱크/연속성 문제**가 있는 쇼트만 재생성할 수 있습니다.

### LTX 직접 실행

Studio의 **선택 컷 LTX 생성** 버튼은 로컬 LTX-Video 설치와 직접 연결됩니다.

Windows PowerShell 예:

```powershell
$env:LTX_VIDEO_HOME="C:\\AI\\LTX-Video"
$env:LTX_PYTHON="C:\\AI\\LTX-Video\\env\\Scripts\\python.exe"
python studio/app.py
```

`LTX_PYTHON`을 생략하면 Studio가 실행 중인 Python을 사용합니다.
GPU가 없거나 LTX 설치가 확인되지 않으면 생성 버튼은 이유를 안내하고 실행하지 않습니다.

생성 완료 파일은 `media/generated/<SHOT_ID>.mp4`에 저장되고 해당 Shot의 `visual`로 자동 연결됩니다.
최종 렌더는 Shot별 영상을 순서대로 이어 붙이므로 6초 영상을 90초 장면 전체에 늘여 쓰지 않습니다.

### MCP 추가 도구

- `get_scene_performance_plan`: 대사/시선/반응/행동 타임라인 확인
- `get_shot_generation_prompt`: 실제 LTX에 전달되는 쇼트 프롬프트 확인
- `set_shot_quality`: 품질 점수와 오류 플래그 기록
- `get_regeneration_plan`: 재생성이 필요한 쇼트만 반환
- `run_ltx_shot`: CUDA와 LTX가 준비된 머신에서 한 쇼트 실제 생성


## Colab GPU 백그라운드 워커

Studio는 Google Drive 동기화 폴더를 작업 큐로 사용해 Colab GPU를 원격 워커처럼 쓸 수 있습니다.

### 1. 로컬 Studio

앱의 **Colab GPU 백그라운드**에서 Google Drive에 동기화되는 `SASEOK_GPU_QUEUE` 폴더를 선택합니다.

환경변수로 고정할 수도 있습니다.

Windows PowerShell:

```powershell
$env:SASEOK_COLAB_QUEUE_ROOT="G:\\내 드라이브\\SASEOK_GPU_QUEUE"
python studio/app.py saseok_studio_project.json
```

Studio에서 **선택 컷 Colab 큐 등록**을 누르면 다음 구조가 자동 생성됩니다.

```text
SASEOK_GPU_QUEUE/
  jobs/
    queued/
    running/
    done/
    failed/
    cancelled/
  assets/
  outputs/
    shots/
    logs/
  workers/
    heartbeat/
```

작업 JSON에는 쇼트 프롬프트, 대사 기반 연기 정보가 반영된 최종 프롬프트,
해상도/FPS/seed/negative prompt와 필요한 참조 파일만 들어갑니다.

### 2. Colab

저장소 루트의 **SASEOK_COLAB_GPU_WORKER.ipynb**를 Colab에서 열고 GPU 런타임으로 실행합니다.

노트북은:

1. Google Drive 마운트
2. `imgs` 저장소 갱신
3. 공식 `Lightricks/LTX-Video` 설치
4. GPU 확인
5. `colab/drive_worker.py` 실행

순서로 진행됩니다.

워커가 살아 있는 동안 Drive의 `queued` 작업을 가져가 LTX-Video로 생성하고
`outputs/shots/<JOB_ID>.mp4`에 저장합니다. Studio는 5초 간격으로 상태를 확인하고
완료 영상을 `media/generated/<SHOT_ID>.mp4`로 자동 복사해 타임라인에 연결합니다.

### 3. 백그라운드 상태

앱에서는 다음 상태를 구분합니다.

- `queued`: Colab 대기
- `generating`: Colab 생성 중
- `ready`: 결과 자동 반영 완료
- `failed`: 재시도 필요

Colab은 heartbeat를 `workers/heartbeat/*.json`에 기록합니다.
90초 이상 갱신되지 않은 워커는 Studio에서 오프라인으로 표시됩니다.

실행 중 취소 요청도 큐 JSON으로 전달되며 워커가 LTX 프로세스를 종료합니다.
실패 작업은 워커가 설정된 횟수까지 자동 재시도하고, Studio/MCP에서도 수동 재시도할 수 있습니다.

### 4. MCP

추가된 원격 GPU 도구:

- `submit_colab_shot`
- `get_colab_jobs`
- `sync_colab_results`
- `retry_colab_job`
- `cancel_colab_job`

따라서 MCP 클라이언트에서도
**쇼트 선택 → Colab 등록 → 워커 상태 확인 → 결과 동기화 → 실패 컷만 재시도**
흐름을 제어할 수 있습니다.

> Colab은 상시 서버가 아닙니다. 런타임이 끊기면 워커 heartbeat가 멈추며,
> 다시 노트북의 Worker 셀을 실행하면 남아 있는 queued 작업부터 이어서 처리합니다.
