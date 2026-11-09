"""Drive-safe checkpoint helpers for short AI motion clips.

No CUDA or model imports: CPU-side status checks and validation can run
without consuming a Colab GPU session.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov", ".mkv")


def is_valid_video(path: str | Path, *, minimum_bytes: int = 8192) -> bool:
    """Require a readable non-empty video stream before treating a file as done."""
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size < minimum_bytes:
            return False
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,width,height:format=duration",
                "-of", "json", str(path),
            ],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if result.returncode != 0:
            return False
        payload = json.loads(result.stdout)
        duration = float(payload.get("format", {}).get("duration") or 0)
        streams = payload.get("streams", [])
        return duration >= 0.2 and any(
            s.get("codec_type") == "video"
            and int(s.get("width") or 0) > 0
            and int(s.get("height") or 0) > 0
            for s in streams
        )
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return False


def valid_shot(clips_root: str | Path, scene_id: int, shot_idx: int) -> Path | None:
    directory = Path(clips_root) / f"scene_{scene_id:02d}"
    for extension in VIDEO_EXTENSIONS:
        candidate = directory / f"shot_{shot_idx:02d}{extension}"
        if is_valid_video(candidate):
            return candidate
    return None


def episode_progress(episode: dict, clips_root: str | Path) -> tuple[int, int]:
    finished = 0
    total = 0
    for scene in episode["scenes"]:
        for idx in range(1, len(scene["shots"]) + 1):
            total += 1
            finished += valid_shot(clips_root, scene["id"], idx) is not None
    return finished, total


def persist_validated_clip(source: str | Path, destination: str | Path) -> Path:
    """Copy to Drive via a hidden temporary file, validate, then commit."""
    source, destination = Path(source), Path(destination)
    if not is_valid_video(source):
        raise ValueError(f"Generated video is unreadable: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.stem}.{os.getpid()}.part"
    try:
        shutil.copy2(source, temporary)
        if not is_valid_video(temporary):
            raise ValueError(f"Drive copy failed video validation: {destination}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
