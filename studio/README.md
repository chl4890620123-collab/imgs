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

1. **LTX-Video 2B Distilled** — 빠른 미리보기와 I2V 기본 백엔드
2. **HunyuanVideo-1.5 Step-Distilled** — 중요한 인물/전투 컷 품질 백엔드
3. **Wan 2.2 TI2V-5B** — 24GB+ GPU에서 최종 시네마틱 컷
4. **FramePack** — 긴 장면/영상 연장용 선택 백엔드

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
