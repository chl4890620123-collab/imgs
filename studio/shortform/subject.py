from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .clipping import Highlight


@dataclass(frozen=True)
class FaceTrackPoint:
    at: float
    x: float

    def to_dict(self) -> dict:
        return {"at": self.at, "x": self.x}


@dataclass(frozen=True)
class LayoutDecision:
    layout: str
    confidence: float
    reason: str
    detected_ratio: float = 0.0
    mean_face_x: float | None = None
    face_x_spread: float | None = None
    track: tuple[FaceTrackPoint, ...] = ()
    source_aspect: float | None = None


def _smooth(points: list[FaceTrackPoint], alpha: float = 0.34) -> tuple[FaceTrackPoint, ...]:
    if not points:
        return ()
    out: list[FaceTrackPoint] = []
    state = points[0].x
    for point in points:
        state = state * (1.0 - alpha) + point.x * alpha
        out.append(FaceTrackPoint(point.at, max(0.0, min(1.0, state))))
    return tuple(out)


def recommend_layout(video: str | Path, clip: Highlight) -> LayoutDecision:
    """Choose crop, dynamic face-follow, or blur-fill.

    Face-follow is enabled only when OpenCV detects the dominant face in most
    sampled frames. Weak/inconsistent detection deliberately falls back to
    blur-fill instead of risking an aggressive crop.
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

    frame_w = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    frame_h = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    source_aspect = frame_w / frame_h if frame_w > 0 and frame_h > 0 else None
    # A source narrower than the target 9:16 frame cannot be safely cropped to
    # the target without inventing pixels at the sides.
    if source_aspect is not None and source_aspect < (9.0 / 16.0):
        cap.release()
        return LayoutDecision(
            "blur",
            0.9,
            "원본이 9:16보다 좁아 전체 화면 보존",
            source_aspect=source_aspect,
        )

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    sample_count = max(10, min(40, int(clip.duration / 0.6) + 1))
    raw: list[FaceTrackPoint] = []

    for idx in range(sample_count):
        ratio = idx / max(1, sample_count - 1)
        rel = clip.duration * ratio
        t = clip.start + rel
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(
            gray,
            scaleFactor=1.10,
            minNeighbors=5,
            minSize=(40, 40),
        )
        if len(faces) == 0:
            continue
        x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
        raw.append(
            FaceTrackPoint(
                at=rel,
                x=(x + w / 2.0) / max(1.0, frame.shape[1]),
            )
        )
    cap.release()

    detected_ratio = len(raw) / sample_count
    if not raw:
        return LayoutDecision(
            "blur",
            0.72,
            "얼굴을 안정적으로 찾지 못해 전체 화면 보존",
            detected_ratio=0.0,
            source_aspect=source_aspect,
        )

    track = _smooth(raw)
    positions = [x.x for x in track]
    mean_x = sum(positions) / len(positions)
    spread = max(positions) - min(positions)
    centered = 0.36 <= mean_x <= 0.64
    stable = spread <= 0.12

    if detected_ratio >= 0.65 and len(track) >= 4:
        if centered and stable:
            return LayoutDecision(
                "crop",
                min(0.97, 0.66 + detected_ratio * 0.30),
                "얼굴이 중앙에서 안정적: 고밀도 9:16 crop",
                detected_ratio,
                mean_x,
                spread,
                track,
                source_aspect,
            )
        return LayoutDecision(
            "follow",
            min(0.94, 0.62 + detected_ratio * 0.30),
            "얼굴 검출이 충분하고 이동/비중앙: 부드러운 face-follow crop",
            detected_ratio,
            mean_x,
            spread,
            track,
            source_aspect,
        )

    return LayoutDecision(
        "blur",
        min(0.92, 0.62 + detected_ratio * 0.2),
        "얼굴 검출 비율이 낮아 피사체 보존 blur-fill",
        detected_ratio,
        mean_x,
        spread,
        track,
        source_aspect,
    )
