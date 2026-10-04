from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg가 필요합니다. 설치 후 PATH에 ffmpeg를 추가해 주세요.")
    return exe


def prepare_recording(src: str | Path, dst: str | Path) -> Path:
    """Trim leading/trailing silence and normalize a friend's recording."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    filt = (
        "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB:"
        "stop_periods=-1:stop_duration=0.08:stop_threshold=-45dB,"
        "loudnorm=I=-16:TP=-1.5:LRA=11"
    )
    subprocess.run([
        ffmpeg(), "-y", "-i", str(src), "-vn", "-af", filt,
        "-ar", "48000", "-ac", "1", str(dst)
    ], check=True)
    return dst
