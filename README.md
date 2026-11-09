# SASEOK / Video Maker

## Saseok Studio 3D — 편집 가능한 Blender 3D 영상 제작

**실제 3D 메시/재질/키프레임/카메라 편집**이 가능한 Blender 파일(.blend)을 기존 Saseok Studio 영상 컷에 연결했습니다. 3D 프레임은 24장씩 끊어 저장하고, MP4로 합쳐 대사·자막 타임라인으로 넘길 수 있습니다.

- **Windows 빠른 실행:** `START_SASEOK_STUDIO_3D.bat` (Python 3.11+, Blender, FFmpeg 설치 필요)
- **macOS/Linux:** `bash start_saseok_studio_3d.sh`
- **자세한 설치·사용법:** [3D 모델링 안내](docs/BLENDER_3D_WORKSPACE.md)
- **GitHub Actions:** 자동검증된 시연용 `.blend` · PNG · MP4 아티팩트 다운로드 가능

기존 Wan 2.2 / Colab AI 영상 생성 기능과는 **별도로 동작하는 실제 로컬 3D 렌더 기능**입니다. 3D 캐릭터 메시를 자연어만으로 자동 생성하는 기능은 아닙니다.


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

### GPU 비용·대기시간 개선 (2026-11)

기존 15장면·120컷·대사와 프롬프트를 유지하면서 Colab 작업을 개선했습니다.

- 소형 GPU(T4 등): `SASEOK_PROFILE=auto`가 640×352 / 81프레임 / 14단계의 균형 모드를 선택합니다. `quality`로 기존 832×480 설정을 유지할 수도 있습니다.
- 기본 **2컷씩 짧게 GPU 호출**(`SASEOK_MAX_SHOTS`로 조절), 매 컷 저장·검증, 실패 시 재시도. 한 컷당 최대 대기시간과 실행 시간 예산으로 장시간 정지 방지.
- `MyDrive/SASEOK_EP01/render_state/`에 각 컷의 실행/완료/실패 상태와 마지막 배치 진행률을 보존. 재실행 로그는 덮어쓰지 않고 이어서 기록.
- 모든 컷이 있으면 GPU·모델 설치 없이 CPU만으로 최종 음성·FFmpeg 합성.
- 같은 런타임에서 Python·ComfyUI 의존성 반복 설치를 가능한 한 생략.
- **자세한 실행·설정·한계:** [Colab GPU 최적화 가이드](docs/COLAB_GPU_RENDER_GUIDE.md)

> Colab의 무료 GPU는 연결이 끊긴 뒤 백그라운드에서 계속 도는 서버가 아닙니다. 대용량 모델의 최초 다운로드와 실제 영상 생성 시간은 여전히 필요합니다.

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

> 자동 프레이밍은 얼굴 검출 신뢰도에 따라 **crop / dynamic face-follow / blur-fill** 중 하나를 선택합니다.
> face-follow는 검출 비율이 충분할 때만 켜지고, 불안정하면 피사체 절단을 피하기 위해 blur-fill로 자동 후퇴합니다.
> 실제 원본 영상에서는 인물 수·카메라 움직임에 따라 추적 결과를 한 번 더 검수하는 것을 권장합니다.
