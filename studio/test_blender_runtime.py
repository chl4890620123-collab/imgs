"""End-to-end Blender smoke: a native editable .blend and genuine 3D MP4.

Invoked from GitHub Actions on a CPU runner with Blender + FFmpeg installed.
Outputs small demo artifacts to 3d-smoke-artifacts/ for human inspection.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from blender_3d import (
    blender_executable, build_blend, init_workspace, preview,
    render_chunk, valid_png, workspace,
)
from project import Scene, Shot, StudioProject


def main() -> None:
    assert blender_executable(), "Blender is required for this runtime smoke test"
    assert shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required"
    with tempfile.TemporaryDirectory(prefix="saseok-blender-ci-") as td:
        root = Path(td)
        project_file = root / "saseok_studio_project.json"
        project = StudioProject(
            title="SASEOK 3D demo",
            fps=4, width=128, height=128,
            scenes=[Scene(1, "3D scene", 0.0, 1.0)],
            shots=[Shot("S01_SH01", 1, 0.0, 1.0, "Camera and moving cube")],
        )
        project.save(project_file)
        scene_path = init_workspace(project_file, "S01_SH01")
        spec = json.loads(scene_path.read_text(encoding="utf-8"))
        spec["width"] = 128
        spec["height"] = 128
        spec["fps"] = 4
        spec["frames"] = 4
        spec["render_engine"] = "CYCLES"  # Headless CPU-renderable test
        spec["cycles_samples"] = 2
        scene_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                              encoding="utf-8")

        blend = build_blend(project_file, "S01_SH01")
        assert blend.is_file() and blend.stat().st_size > 1000
        still = preview(project_file, "S01_SH01")
        assert valid_png(still), "Blender preview is unreadable"

        first = render_chunk(project_file, "S01_SH01", max_frames=2)
        assert first["rendered_frames"] == 2 and not first["ready"], first
        second = render_chunk(project_file, "S01_SH01", max_frames=2)
        assert second["rendered_frames"] == 4 and second["ready"], second
        shot = StudioProject.load(project_file).shot("S01_SH01")
        assert shot.visual and shot.generation_status == "ready"
        clip = root / shot.visual
        assert clip.is_file() and clip.stat().st_size > 1000

        output = Path(__file__).resolve().parents[1] / "3d-smoke-artifacts"
        output.mkdir(exist_ok=True)
        for src in (blend, still, clip, scene_path):
            shutil.copy2(src, output / src.name)
        print("Blender native project, PNG preview, resumable frames and video: PASSED")
        print(f"demo artifacts: {output}")


if __name__ == "__main__":
    main()
