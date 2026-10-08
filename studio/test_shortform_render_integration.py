from pathlib import Path
import shutil
import subprocess
import tempfile

from shortform.clipping import Highlight, find_highlights
from shortform.quality_gate import validate_vertical_output
from shortform.reframe import render_vertical_clip


def test_real_vertical_render():
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg and ffprobe

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "source.mp4"
        out = root / "out.mp4"

        subprocess.run(
            [
                ffmpeg, "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                "-t", "8",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                str(source),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        candidates = find_highlights(source, num_highlights=1, target_duration_sec=6)
        assert len(candidates) == 1
        render_vertical_clip(source, Highlight(0, 4, 1, 1, 1), out, width=360, height=640, fps=24)
        assert out.exists() and out.stat().st_size > 1000

        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "360x640"

        quality_out = root / "quality_preview.mp4"
        render_vertical_clip(
            source,
            Highlight(0, 4, 1, 1, 1),
            quality_out,
            layout="blur",
            quality="preview",
        )
        inspection = validate_vertical_output(
            quality_out,
            expected_width=720,
            expected_height=1280,
            min_duration=3.5,
        )
        assert inspection.has_audio
        assert inspection.fps >= 29.0


if __name__ == "__main__":
    test_real_vertical_render()
    print("ok")
