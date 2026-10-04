from __future__ import annotations

import sys
from pathlib import Path

from project import DialogueLine, Scene, StudioProject


def build(repo_root: Path, out_file: Path) -> Path:
    sys.path.insert(0, str(repo_root / "colab"))
    from saseok_episode import EPISODE

    project = StudioProject(title=EPISODE["title"], fps=EPISODE.get("fps", 24))
    cursor = 0.0
    line_no = 1
    for src_scene in EPISODE["scenes"]:
        scene = Scene(
            id=src_scene["id"],
            title=src_scene["title"],
            start=cursor,
            duration=float(src_scene["duration"]),
        )
        project.scenes.append(scene)
        dialogue = src_scene.get("dialogue", [])
        if dialogue:
            gap = scene.duration / (len(dialogue) + 1)
            for i, (character, text) in enumerate(dialogue, 1):
                start = cursor + max(1.0, gap * i - 1.2)
                end = min(cursor + scene.duration - 0.2, start + max(2.0, min(6.0, len(text) * 0.16)))
                project.dialogue.append(DialogueLine(
                    id=f"L{line_no:04d}",
                    scene_id=scene.id,
                    character=character,
                    text=text,
                    start=start,
                    end=end,
                    ai_audio=f"media/audio/ai/{character}/L{line_no:04d}.wav",
                    external_audio=f"media/audio/actors/{character}/L{line_no:04d}.wav",
                ))
                project.profile(character)
                line_no += 1
        cursor += scene.duration

    for name, profile in project.characters.items():
        if name in {"서진우", "서진우_속말"}:
            profile.pitch, profile.speed, profile.emotion, profile.power = 35, 42, 30, 42
        elif name == "리아":
            profile.pitch, profile.speed, profile.emotion, profile.power = 50, 55, 62, 70
        elif name == "테오":
            profile.pitch, profile.speed, profile.emotion, profile.power = 60, 65, 68, 62
        elif name == "카르만":
            profile.age, profile.pitch, profile.speed, profile.power = 80, 25, 38, 72

    project.save(out_file)
    return out_file


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    dst = root / "saseok_studio_project.json"
    print(build(root, dst))
