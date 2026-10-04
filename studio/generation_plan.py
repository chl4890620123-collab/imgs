from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project import StudioProject
from video_cache import VideoCache
from video_recipe import RecipeStore, VideoRecipe


@dataclass(frozen=True)
class ScenePlan:
    scene_id: int
    title: str
    cached_calls: int
    required_calls: int
    total_slots: int
    backend: str
    resolution: str


@dataclass(frozen=True)
class GenerationPlan:
    scenes: list[ScenePlan]

    @property
    def required_calls(self) -> int:
        return sum(x.required_calls for x in self.scenes)

    @property
    def cached_calls(self) -> int:
        return sum(x.cached_calls for x in self.scenes)

    @property
    def total_slots(self) -> int:
        return sum(x.total_slots for x in self.scenes)


def build_plan(project: StudioProject, project_root: str | Path, store: RecipeStore) -> GenerationPlan:
    cache = VideoCache(project_root)
    rows = []
    for scene in project.scenes:
        recipe: VideoRecipe = store.get(scene.id)
        missing = cache.missing_slots(recipe)
        rows.append(ScenePlan(
            scene_id=scene.id,
            title=scene.title,
            cached_calls=recipe.call_budget - len(missing),
            required_calls=len(missing),
            total_slots=recipe.call_budget,
            backend=recipe.inference.backend,
            resolution=f"{recipe.inference.width}x{recipe.inference.height}",
        ))
    return GenerationPlan(rows)


def plan_text(plan: GenerationPlan) -> str:
    lines = [
        f"실제 AI 호출 필요: {plan.required_calls}회",
        f"캐시 재사용: {plan.cached_calls}회",
        f"전체 생성 슬롯: {plan.total_slots}개",
        "",
    ]
    for row in plan.scenes:
        lines.append(
            f"{row.scene_id:02d}. {row.title} — {row.backend} {row.resolution} / "
            f"새 호출 {row.required_calls}, 캐시 {row.cached_calls}"
        )
    lines += [
        "",
        "자막, 성우, 색감, 줌/패닝, 흔들림, 보간, 업스케일 설정만 바꾸면 AI 영상은 재호출하지 않습니다.",
    ]
    return "\n".join(lines)
