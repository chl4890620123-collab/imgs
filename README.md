# GitHub Video Maker

GitHub 저장소를 무료 영상 렌더링 서버처럼 사용하는 프로젝트입니다.

## 사용법
1. `assets/`에 JPG/PNG 이미지를 올립니다.
2. `project.yaml`에서 이미지 경로, 한국어 대사, 장면 길이를 작성합니다.
3. GitHub의 **Actions → Render Video → Run workflow**를 실행합니다.
4. 완료 후 **Artifacts → video-output**에서 MP4를 받습니다.

이미지와 대본을 push하면 자동 실행됩니다.

## 영상 효과
정지 이미지에 천천히 확대되는 Ken Burns 효과와 페이드 인/아웃을 적용하고 Microsoft Edge TTS로 한국어 음성을 생성한 뒤 FFmpeg로 MP4를 합성합니다.

## 기본 음성
`ko-KR-InJoonNeural`

## 주의
예제는 `assets/scene1.jpg`, `assets/scene2.jpg`를 기대합니다. 실제 이미지를 추가한 후 렌더링하세요.
