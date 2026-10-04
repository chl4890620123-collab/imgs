from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from performance import build_shot_prompt
from project import Shot, StudioProject
from video_recipe import VideoRecipe


@dataclass(frozen=True)
class LTXJob:
    shot_id: str
    command: tuple[str, ...]
    output_dir: Path
    target_file: Path
    num_frames: int


def frames_for_duration(duration_sec: float, fps: int) -> int:
    desired = max(9, round(duration_sec * fps))
    # LTX uses 8n+1. Keep the official older LTX path under 257 frames.
    n = max(1, min(32, round((desired - 1) / 8)))
    return n * 8 + 1


def ltx_python() -> str:
    return os.getenv("LTX_PYTHON", sys.executable)


def ltx_home() -> Path | None:
    value = os.getenv("LTX_VIDEO_HOME")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if (path / "inference.py").exists() else None


def available() -> tuple[bool, str]:
    home = ltx_home()
    if home is None:
        return False, "LTX_VIDEO_HOME이 설정되지 않았거나 inference.py를 찾을 수 없습니다."
    try:
        probe = subprocess.run(
            [
                ltx_python(),
                "-c",
                "import torch; raise SystemExit(0 if torch.cuda.is_available() else 2)",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if probe.returncode != 0:
            return False, "LTX Python 환경에서 CUDA GPU를 사용할 수 없습니다."
    except Exception as exc:
        return False, f"LTX Python 환경을 확인할 수 없습니다: {exc}"
    return True, str(home)


def build_job(
    project: StudioProject,
    shot: Shot,
    recipe: VideoRecipe,
    project_dir: str | Path,
) -> LTXJob:
    home = ltx_home()
    if home is None:
        raise RuntimeError("LTX_VIDEO_HOME을 LTX-Video 저장소 경로로 설정하세요.")

    root = Path(project_dir)
    out_dir = root / "media" / "generated" / shot.id
    target = root / "media" / "generated" / f"{shot.id}.mp4"
    out_dir.mkdir(parents=True, exist_ok=True)

    fps = int(recipe.inference.fps)
    num_frames = frames_for_duration(min(shot.duration, recipe.inference.duration_sec), fps)
    prompt = build_shot_prompt(project, shot, recipe)

    cmd: list[str] = [
        ltx_python(),
        str(home / "inference.py"),
        "--prompt", prompt,
        "--output_path", str(out_dir),
        "--height", str(recipe.inference.height),
        "--width", str(recipe.inference.width),
        "--num_frames", str(num_frames),
        "--frame_rate", str(fps),
        "--seed", str(recipe.inference.seed),
        "--negative_prompt", recipe.inference.negative_prompt,
        "--pipeline_config", str(home / "configs" / "ltxv-2b-0.9.8-distilled.yaml"),
    ]

    condition = recipe.inference.start_frame or recipe.inference.character_reference
    if condition:
        p = Path(condition)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            cmd += [
                "--conditioning_media_paths", str(p),
                "--conditioning_start_frames", "0",
            ]

    return LTXJob(
        shot_id=shot.id,
        command=tuple(cmd),
        output_dir=out_dir,
        target_file=target,
        num_frames=num_frames,
    )


def finalize_job(job: LTXJob) -> Path:
    candidates = sorted(
        job.output_dir.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    if not candidates:
        raise RuntimeError("LTX가 완료됐지만 출력 MP4를 찾지 못했습니다.")
    job.target_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates[-1], job.target_file)
    return job.target_file


def run_job(job: LTXJob, cwd: str | Path | None = None) -> Path:
    subprocess.run(list(job.command), cwd=cwd, check=True)
    return finalize_job(job)
