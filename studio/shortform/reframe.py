from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .clipping import Highlight


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg 실행 파일을 찾을 수 없습니다.")
    return path


def vertical_filter(width: int = 1080, height: int = 1920) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("width/height는 양수여야 합니다.")
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )


def render_vertical_clip(
    source: str | Path,
    highlight: Highlight,
    output: str | Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    crf: int = 19,
) -> Path:
    src = Path(source)
    out = Path(output)
    if not src.exists():
        raise FileNotFoundError(src)
    if highlight.duration <= 0:
        raise ValueError("highlight 길이가 0보다 커야 합니다.")

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y",
        "-ss", f"{highlight.start:.3f}",
        "-i", str(src),
        "-t", f"{highlight.duration:.3f}",
        "-vf", vertical_filter(width, height),
        "-r", str(max(1, int(fps))),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", str(max(0, min(51, int(crf)))),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "vertical clip render failed")[-3000:])
    if not out.exists() or out.stat().st_size <= 0:
        raise RuntimeError("숏폼 렌더 결과가 생성되지 않았습니다.")
    return out
