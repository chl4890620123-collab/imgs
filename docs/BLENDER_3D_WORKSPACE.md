# Saseok Studio — 실제 Blender 3D 모델링과 영상 제작

이 기능은 3D처럼 보이는 이미지가 아닌 실제 Blender (.blend) 장면·메시·애니메이션 제작입니다. 기존 15장면 / 120컷 / 음성 / AI 영상 생성 기능은 유지합니다. Blender에서 렌더한 MP4는 기존 Shot 타임라인으로 연결됩니다.

## 설치와 실행

- Python 3.11 이상, FFmpeg + ffprobe
- Blender 설치: https://www.blender.org/download/ (4.x 버전 권장)
- Python 의존성: python -m pip install -r studio/requirements.txt
- 샘플 프로젝트 생성: python studio/bootstrap.py
- 앱 실행: python studio/app.py saseok_studio_project.json

Blender를 PATH에서 찾지 못할 때에는 SASEOK_BLENDER 환경변수에 blender.exe 전체 경로를 지정하세요. Windows PowerShell 예:

~~~powershell
$env:SASEOK_BLENDER="C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
python studio/app.py saseok_studio_project.json
~~~

Blender와 FFmpeg는 별도로 설치해야 합니다. ZIP에는 Blender 바이너리나 AI 모델 가중치가 포함되지 않습니다.

## 영상 편집기 사용 방법

1. 영상 생성 메뉴에서 장면과 컷을 선택합니다.
2. **3D 모델링 — 실제 Blender 편집**을 펼칩니다.
3. 모델을 쓰려면 **3D 모델 가져오기** (GLB, GLTF, FBX, OBJ)를 누릅니다.
4. **선택 컷 3D 씬 만들기**로 편집 가능한 .blend 파일을 만듭니다.
5. **Blender에서 편집** 버튼을 눌러 Blender GUI에서 모델링, 조명, 재질, 리깅, 카메라, 키프레임 및 애니메이션을 자유롭게 편집합니다. Ctrl+S로 저장합니다.
6. **첫 프레임 미리보기**로 실제 3D 렌더 PNG를 확인합니다.
7. **3D 24프레임씩 렌더**를 반복합니다. 완료된 프레임은 남고 나머지만 렌더합니다.
8. 모든 프레임이 모이면 자동으로 MP4를 만들고 해당 Shot의 visual 경로를 연결합니다. 기존 **현재 프로젝트 MP4 렌더**로 음성/자막과 합성합니다.
9. **3D → AI 시작화면**을 누르면 저장된 3D 첫 프레임을 기존 LTX 영상 생성의 시작 이미지로 지정할 수 있습니다.

기존 .blend가 있으면 프로그램은 씬을 덮어쓰지 않습니다. 새 3D 모델은 Blender에서 직접 불러오고 수정하세요. 자체 포함형 GLB를 권장합니다. GLTF/OBJ는 외부 텍스처와 .bin 등 연관 파일 경로를 확인하세요.

## CLI 실행

~~~bash
python studio/blender_3d.py init --project saseok_studio_project.json --shot S01_SH01
python studio/blender_3d.py import --project saseok_studio_project.json --shot S01_SH01 --model actor.glb
python studio/blender_3d.py build --project saseok_studio_project.json --shot S01_SH01
python studio/blender_3d.py open --project saseok_studio_project.json --shot S01_SH01
python studio/blender_3d.py preview --project saseok_studio_project.json --shot S01_SH01
python studio/blender_3d.py render --project saseok_studio_project.json --shot S01_SH01 --chunk 24
python studio/blender_3d.py reference --project saseok_studio_project.json --shot S01_SH01
~~~

## 파일 저장

~~~text
media/3d/S01_SH01/
  scene.json                   # 카메라, 조명, 초기 3D 배치
  scene.blend                  # 실제 편집 가능한 Blender 원본
  models/                     # 가져온 모델 자산
  preview.png                 # 렌더 미리보기
  frames/frame_000001.png ... # 끊겨도 남는 프레임별 체크포인트
  frames_blend_revision.txt   # 원본 수정 여부 확인
  render.mp4                  # 완성 컷, 기존 타임라인에 자동 연결
~~~

Blender에서 씬을 수정하고 다시 저장하면 이전 프레임 캐시는 무효화됩니다. 이는 서로 다른 3D 수정본의 프레임이 혼합되는 것을 방지하기 위해서입니다.

3D 렌더링은 현재 로컬 Blender CPU/GPU에서 실행됩니다. 무료 Colab의 Wan 영상 생성과는 별도의 경로입니다. 텍스트 한 줄로 고품질 캐릭터 메시를 자동 생성하는 기능은 아직 제공하지 않으며, Blender 편집기를 직접 사용합니다.

## 검증 및 시연 파일

- PYTHONPATH=studio python studio/test_blender_3d.py : 장면 JSON, 모델 경로, 프레임 무결성 검사
- PYTHONPATH=studio python studio/test_blender_runtime.py : 실제 Blender로 .blend + PNG + MP4를 제작하고 2프레임씩 이어서 저장하는 통합 검사
- GitHub Actions의 **Validate Saseok Studio**가 성공하면 작은 움직이는 블록 데모를 **saseok-blender-3d-demo** 아티팩트로 제공합니다.

데모는 기능 점검용이며 자동으로 완성된 영화 수준의 3D 캐릭터는 아닙니다.
