from __future__ import annotations

import subprocess
from pathlib import Path

from audio import ffmpeg
from project import StudioProject


def _ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _audio_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def write_srt(project: StudioProject, out: Path, project_dir: Path | None = None) -> None:
    rows = []
    lines = sorted(project.dialogue, key=lambda x: x.start)
    scene_end = {scene.id: scene.start + scene.duration for scene in project.scenes}

    for i, line in enumerate(lines, 1):
        end = line.end
        if project_dir is not None:
            audio = project.line_audio(line)
            if audio:
                audio_path = project_dir / audio
                if audio_path.exists():
                    duration = _audio_duration(audio_path)
                    if duration and duration > 0:
                        end = max(end, line.start + duration + 0.12)

        # Prevent a subtitle from running into the next spoken line or out of its scene.
        following = next(
            (x for x in lines if x.scene_id == line.scene_id and x.start > line.start),
            None,
        )
        if following:
            end = min(end, max(line.start + 0.35, following.start - 0.06))
        if line.scene_id in scene_end:
            end = min(end, scene_end[line.scene_id] - 0.03)
        end = max(line.start + 0.35, end)

        rows += [
            str(i),
            f"{_ts(line.start)} --> {_ts(end)}",
            f"{line.character}: {line.text}",
            "",
        ]
    out.write_text("\n".join(rows), encoding="utf-8")


def render(project: StudioProject, project_dir: Path, out_file: Path) -> Path:
    work = project_dir / ".studio_render"
    work.mkdir(parents=True, exist_ok=True)
    srt = work / "subtitles.srt"
    write_srt(project, srt, project_dir)

    total = max((s.start + s.duration for s in project.scenes), default=1.0)
    scene_files: list[Path] = []
    for scene in project.scenes:
        out = work / f"scene_{scene.id:02d}.mp4"
        visual = (project_dir / scene.visual) if scene.visual else None
        if visual and visual.exists() and visual.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            cmd = [
                ffmpeg(), "-y", "-i", str(visual), "-t", str(scene.duration),
                "-vf", (
                    f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease,"
                    f"pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2,"
                    f"tpad=stop_mode=clone:stop_duration={scene.duration},fps={project.fps}"
                ),
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
            ]
        elif visual and visual.exists():
            cmd = [
                ffmpeg(), "-y", "-loop", "1", "-i", str(visual), "-t", str(scene.duration),
                "-vf", f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease,pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2,fps={project.fps}",
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
            ]
        else:
            cmd = [
                ffmpeg(), "-y", "-f", "lavfi", "-i",
                f"color=c=black:s={project.width}x{project.height}:r={project.fps}:d={scene.duration}",
                "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
            ]
        subprocess.run(cmd, check=True)
        scene_files.append(out)

    concat = work / "scenes.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in scene_files), encoding="utf-8")
    video = work / "video.mp4"
    subprocess.run([ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video)], check=True)

    active = []
    for line in project.dialogue:
        audio = project.line_audio(line)
        if audio:
            p = project_dir / audio
            if p.exists():
                active.append((line, p))

    inputs = [ffmpeg(), "-y", "-i", str(video)]
    filter_parts, mix_inputs = [], []
    for idx, (line, p) in enumerate(active, 1):
        inputs += ["-i", str(p)]
        delay = max(0, int(line.start * 1000))
        filter_parts.append(
            f"[{idx}:a]aresample=48000,asetpts=N/SR/TB,adelay={delay}|{delay},apad[a{idx}]"
        )
        mix_inputs.append(f"[a{idx}]")

    subtitle_size = max(22, round(project.height * 0.043))
    vf = (
        f"subtitles='{srt.as_posix()}':"
        f"force_style='FontName=Malgun Gothic,FontSize={subtitle_size},"
        "Outline=1.6,Shadow=0,MarginV=48,PrimaryColour=&H00F5F5F2&,"
        "BackColour=&H70000000&,BorderStyle=3',"
        "unsharp=5:5:0.28:5:5:0.0"
    )
    if mix_inputs:
        filter_parts.append(
            "".join(mix_inputs)
            + f"amix=inputs={len(mix_inputs)}:normalize=0,"
              f"loudnorm=I=-16:TP=-1.5:LRA=11,atrim=duration={total}[mix]"
        )
        subprocess.run(
            inputs + ["-filter_complex", ";".join(filter_parts), "-map", "0:v", "-map", "[mix]", "-vf", vf,
                      "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "aac", "-b:a", "192k",
                      "-t", str(total), "-movflags", "+faststart", str(out_file)],
            check=True,
        )
    else:
        subprocess.run(
            inputs + ["-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                      "-t", str(total), "-movflags", "+faststart", str(out_file)],
            check=True,
        )
    return out_file
