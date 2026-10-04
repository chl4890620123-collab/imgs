from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from project import DialogueLine, Scene, Shot, StudioProject, VoiceProfile
from render import render


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("ffmpeg/ffprobe가 필요합니다.")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        audio = root / "actor.wav"
        shot_video = root / "shot.mp4"
        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=0.8",
                "-ar", "48000",
                "-ac", "1",
                str(audio),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", "color=c=navy:s=640x360:r=24:d=2",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(shot_video),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        project = StudioProject(
            title="render-smoke",
            fps=24,
            width=640,
            height=360,
            characters={"테스트": VoiceProfile(mode="external")},
            scenes=[Scene(id=1, title="검증", start=0.0, duration=2.0)],
            shots=[
                Shot(
                    id="S01_SH01",
                    scene_id=1,
                    start=0.0,
                    duration=2.0,
                    prompt="shot-level render integration",
                    visual="shot.mp4",
                    generation_status="ready",
                )
            ],
            dialogue=[
                DialogueLine(
                    id="L0001",
                    scene_id=1,
                    character="테스트",
                    text="실제 렌더 검증입니다.",
                    start=0.25,
                    end=1.25,
                    external_audio="actor.wav",
                )
            ],
        )

        out = root / "rendered.mp4"
        render(project, root, out)
        assert out.exists() and out.stat().st_size > 10_000, out

        probe = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        assert 1.8 <= duration <= 2.2, duration
        print(f"render integration ok: {out.stat().st_size} bytes, {duration:.3f}s")


if __name__ == "__main__":
    main()
