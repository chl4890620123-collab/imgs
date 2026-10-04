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
