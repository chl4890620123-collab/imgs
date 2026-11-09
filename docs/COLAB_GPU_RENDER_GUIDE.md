# 《사석》 Colab GPU 렌더 최적화 (2026-11)

기존 15장면, 120컷, 캐릭터 참조, 대사, 바둑판, 프롬프트는 그대로 사용합니다. AI 움직임 생성만 Colab GPU에서 하고, 컷 검증과 최종 음성·FFmpeg 합성은 CPU로도 실행할 수 있습니다.

## 실행

1. [Colab 노트북](https://colab.research.google.com/github/chl4890620123-collab/imgs/blob/main/SASEOK_EP01_WAN22_COLAB.ipynb)을 엽니다.
2. **런타임 → 런타임 유형 변경 → GPU**를 선택합니다.
3. 노트북 셀을 실행합니다. 새로 생성한 컷은 Google Drive의 `MyDrive/SASEOK_EP01/clips/`에 검증 후 저장됩니다.
4. Colab이 종료되거나 **기본 2컷 한도**에 도달하면 같은 셀을 재실행합니다. 완료된 정상 MP4는 재생성하지 않습니다.
5. 모든 120컷이 모이면 자동으로 장면·음성을 합성합니다.

기본값: `SASEOK_PROFILE=auto`, `SASEOK_MAX_SHOTS=2`, `SASEOK_SHOT_RETRIES=2`, `SASEOK_SHOT_TIMEOUT_MINUTES=45`, `SASEOK_MAX_BATCH_MINUTES=55`.

노트북 실행 셀의 맨 위에서 다음처럼 환경변수를 변경할 수 있습니다.

```python
import os
os.environ["SASEOK_PROFILE"] = "balanced" # auto | preview | balanced | quality
os.environ["SASEOK_MAX_SHOTS"] = "2"      # 한번 실행할 생성 컷 수
os.environ["SASEOK_SHOT_RETRIES"] = "2"   # 컷 실패 시 재시도 횟수
os.environ["SASEOK_SHOT_TIMEOUT_MINUTES"] = "45"  # 한 컷 최대 대기시간
os.environ["SASEOK_MAX_BATCH_MINUTES"] = "55"    # 한번 실행의 렌더 시간 예산
```

| 프로필 | 해상도 | 생성 프레임 | 샘플링 단계 | 용도 |
|---|---|---:|---:|---|
| preview | 512×288 | 49 | 8 | 매우 빠른 구도·동작 사전 점검 |
| balanced | 640×352 | 81 | 14 | T4 등 16GB 이하 GPU 기본 |
| quality | 832×480 | 121 | 20 | 성능 좋은 GPU 또는 고화질 우선 |
| auto | VRAM 기반 선택 | — | — | 16GB 이하이면 balanced, 그 외 quality |

모두 생성 후 1280×720로 편집하지만 업스케일은 실제 디테일을 늘려 주지 않습니다. balanced의 최종 화질은 quality보다 낮을 수 있습니다. Wan 모델의 5B 구조상 T4에서 balanced도 느리거나 메모리 부족이 날 수 있습니다.

### GPU 없이 최종 합성만 다시 실행

120컷이 모두 Google Drive에 저장된 다음에는 Colab의 CPU 런타임에서도 가능합니다. 노트북의 실행 셀 초반에 다음 환경변수를 넣으세요.

```python
os.environ["SASEOK_ASSEMBLE_ONLY"] = "1"
```

또는 Drive가 마운트되어 있고 저장소가 체크아웃되어 있을 때:

```bash
python /content/imgs/colab/saseok_colab_runner.py --assemble-only
```

파일 검사·음성·FFmpeg 합성만 수행하며, ComfyUI 모델을 다운로드하거나 CUDA를 시작하지 않습니다. 전체 컷이 없으면 부족한 수를 표시하고 중단합니다.

## 한 컷씩 GPU 호출하고 즉시 저장하기

이제 긴 120컷 일괄 처리 대신 **한 번의 GPU 호출로 한 컷 생성 → MP4 검사 → Drive에 저장 → 상태 기록 → 다음 컷 호출**합니다. Colab 노트북 셀 한 번에는 기본 최대 2컷만 요청합니다. 작은 작업이 완성될 때마다 진행 결과가 남으므로 전체 작업이 중단되어도 이전 성공 컷을 다시 만들 필요가 없습니다.

- `MyDrive/SASEOK_EP01/clips/scene_XX/shot_YY.mp4`: 검증된 영상
- `MyDrive/SASEOK_EP01/render_state/scene_XX_shot_YY.json`: 컷별 `running`, `done`, `failed` 상태, 시도 횟수 및 렌더 시간
- `MyDrive/SASEOK_EP01/render_state/last_batch.json`: 최근 배치의 진행률, 중지 이유
- `MyDrive/SASEOK_EP01/saseok_run.log`: 전체 실행 로그. 재실행 시 **덮어쓰지 않고 추가**합니다.

GPU 호출이 45분을 넘으면 해당 호출을 중지하고 실패로 기록합니다. 앞서 저장된 클립에는 영향이 없습니다. 55분 배치 예산을 다 써가면 다음 컷은 시작하지 않습니다. 한 컷이 실제로 더 오래 걸리는 하드웨어라면 시간 제한을 조절해야 합니다. 45/55분은 성공 보장이나 실제 소요시간 예측이 아니라 **안전용 상한값**입니다.

**중요:** ComfyUI 모델을 로드한 뒤 이미지를 생성하는 한 컷 내부 연산을 중간 프레임별로 자동 저장하는 것은 아닙니다. 한 컷이 끝나야 검증된 MP4로 저장합니다. Colab 세션이 꺼져 있으면 알아서 GPU를 다시 켜거나 예약 실행할 수 없으며, 같은 셀을 다시 실행해야 합니다. 자주 세션을 재시작하면 모델 로드 오버헤드로 **전체 처리 시간이 늘 수 있으므로**, 안정성과 속도는 실제 GPU 실행 로그를 보고 조절하는 것이 좋습니다.

## 개선된 복구와 한계

- 단순히 `shot_*.mp4`가 **존재하는 것**만으로 완료 처리하지 않습니다. `ffprobe`로 영상 스트림, 길이, 크기를 확인합니다.
- GPU가 만든 컷을 Drive의 숨김 임시 파일로 복사하고, 복사본도 검증한 뒤 최종 파일명으로 바꿉니다. 복사 중 중단되어도 잘못된 파일이 완료로 표시되지 않습니다.
- 실패 컷은 최대 2회 재시도합니다. 다른 정상 컷은 Drive에 남습니다.
- 동일 Colab 런타임에서는 가상환경, 주요 Python 의존성 재설치를 최대한 생략합니다.
- Colab 연결이 완전히 끊기면 인스턴스는 종료됩니다. Google 무료 GPU가 PC를 끈 상태에서도 스스로 계속 실행되는 서버는 **아닙니다**.
- Colab 런타임을 새로 할당받으면 큰 모델을 다시 다운로드할 수 있습니다. `SASEOK_MODEL_CACHE`는 선택형 캐시 설정이며, Drive를 캐시로 쓰면 복사·읽기 오버헤드와 저장공간이 필요합니다.
- **최적화 구현·CPU 무결성 검증**과 **실제 Colab에서 120컷 GPU 렌더 완료**는 서로 다릅니다. 실제 GPU 시간·품질은 Colab에서 측정해야 합니다.

### 문제 발생 시

- `PIL._typing` ImportError: 격리된 Python 3.12 venv를 사용합니다. 호환성 실패 시 런타임의 `/content/saseok-venv`를 지우고 새로 실행합니다.
- GPU CUDA OOM: `SASEOK_PROFILE=preview` 또는 다른 GPU로 조정하고 다시 실행합니다.
- 컷이 계속 실패: Drive의 `saseok_run.log`와 Colab의 `/content/comfyui.log`를 확인합니다.
- 재실행이 오래 걸림: 새 런타임에서는 모델 다운로드, Colab 설치, 모델 로드 시간이 여전히 필요합니다.

### CPU 자동 테스트

```bash
python -m unittest discover -s colab -p "test_render_integrity.py" -v
```
