from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project import StudioProject
from remote_jobs import RemoteQueue
from video_recipe import RecipeStore

EXPECTED_SHOTS = 120
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass(frozen=True)
class FullEpisodeSubmission:
    total_shots: int
    submitted: int
    already_running: int
    reused_videos: int


def submit_full_episode(project: StudioProject, project_path: str | Path,
                        recipe_store: RecipeStore, queue: RemoteQueue) -> FullEpisodeSubmission:
    if len(project.shots) != EXPECTED_SHOTS:
        raise ValueError(f"전체 자동 제작은 {EXPECTED_SHOTS}컷 프로젝트를 대상으로 합니다. 현재 {len(project.shots)}컷입니다.")
    recipes = {scene.id: recipe_store.get(scene.id) for scene in project.scenes}
    unsupported = [sid for sid, recipe in recipes.items() if recipe.inference.backend != "ltx-2b"]
    if unsupported:
        raise ValueError(f"Colab 전체 컷 생성은 ltx-2b만 지원합니다. 추론 엔진을 바꿔야 하는 장면: {unsupported}")
    root = Path(project_path).resolve().parent
    jobs = []
    running = 0
    reused = 0
    for shot in sorted(project.shots, key=lambda item: (item.start, item.id)):
        recipe = recipes.get(shot.scene_id)
        if recipe is None:
            raise ValueError(f"{shot.id}: 장면 {shot.scene_id}의 영상 설정이 없습니다.")
        if shot.visual:
            visual = Path(shot.visual)
            if not visual.is_absolute():
                visual = root / visual
            if visual.is_file() and visual.suffix.lower() in VIDEO_SUFFIXES:
                shot.generation_status = "ready"
                reused += 1
                continue
        latest = queue.latest_job_for_shot(shot.id)
        if latest and latest.get("status") in {"queued", "running"}:
            shot.generation_status = "queued" if latest["status"] == "queued" else "generating"
            running += 1
            continue
        jobs.append(queue.submit_shot(project, shot, recipe, root))
        shot.generation_status = "queued"
    project.save(project_path)
    return FullEpisodeSubmission(len(project.shots), len(jobs), running, reused)


def episode_videos_ready(project: StudioProject, project_dir: str | Path) -> bool:
    root = Path(project_dir).resolve()
    if len(project.shots) != EXPECTED_SHOTS:
        return False
    for shot in project.shots:
        if not shot.visual or shot.generation_status != "ready":
            return False
        visual = Path(shot.visual)
        if not visual.is_absolute():
            visual = root / visual
        if not visual.is_file() or visual.suffix.lower() not in VIDEO_SUFFIXES:
            return False
    return True
