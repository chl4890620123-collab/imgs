"""Real Blender 3D workspace for Saseok Studio shots.

No bpy dependency in the Studio process: this module drives the installed
Blender executable. Users can edit native .blend files freely in Blender.
Frames are checkpointed to disk and then incorporated as normal Shot visuals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import struct
import zlib
from pathlib import Path

from project import StudioProject

SUPPORTED_MODELS = {".glb", ".gltf", ".fbx", ".obj"}
SHOT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def blender_executable() -> str | None:
    configured = os.environ.get("SASEOK_BLENDER", "").strip()
    if configured:
        if Path(configured).is_file():
            return str(Path(configured).resolve())
        return shutil.which(configured)
    return shutil.which("blender")


def project_and_shot(project_file: Path, shot_id: str) -> tuple[StudioProject, Path]:
    project_file = project_file.resolve()
    project = StudioProject.load(project_file)
    if not SHOT_PATTERN.fullmatch(shot_id):
        raise ValueError("Invalid 3D shot ID")
    project.shot(shot_id)
    return project, project_file.parent


def workspace(root: Path, shot_id: str) -> Path:
    if not SHOT_PATTERN.fullmatch(shot_id):
        raise ValueError("Invalid shot ID")
    return root / "media" / "3d" / shot_id


def _relative_media_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def load_spec(path: Path, root: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported Blender scene recipe version")
    for key in ("objects", "camera", "lights"):
        if key not in data or not isinstance(data[key], (list if key != "camera" else dict)):
            raise ValueError(f"Invalid 3D recipe section: {key}")
    if not 1 <= int(data.get("fps", 0)) <= 120:
        raise ValueError("3D FPS must be between 1 and 120")
    if not 1 <= int(data.get("frames", 0)) <= 21600:
        raise ValueError("3D frame count must be between 1 and 21600")
    width, height = int(data.get("width", 0)), int(data.get("height", 0))
    if not (64 <= width <= 3840 and 64 <= height <= 2160):
        raise ValueError("3D resolution is outside supported range")
    for item in data["objects"]:
        if not isinstance(item, dict) or item.get("type") not in (
            "cube", "uv_sphere", "cylinder", "plane", "cone", "import"
        ):
            raise ValueError("Unsupported 3D object type")
        if item["type"] == "import":
            raw = Path(str(item.get("source", "")))
            if raw.is_absolute():
                raise ValueError("Model source must be relative to the project folder")
            resolved = (root / raw).resolve()
            if root.resolve() not in resolved.parents or resolved.suffix.lower() not in SUPPORTED_MODELS:
                raise ValueError("Model source must be a supported project-local model")
            if not resolved.is_file():
                raise FileNotFoundError(resolved)
    return data


def init_workspace(project_file: Path, shot_id: str) -> Path:
    project, root = project_and_shot(project_file, shot_id)
    shot = project.shot(shot_id)
    folder = workspace(root, shot_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "scene.json"
    if path.exists():
        load_spec(path, root)
        return path
    frames = max(1, round(shot.duration * project.fps))
    recipe = {
        "schema_version": 1,
        "title": f"{project.title} / {shot.id}",
        "fps": project.fps,
        "frames": frames,
        "width": project.width,
        "height": project.height,
        "render_engine": "EEVEE",
        "camera": {
            "location": [6.0, -9.0, 6.0],
            "target": [0.0, 0.0, 1.0],
            "focal_length_mm": 38,
        },
        "lights": [
            {"name": "Key light", "type": "AREA", "location": [0, -5, 8],
             "energy": 950, "size": 6},
            {"name": "Rim light", "type": "AREA", "location": [-4, 3, 6],
             "energy": 500, "size": 4},
        ],
        "objects": [
            {"name": "Floor", "type": "plane", "location": [0, 0, 0],
             "scale": [9, 9, 1], "material": {"color": "#313846", "roughness": 0.88}},
            {"name": "Actor block (replace in Blender)", "type": "cube",
             "location": [-1.5, 0, 1], "scale": [0.7, 0.7, 1],
             "material": {"color": "#ba6d48", "metallic": 0.25},
             "keyframes": [
                 {"frame": 1, "location": [-1.5, 0, 1]},
                 {"frame": frames, "location": [1.5, 0, 1], "rotation_degrees": [0, 0, 90]},
             ]},
        ],
    }
    path.write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def add_model_asset(project_file: Path, shot_id: str, model_file: Path) -> Path:
    _, root = project_and_shot(project_file, shot_id)
    model_file = model_file.expanduser().resolve()
    if model_file.suffix.lower() not in SUPPORTED_MODELS or not model_file.is_file():
        raise ValueError("Supported files are GLB, GLTF, FBX, OBJ")
    spec_path = init_workspace(project_file, shot_id)
    folder = workspace(root, shot_id)
    if (folder / "scene.blend").exists():
        raise RuntimeError(
            "Native .blend already exists. Import directly in Blender and save it; "
            "regenerating from scene.json would overwrite manual edits."
        )
    dest_folder = folder / "models"
    dest_folder.mkdir(parents=True, exist_ok=True)
    destination = dest_folder / model_file.name
    if model_file != destination:
        shutil.copy2(model_file, destination)
    spec = load_spec(spec_path, root)
    spec["objects"].append({
        "name": model_file.stem,
        "type": "import",
        "source": _relative_media_path(root, destination),
        "location": [0, 0, 0],
        "scale": [1, 1, 1],
        "rotation_degrees": [0, 0, 0],
    })
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _run_blender(mode: str, root: Path, folder: Path, *, start: int = 1,
                 end: int = 1, timeout_seconds: int = 3600) -> None:
    binary = blender_executable()
    if not binary:
        raise RuntimeError("Blender is not installed; install Blender 4.5+ and set SASEOK_BLENDER")
    script = Path(__file__).with_name("blender_3d_worker.py")
    blend = folder / "scene.blend"
    recipe = folder / "scene.json"
    args = [binary, "--background", "--disable-autoexec"]
    if mode != "build":
        if not blend.is_file():
            raise FileNotFoundError(f"Make a .blend scene before rendering: {blend}")
        args.append(str(blend))
    else:
        args.append("--factory-startup")
    args += [
        "--python", str(script), "--",
        "--mode", mode,
        "--project-root", str(root),
        "--recipe", str(recipe),
        "--blend", str(blend),
        "--frames-dir", str(folder / "frames"),
        "--preview", str(folder / "preview.png"),
        "--start", str(start),
        "--end", str(end),
    ]
    proc = subprocess.run(args, cwd=root, capture_output=True, text=True,
                          timeout=timeout_seconds, check=False)
    if proc.returncode:
        raise RuntimeError(
            f"Blender {mode} failed ({proc.returncode}):\n"
            + (proc.stdout + "\n" + proc.stderr)[-5000:]
        )


def build_blend(project_file: Path, shot_id: str) -> Path:
    _, root = project_and_shot(project_file, shot_id)
    folder = workspace(root, shot_id)
    path = init_workspace(project_file, shot_id)
    load_spec(path, root)
    blend = folder / "scene.blend"
    if blend.exists():
        raise FileExistsError("Scene already exists. Open it in Blender to edit without overwriting.")
    _run_blender("build", root, folder, timeout_seconds=180)
    if not blend.is_file():
        raise RuntimeError("Blender returned success without a .blend file")
    return blend


def open_native_scene(project_file: Path, shot_id: str) -> Path:
    _, root = project_and_shot(project_file, shot_id)
    blend = workspace(root, shot_id) / "scene.blend"
    if not blend.is_file():
        raise FileNotFoundError("Create the 3D scene before editing in Blender")
    binary = blender_executable()
    if not binary:
        raise RuntimeError("Blender is not installed; set SASEOK_BLENDER")
    subprocess.Popen([binary, str(blend)], cwd=root,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return blend


def valid_png(path: Path) -> bool:
    """Check the entire PNG chunk stream and CRCs before accepting a frame."""
    try:
        if not path.is_file() or path.stat().st_size < 100:
            return False
        with path.open("rb") as handle:
            if handle.read(8) != b"\\x89PNG\\r\\n\\x1a\\n":
                return False
            saw_header = saw_image = False
            while True:
                raw_length = handle.read(4)
                if len(raw_length) != 4:
                    return False
                length = struct.unpack(">I", raw_length)[0]
                if length > 150 * 1024 * 1024:
                    return False
                kind = handle.read(4)
                data = handle.read(length)
                checksum = handle.read(4)
                if len(kind) != 4 or len(data) != length or len(checksum) != 4:
                    return False
                actual = zlib.crc32(kind + data) & 0xFFFFFFFF
                if actual != struct.unpack(">I", checksum)[0]:
                    return False
                if kind == b"IHDR":
                    if saw_header or length != 13:
                        return False
                    width, height = struct.unpack(">II", data[:8])
                    if not width or not height:
                        return False
                    saw_header = True
                elif kind == b"IDAT":
                    saw_image = True
                elif kind == b"IEND":
                    return saw_header and saw_image and length == 0 and handle.read(1) == b""
    except (OSError, ValueError, struct.error):
        return False


def _blend_signature(blend: Path) -> str:
    # A fast content revision marker: Blender save changes size and/or mtime.
    stat = blend.stat()
    return hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()


def _reset_outdated_frames(folder: Path, blend: Path) -> None:
    """Never silently reuse cached frames after a user edits the .blend."""
    marker = folder / "frames_blend_revision.txt"
    current = _blend_signature(blend)
    prior = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if prior != current:
        frames = folder / "frames"
        if frames.exists():
            for p in frames.glob("frame_*.png"):
                p.unlink()
        (folder / "render.mp4").unlink(missing_ok=True)
        marker.write_text(current, encoding="utf-8")


def preview(project_file: Path, shot_id: str) -> Path:
    _, root = project_and_shot(project_file, shot_id)
    folder = workspace(root, shot_id)
    target = folder / "preview.png"
    target.unlink(missing_ok=True)
    _run_blender("preview", root, folder, timeout_seconds=300)
    if not valid_png(target):
        raise RuntimeError("Blender preview image is invalid")
    return target


def attach_start_frame(project_file: Path, shot_id: str) -> Path:
    from video_recipe import RecipeStore
    project, root = project_and_shot(project_file, shot_id)
    folder = workspace(root, shot_id)
    blend = folder / "scene.blend"
    if not blend.is_file():
        raise FileNotFoundError("Create a 3D scene first")
    marker = folder / "frames_blend_revision.txt"
    valid_revision = (
        marker.exists()
        and marker.read_text(encoding="utf-8").strip() == _blend_signature(blend)
    )
    frame = folder / "frames" / "frame_000001.png"
    if not valid_revision or not valid_png(frame):
        frame = folder / "preview.png"
    if not valid_png(frame) or frame.stat().st_mtime_ns < blend.stat().st_mtime_ns:
        raise FileNotFoundError("Render a fresh preview after saving the latest Blender edits")
    recipes = RecipeStore(root / "saseok_video_recipes.json")
    recipe = recipes.get(project.shot(shot_id).scene_id)
    recipe.inference.start_frame = _relative_media_path(root, frame)
    recipes.save()
    return frame


def render_chunk(project_file: Path, shot_id: str, max_frames: int = 24) -> dict:
    if not 1 <= max_frames <= 240:
        raise ValueError("max_frames must be between 1 and 240")
    project, root = project_and_shot(project_file, shot_id)
    folder = workspace(root, shot_id)
    spec = load_spec(folder / "scene.json", root)
    blend = folder / "scene.blend"
    if not blend.is_file():
        raise FileNotFoundError("Create the .blend file before rendering")
    _reset_outdated_frames(folder, blend)
    frames = folder / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    total = int(spec["frames"])
    pending = [i for i in range(1, total + 1)
               if not valid_png(frames / f"frame_{i:06d}.png")]
    if pending:
        # Render one small contiguous burst. Each PNG is saved independently.
        start = pending[0]
        end = start
        while end - start + 1 < max_frames and end + 1 <= total and (
            not valid_png(frames / f"frame_{end + 1:06d}.png")
        ):
            end += 1
        _run_blender("frames", root, folder, start=start, end=end, timeout_seconds=7200)
    done = sum(valid_png(frames / f"frame_{i:06d}.png") for i in range(1, total + 1))
    ready = done == total
    video = folder / "render.mp4"
    if ready:
        if video.is_file():
            try:
                probe = subprocess.run(
                    [shutil.which("ffprobe") or "ffprobe", "-v", "error",
                     "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                if float(probe.stdout.strip()) >= total / spec["fps"] * 0.9:
                    shot = project.shot(shot_id)
                    shot.visual = _relative_media_path(root, video)
                    shot.generation_status = "ready"
                    project.save(project_file)
                    return {"shot_id": shot_id, "rendered_frames": done,
                            "total_frames": total, "ready": True,
                            "video": _relative_media_path(root, video)}
            except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise RuntimeError("FFmpeg and ffprobe are required to combine 3D frames")
        temp = folder / ".render.partial.mp4"
        try:
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                 "-framerate", str(spec["fps"]), "-start_number", "1",
                 "-i", str(frames / "frame_%06d.png"),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-crf", "18", "-movflags", "+faststart", str(temp)],
                check=True, timeout=3600,
            )
            probe = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height:format=duration",
                 "-of", "json", str(temp)], capture_output=True, text=True,
                check=True, timeout=30,
            )
            metadata = json.loads(probe.stdout)
            duration = float(metadata.get("format", {}).get("duration") or 0)
            video_streams = metadata.get("streams", [])
            if duration < total / spec["fps"] * 0.9 or not any(
                int(stream.get("width", 0)) > 0 and int(stream.get("height", 0)) > 0
                for stream in video_streams
            ):
                raise RuntimeError("Final 3D MP4 validation failed")
            os.replace(temp, video)
        finally:
            temp.unlink(missing_ok=True)
        # Link result to existing Shot timeline only after it is fully validated.
        shot = project.shot(shot_id)
        shot.visual = _relative_media_path(root, video)
        shot.generation_status = "ready"
        project.save(project_file)
    return {"shot_id": shot_id, "rendered_frames": done,
            "total_frames": total, "ready": ready,
            "video": _relative_media_path(root, video) if ready else None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Blender 3D shot workspace")
    parser.add_argument("action", choices=("init", "build", "open", "preview", "render", "reference", "import"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--shot", required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--chunk", type=int, default=24)
    args = parser.parse_args()
    if args.action == "init":
        result = init_workspace(args.project, args.shot)
    elif args.action == "build":
        result = build_blend(args.project, args.shot)
    elif args.action == "open":
        result = open_native_scene(args.project, args.shot)
    elif args.action == "preview":
        result = preview(args.project, args.shot)
    elif args.action == "render":
        result = render_chunk(args.project, args.shot, args.chunk)
    elif args.action == "reference":
        result = attach_start_frame(args.project, args.shot)
    else:
        if args.model is None:
            parser.error("import requires --model")
        result = add_model_asset(args.project, args.shot, args.model)
    print(json.dumps({"result": str(result) if isinstance(result, Path) else result},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
