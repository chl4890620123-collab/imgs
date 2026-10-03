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
