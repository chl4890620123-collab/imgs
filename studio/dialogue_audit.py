from __future__ import annotations

from dataclasses import dataclass

from project import StudioProject


@dataclass(frozen=True)
class DialogueAudit:
    total_duration_sec: float
    total_lines: int
    total_characters: int
    silent_scenes: tuple[int, ...]
    sparse_scenes: tuple[int, ...]

    @property
    def lines_per_minute(self) -> float:
        if self.total_duration_sec <= 0:
            return 0.0
        return self.total_lines / (self.total_duration_sec / 60.0)

    @property
    def chars_per_minute(self) -> float:
        if self.total_duration_sec <= 0:
            return 0.0
        return self.total_characters / (self.total_duration_sec / 60.0)


def audit_dialogue(project: StudioProject) -> DialogueAudit:
    by_scene: dict[int, list] = {scene.id: [] for scene in project.scenes}
    for line in project.dialogue:
        by_scene.setdefault(line.scene_id, []).append(line)

    silent = tuple(scene.id for scene in project.scenes if not by_scene.get(scene.id))
    sparse = tuple(
        scene.id
        for scene in project.scenes
        if scene.duration >= 60 and len(by_scene.get(scene.id, [])) <= 2
    )
    return DialogueAudit(
        total_duration_sec=sum(scene.duration for scene in project.scenes),
        total_lines=len(project.dialogue),
        total_characters=sum(len(line.text) for line in project.dialogue),
        silent_scenes=silent,
        sparse_scenes=sparse,
    )


def audit_text(project: StudioProject) -> str:
    result = audit_dialogue(project)
    return (
        f"총 길이: {result.total_duration_sec:.0f}초\n"
        f"대사: {result.total_lines}줄 / {result.total_characters}자\n"
        f"분당 대사: {result.lines_per_minute:.2f}줄\n"
        f"분당 문자: {result.chars_per_minute:.1f}자\n"
        f"무대사 장면: {list(result.silent_scenes)}\n"
        f"60초 이상인데 대사 2줄 이하 장면: {list(result.sparse_scenes)}"
    )
