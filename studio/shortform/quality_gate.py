from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputInspection:
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool
    size_bytes: int

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "fps": self.fps,
            "has_audio": self.has_audio,
            "size_bytes": self.size_bytes,
        }


def inspect_output(path: str | Path) -> OutputInspection:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe 실행 파일을 찾을 수 없습니다.")
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)

    result = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_streams", "-show_format",
            "-of", "json",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    video = next((x for x in data.get("streams", []) if x.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("출력 파일에 비디오 스트림이 없습니다.")

    rate = str(video.get("avg_frame_rate") or "0/1")
    num, den = rate.split("/", 1)
    fps = float(num) / max(float(den), 1.0)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    has_audio = any(x.get("codec_type") == "audio" for x in data.get("streams", []))
    return OutputInspection(
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        duration=duration,
        fps=fps,
        has_audio=has_audio,
        size_bytes=source.stat().st_size,
    )


def validate_vertical_output(
    path: str | Path,
    *,
    expected_width: int,
    expected_height: int,
    min_duration: float = 1.0,
) -> OutputInspection:
    info = inspect_output(path)
    errors = []
    if (info.width, info.height) != (expected_width, expected_height):
        errors.append(f"해상도 {info.width}x{info.height}")
    if info.duration < min_duration:
        errors.append(f"길이 {info.duration:.2f}s")
    if info.size_bytes <= 1000:
        errors.append("파일 크기가 너무 작음")
    if errors:
        raise RuntimeError("숏폼 품질 검증 실패: " + ", ".join(errors))
    return info
