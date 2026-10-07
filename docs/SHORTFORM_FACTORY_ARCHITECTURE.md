# Shortform Factory Foundation

## 목표

기존 `Saseok Studio`의 장점(Shot 타임라인, 캐릭터/대사, Colab GPU 큐, 캐시, 품질 재생성, MCP)을 유지하면서,
Open-Generative-AI에서 확인한 **Image / Video / Audio / AI Clipping / Motion / Lip Sync / Cinema / Workflow / Agent / MCP**
기능 범주를 숏폼 제작 흐름으로 묶는다.

중요한 원칙은 "외부 프로젝트를 통째로 이식"하는 것이 아니라 **기능을 독립 단계와 provider로 분리**하는 것이다.
Open-Generative-AI는 MIT이지만 실제 클라우드 모델 호출은 MuAPI 등 별도 서비스 정책/비용을 따르므로,
기본 라우팅은 local-first이고 클라우드는 opt-in provider로 둔다.

## 사용자 흐름

### 1. 새 숏폼 생성

```text
아이디어/대본/이미지
  -> 구성/Shot 계획
  -> 이미지/영상 생성
  -> 모션/카메라
  -> 음성
  -> 립싱크(선택)
  -> 자막
  -> 로컬 후처리
  -> 품질검사
  -> 9:16 최종 렌더
```

### 2. 긴 영상에서 숏폼 추출

```text
원본 영상
  -> AI Clipping 후보
  -> 9:16 자동 리프레임
  -> 자막
  -> 강조/컷 편집
  -> 품질검사
  -> 렌더
```

## 구조

```text
studio/
  shortform/
    __init__.py
    feature_catalog.py   # 지원 기능과 준비 상태
    models.py            # 입력/작업/파이프라인 데이터 모델
    planner.py           # 요청 -> 실행 단계 계획
    providers.py         # local/cloud provider 계약
```

기존 모듈은 그대로 재사용한다.

```text
studio/project.py             -> 프로젝트/Shot
studio/prompt_engine.py       -> 자연어 감독 지시
studio/performance.py         -> 연기/대사 타임라인
studio/ltx_runner.py          -> 로컬 영상 생성
studio/remote_jobs.py         -> Colab GPU 큐
studio/video_cache.py         -> 재생성 방지
studio/quality_review.py      -> 불량 Shot 재생성
studio/render.py              -> FFmpeg 최종 출력
studio/mcp_server.py          -> 외부 에이전트 제어
```

## 기능 매핑

| 기능 | 현재 imgs | 이번 구조에서 처리 |
|---|---|---|
| Image | 부분적/참조이미지 중심 | provider 단계로 분리 |
| Video | LTX + Colab | 기존 코드 재사용 |
| Audio/TTS | Gemini + 외부 녹음 | 기존 코드 재사용 |
| AI Clipping | 미구현 | 독립 `clip_detect` 단계 |
| Motion | 프롬프트/Shot 기반 | 기존 프롬프트 + provider |
| Lip Sync | 미구현 | 독립 `lip_sync` 단계 |
| Cinema controls | camera_prompt 등 일부 | 렌즈/초점/DOF 메타 확장 예정 |
| Workflow | 코드 흐름으로 존재 | `PipelinePlan`으로 명시 |
| Agent | 감독 프롬프트/MCP 일부 | planner 위에서 실행 |
| MCP | 구현됨 | 숏폼 계획/실행 도구 추가 예정 |

## Provider 정책

1. **local-first**
   - FFmpeg, 기존 LTX, 로컬/Colab GPU를 우선.
2. **cloud-opt-in**
   - Open-Generative-AI/MuAPI 같은 클라우드 기능은 명시적으로 provider를 선택했을 때만 호출.
3. **호출 비용 분리**
   - 자막/크롭/색감/속도/오디오 믹스는 AI 생성 재호출 금지.
4. **캐시 우선**
   - 생성 파라미터가 동일하면 기존 Shot 재사용.
5. **실패 단위 최소화**
   - 전체 영상을 다시 만들지 않고 실패한 단계/Shot만 재실행.

## 1차 성공 기준

- 생성형 숏폼 계획과 클리핑 숏폼 계획을 코드로 만들 수 있다.
- 각 단계에 provider(local/cloud/auto)를 지정할 수 있다.
- 기능의 실제 준비 상태를 코드에서 거짓 없이 구분한다.
- 기존 Studio 테스트를 깨뜨리지 않는다.
- 실제 유료 API 호출 없이 테스트 가능하다.

## 다음 구현 순서

1. Planner를 Studio UI와 MCP에 노출
2. 긴 영상 `clip_detect` + 9:16 reframe 구현
3. local image provider 연결
4. lip-sync provider 연결
5. Cinema 메타(렌즈/초점/DOF) -> 영상 프롬프트 연결
6. 선택적 MuAPI/Open-Generative-AI 호환 provider 추가
