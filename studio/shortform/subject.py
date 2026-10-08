from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .clipping import Highlight


@dataclass(frozen=True)
class LayoutDecision:
    layout: str
    confidence: float
    reason: str
    detected_ratio: float = 0.0
    mean_face_x: float | None = None
    face_x_spread: float | None = None


def recommend_layout(video: str | Path, clip: Highlight) -> LayoutDecision:
    """Choose crop only when a face is stably near center; otherwise preserve framing.

    OpenCV is optional. Without it we deliberately choose blur-fill instead of a
    blind center crop, because cutting off an off-center speaker is worse quality.
    """
    try:
        import cv2
    except Exception:
        return LayoutDecision(
            layout="blur",
            confidence=0.65,
            reason="OpenCV 없음: 피사체 절단을 피하기 위해 blur-fill 사용",
        )

    source = str(Path(video).expanduser().resolve())
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        return LayoutDecision("blur", 0.5, "영상 프레임 분석 실패: 안전한 blur-fill 사용")

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    sample_count = 12
    positions: list[float] = []
    for idx in range(sample_count):
        ratio = idx / max(1, sample_count - 1)
        t = clip.start + clip.duration * ratio
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(40, 40))
        if len(faces) == 0:
            continue
        x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
        positions.append((x + w / 2.0) / max(1.0, frame.shape[1]))
    cap.release()

    detected_ratio = len(positions) / sample_count
    if not positions:
        return LayoutDecision(
            "blur",
            0.7,
            "얼굴을 안정적으로 찾지 못해 전체 화면 보존",
            detected_ratio=0.0,
        )

    mean_x = sum(positions) / len(positions)
    spread = max(positions) - min(positions)
    centered = 0.34 <= mean_x <= 0.66
    stable = spread <= 0.18
    enough = detected_ratio >= 0.42

    if centered and stable and enough:
        confidence = min(0.95, 0.55 + detected_ratio * 0.35)
        return LayoutDecision(
            "crop",
            confidence,
            "얼굴이 중앙 부근에서 안정적: 몰입감 높은 세로 crop",
            detected_ratio,
            mean_x,
            spread,
        )

    return LayoutDecision(
        "blur",
        min(0.92, 0.62 + detected_ratio * 0.2),
        "얼굴 위치가 불안정/비중앙: 피사체 보존 blur-fill",
        detected_ratio,
        mean_x,
        spread,
    )
