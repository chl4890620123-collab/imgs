# SASEOK / Video Maker

이 저장소에는 두 가지 영상 제작 방식이 있습니다.

기존 `video_maker.py` + GitHub Actions 방식은 정지 이미지에 줌/패닝과 TTS를 합치는 가벼운 테스트 렌더러입니다.

## 《사석(死石)》 1화 — 실제 AI 모션 영상

본 제작은 **Google Colab 무료 GPU + ComfyUI + Wan 2.2 TI2V-5B**를 사용합니다. 유료 영상 생성 API를 호출하지 않습니다.

### 바로 실행

[Open in Google Colab](https://colab.research.google.com/github/chl4890620123-collab/imgs/blob/main/SASEOK_EP01_WAN22_COLAB.ipynb)

Colab에서 **런타임 → 런타임 유형 변경 → GPU**를 선택한 뒤 셀 하나를 실행합니다.

### 구성

- 1화 〈신의 한 수〉
- 총 15장면
- 총 120개의 Wan 2.2 모션 컷
- 목표 러닝타임 1,200초(20분)
- 생성 해상도 기본 832×480, 최종 편집 1280×720
- 24fps
- 서진우 / 리아 / 테오 / 카르만 캐릭터 시트 참조
- 정확한 19×19 바둑판 시작 프레임을 코드로 생성
- 체스판 / 체스말을 네거티브 프롬프트로 차단
- 흑돌→검은 갑옷, 백돌→흰 갑옷 MATCH CUT 반복
- 임시 한국어 TTS는 장면별 WAV로 분리되어 실제 성우 녹음으로 교체 가능

### 중단되어도 이어서 생성

각 AI 모션 컷은 생성 직후 Google Drive의 아래 경로에 저장됩니다.

`MyDrive/SASEOK_EP01/clips/`

무료 Colab 세션이 끊기면 같은 노트북을 다시 실행하면 됩니다. 이미 생성된 컷은 자동으로 건너뛰고 다음 컷부터 진행합니다.

모든 컷이 완료되면 최종 파일을 자동 조립합니다.

`MyDrive/SASEOK_EP01/SASEOK_EP01_WAN22_20min.mp4`

### 관련 파일

- `SASEOK_EP01_WAN22_COLAB.ipynb` — Colab 시작 노트북
- `colab/saseok_colab_runner.py` — 설치/모델/렌더/재개/최종 조립
- `colab/saseok_episode.py` — 15장면, 대사, 120컷 프롬프트
- `video_maker.py` — 기존 정지 이미지 기반 테스트 렌더러

## 기존 GitHub Actions 테스트 렌더러

1. `assets/`에 이미지를 올립니다.
2. `project.yaml`에서 장면 순서와 대사를 설정합니다.
3. GitHub Actions의 **Render Video**를 실행합니다.
4. `video-output` artifact에서 결과를 받습니다.

이 방식은 실제 AI 모션 생성이 아니라 정지 이미지 카메라 효과 테스트용입니다.


## 숏폼 공장 — 긴 영상 → 9:16 숏폼

현재 브랜치 구조에는 **유료 API 없이 동작하는 로컬 클리핑 MVP**가 포함됩니다.

- FFmpeg scene-change 감지
- 무음/발화 밀도 기반 후보 점수
- 중복 구간 제거
- 9:16 자동 center-crop
- H.264/AAC MP4 출력
- MCP에서 분석/렌더 호출 가능

이 로컬 방식은 의미 기반 AI 하이라이트 판정의 대체제가 아니라 **무료 fallback**입니다.
Open-Generative-AI 계열의 의미 기반 클리핑 provider는 선택적으로 붙일 수 있게 분리되어 있습니다.


### Studio에서 바로 사용

`python studio/app.py` 실행 후 우측의 **숏폼 공장 — 긴 영상 → 9:16**에서:

1. 원본 영상 선택
2. 후보 개수 / 숏폼 길이 지정
3. **후보 분석**으로 타임코드 확인
4. **9:16 MP4 만들기**로 `media/shorts/<원본이름>/`에 출력

CLI도 동일한 로컬 파이프라인을 사용합니다.

```bash
PYTHONPATH=studio python studio/shortform_cli.py analyze input.mp4 --count 3 --duration 30
PYTHONPATH=studio python studio/shortform_cli.py render input.mp4 --output-dir media/shorts --count 3 --duration 30
```


## 숏폼 고품질 모드

기본 클리핑보다 결과 품질을 우선할 때는 optional quality stack을 설치합니다.

```bash
python -m pip install -r studio/requirements-quality.txt
```

고품질 모드는 다음 순서로 동작합니다.

1. **faster-whisper**로 한국어 transcript + word timing 생성
2. 질문/반전/이유/숫자/핵심 문장과 문장 완결성을 이용해 후보 점수화
3. OpenCV가 있으면 얼굴 위치를 샘플링해 안전한 레이아웃 선택
4. 얼굴이 중앙에서 안정적이면 9:16 crop, 아니면 피사체를 보존하는 blur-fill
5. word timing 기반 ASS 자막 생성
6. 고화질 H.264 렌더 + loudness normalization
7. ffprobe로 해상도/길이/파일 유효성 검증
8. 각 결과와 분석 근거를 `shortform_manifest.json`에 저장

Studio에서는 **숏폼 공장 — 긴 영상 → 9:16**에서
`고화질` 또는 `최고화질`을 선택하고 **Whisper 자막 + 의미 기반 후보 분석**을 켠 뒤 실행합니다.

CLI:

```bash
PYTHONPATH=studio python studio/shortform_cli.py analyze-quality input.mp4 \
  --count 3 --duration 30 --whisper-model medium --strict-transcript

PYTHONPATH=studio python studio/shortform_cli.py render-quality input.mp4 \
  --output-dir media/shorts-quality \
  --count 3 --duration 30 --quality high \
  --whisper-model medium --strict-transcript
```

`cinematic`은 CRF와 인코더 프리셋을 더 보수적으로 사용해 파일 크기와 렌더 시간을 늘리는 대신 화질 손실을 더 줄입니다.

> 현재 자동 프레이밍은 **얼굴 위치를 분석해 crop/blur-fill 중 안전한 방식을 선택**합니다.
> 실제 인물을 따라 프레임이 좌우로 움직이는 dynamic face-follow는 원본 영상으로 검증한 뒤 추가하는 것이 안전합니다.
