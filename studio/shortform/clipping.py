from __future__ import annotations

import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Highlight:
    start: float
    end: float
    score: float
    speech_ratio: float
    scene_density: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return asdict(self) | {"duration": self.duration}


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} 실행 파일을 찾을 수 없습니다.")
    return path


def probe_duration(video: str | Path) -> float:
    ffprobe = _require_binary("ffprobe")
    p = Path(video)
    if not p.exists():
        raise FileNotFoundError(p)
    result = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(p),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    value = float(result.stdout.strip())
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("영상 길이를 확인할 수 없습니다.")
    return value


def detect_scene_changes(video: str | Path, threshold: float = 0.35) -> list[float]:
    ffmpeg = _require_binary("ffmpeg")
    threshold = max(0.05, min(0.95, float(threshold)))
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i", str(video),
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-an",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    # showinfo is written to stderr. ffmpeg may still return non-zero for odd
    # source files while producing useful timestamps, so parse before failing.
    times: list[float] = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", result.stderr or ""):
        value = float(match.group(1))
        if value >= 0:
            times.append(value)
    if result.returncode != 0 and not times:
        raise RuntimeError((result.stderr or "scene detection failed")[-2000:])
    return sorted(set(round(x, 3) for x in times))


def detect_silences(
    video: str | Path,
    noise_db: float = -34.0,
    min_silence_sec: float = 0.7,
) -> list[tuple[float, float]]:
    ffmpeg = _require_binary("ffmpeg")
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-i", str(video),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_sec}",
            "-vn",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    text = result.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9]+(?:\.[0-9]+)?)", text)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9]+(?:\.[0-9]+)?)", text)]
    if result.returncode != 0 and "matches no streams" in text.lower():
        return []

    out: list[tuple[float, float]] = []
    for start, end in zip(starts, ends):
        if end > start:
            out.append((start, end))
    return out


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _speech_ratio(start: float, end: float, silences: list[tuple[float, float]]) -> float:
    duration = max(0.001, end - start)
    silent = sum(_overlap(start, end, a, b) for a, b in silences)
    return max(0.0, min(1.0, 1.0 - silent / duration))


def _choose_highlights(
    *,
    duration: float,
    scene_changes: list[float],
    silences: list[tuple[float, float]],
    num_highlights: int,
    target_duration_sec: float,
) -> list[Highlight]:
    if duration <= 0:
        return []
    count = max(1, min(20, int(num_highlights)))
    target = max(6.0, min(float(target_duration_sec), min(60.0, duration)))

    # Scene changes become natural anchors. Add a uniform fallback so a quiet
    # one-take video still produces usable candidates.
    anchors = [x for x in scene_changes if 0 < x < duration]
    stride = max(4.0, target / 2.0)
    cursor = target / 2.0
    while cursor < duration:
        anchors.append(cursor)
        cursor += stride
    if not anchors:
        anchors = [duration / 2.0]

    candidates: list[Highlight] = []
    for center in sorted(set(round(x, 3) for x in anchors)):
        start = max(0.0, center - target / 2.0)
        end = min(duration, start + target)
        start = max(0.0, end - target)
        speech = _speech_ratio(start, end, silences)
        cuts = sum(1 for t in scene_changes if start <= t <= end)
        # Roughly one meaningful cut per ~8 seconds saturates the visual score.
        density = min(1.0, cuts / max(1.0, (end - start) / 8.0))
        # Spoken content matters slightly more for social shorts, but highly
        # visual clips can still win when the video has no audio.
        score = round((speech * 0.62) + (density * 0.38), 6)
        candidates.append(Highlight(start, end, score, speech, density))

    chosen: list[Highlight] = []
    for candidate in sorted(candidates, key=lambda x: (x.score, x.speech_ratio, x.scene_density), reverse=True):
        if any(
            _overlap(candidate.start, candidate.end, x.start, x.end)
            > min(candidate.duration, x.duration) * 0.35
            for x in chosen
        ):
            continue
        chosen.append(candidate)
        if len(chosen) >= count:
            break

    # If overlap filtering was too strict, fill remaining slots with evenly
    # spaced windows so the caller always gets useful output where possible.
    if len(chosen) < count:
        step = duration / count
        for idx in range(count):
            center = min(duration, (idx + 0.5) * step)
            start = max(0.0, min(duration - target, center - target / 2.0))
            end = min(duration, start + target)
            candidate = Highlight(
                start,
                end,
                round((_speech_ratio(start, end, silences) * 0.62), 6),
                _speech_ratio(start, end, silences),
                0.0,
            )
            if any(abs(candidate.start - x.start) < 0.25 for x in chosen):
                continue
            chosen.append(candidate)
            if len(chosen) >= count:
                break

    return sorted(chosen[:count], key=lambda x: x.start)


def find_highlights(
    video: str | Path,
    *,
    num_highlights: int = 3,
    target_duration_sec: float = 30.0,
    scene_threshold: float = 0.35,
) -> list[Highlight]:
    duration = probe_duration(video)
    scenes = detect_scene_changes(video, scene_threshold)
    try:
        silences = detect_silences(video)
    except RuntimeError:
        # Audio is optional. Visual-only content still gets scene-based clips.
        silences = []
    return _choose_highlights(
        duration=duration,
        scene_changes=scenes,
        silences=silences,
        num_highlights=num_highlights,
        target_duration_sec=target_duration_sec,
    )
