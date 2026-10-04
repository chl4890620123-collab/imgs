from __future__ import annotations

from dataclasses import dataclass

from project import Shot, StudioProject
from video_recipe import VideoRecipe


QUALITY_FLAGS = {
    "face_drift": "얼굴/정체성 변화",
    "body_error": "손/팔/몸 형태 오류",
    "motion_jitter": "움직임 떨림",
    "lip_sync": "대사/입 움직임 불일치",
    "continuity": "의상/소품/위치 연속성 오류",
    "soft": "선명도 부족",
    "camera": "카메라 동선 오류",
}


@dataclass(frozen=True)
class RegenerationItem:
    shot_id: str
    reason: str
    priority: int


def mark_shot_quality(
    project: StudioProject,
    shot_id: str,
    score: float,
    flags: list[str] | None = None,
) -> Shot:
    shot = project.shot(shot_id)
    shot.quality_score = max(0.0, min(100.0, float(score)))
    shot.quality_flags = list(dict.fromkeys(flags or []))
    return shot


def regeneration_plan(
    project: StudioProject,
    scene_id: int,
    recipe: VideoRecipe,
    threshold: float = 72.0,
) -> list[RegenerationItem]:
    items: list[RegenerationItem] = []
    for shot in project.scene_shots(scene_id):
        if shot.visual is None and shot.generation_status != "ready":
            continue
        score = shot.quality_score
        if score is None:
            continue
        if score >= threshold and not shot.quality_flags:
            continue
        labels = [QUALITY_FLAGS.get(x, x) for x in shot.quality_flags]
        reason = ", ".join(labels) if labels else f"품질 점수 {score:.0f}"
        severity = max(0, round(threshold - score))
        priority = severity + len(shot.quality_flags) * 10
        items.append(RegenerationItem(shot.id, reason, priority))

    return sorted(items, key=lambda x: x.priority, reverse=True)[: max(1, recipe.call_budget)]
