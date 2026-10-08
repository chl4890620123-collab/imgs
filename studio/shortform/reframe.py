from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .clipping import Highlight
from .quality import get_quality_preset


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


def blur_fill_filter(width: int = 1080, height: int = 1920, unsharp_amount: float = 0.2) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("width/height는 양수여야 합니다.")
    amount = max(0.0, min(1.0, float(unsharp_amount)))
    return (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=24:2,eq=brightness=-0.10:saturation=0.88[bgv];"
        f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgv];"
        "[bgv][fgv]overlay=(W-w)/2:(H-h)/2,"
        f"setsar=1,unsharp=5:5:{amount}:5:5:0[base]"
    )


def _ass_path(path: Path) -> str:
    # FFmpeg/libass filter escaping for common Windows/POSIX paths.
    value = path.resolve().as_posix()
    return value.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def render_vertical_clip(
    source: str | Path,
    highlight: Highlight,
    output: str | Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    crf: int = 19,
    layout: str = "crop",
    quality: str | None = None,
    subtitles_ass: str | Path | None = None,
) -> Path:
    src = Path(source)
    out = Path(output)
    if not src.exists():
        raise FileNotFoundError(src)
    if highlight.duration <= 0:
        raise ValueError("highlight 길이가 0보다 커야 합니다.")
    if layout not in {"crop", "blur"}:
        raise ValueError("layout은 crop/blur 중 하나여야 합니다.")

    if quality:
        preset = get_quality_preset(quality)
        width, height, fps, crf = preset.width, preset.height, preset.fps, preset.crf
        encoder_preset = preset.encoder_preset
        audio_bitrate = preset.audio_bitrate
        loudnorm = preset.loudnorm
        unsharp = preset.unsharp_amount
    else:
        encoder_preset = "medium"
        audio_bitrate = "160k"
        loudnorm = False
        unsharp = 0.20

    out.parent.mkdir(parents=True, exist_ok=True)

    if layout == "blur":
        filter_complex = blur_fill_filter(width, height, unsharp)
    else:
        filter_complex = (
            f"[0:v]{vertical_filter(width, height)},"
            f"unsharp=5:5:{unsharp}:5:5:0[base]"
        )

    video_label = "base"
    ass_path = Path(subtitles_ass) if subtitles_ass else None
    if ass_path:
        if not ass_path.exists():
            raise FileNotFoundError(ass_path)
        filter_complex += f";[base]ass='{_ass_path(ass_path)}'[vout]"
        video_label = "vout"

    cmd = [
        _ffmpeg(), "-y",
        "-i", str(src),
        "-ss", f"{highlight.start:.3f}",
        "-t", f"{highlight.duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", f"[{video_label}]",
        "-map", "0:a?",
        "-r", str(max(1, int(fps))),
        "-c:v", "libx264",
        "-preset", encoder_preset,
        "-crf", str(max(0, min(51, int(crf)))),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
    ]
    if loudnorm:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += ["-movflags", "+faststart", str(out)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "vertical clip render failed")[-4000:])
    if not out.exists() or out.stat().st_size <= 0:
        raise RuntimeError("숏폼 렌더 결과가 생성되지 않았습니다.")
    return out
