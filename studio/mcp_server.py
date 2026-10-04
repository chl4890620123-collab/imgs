from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from mcp.server import MCPServer

from generation_plan import build_plan, plan_text
from project import StudioProject
from prompt_engine import apply_plan, plan_instruction
from video_recipe import RecipeStore, apply_preset
from scene_prompt import build_scene_generation_prompt
from dialogue_audit import audit_text
from performance import build_shot_prompt, performance_plan_text
from quality_review import mark_shot_quality, regeneration_plan
from ltx_runner import available as ltx_available, build_job, run_job
from remote_jobs import RemoteQueue, default_queue_root


mcp = MCPServer(
    "Saseok Studio",
    instructions=(
        "Control the Saseok Studio video project. Prefer preview_instruction before "
        "apply_instruction when a user's request changes multiple settings."
    ),
)


def _project_path() -> Path:
    env = os.getenv("SASEOK_PROJECT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "saseok_studio_project.json"


def _remote_queue(path: Path) -> RemoteQueue:
    return RemoteQueue(default_queue_root(path.parent))


def _load():
    path = _project_path()
    if not path.exists():
        from bootstrap import build
        build(Path(__file__).resolve().parents[1], path)
    project = StudioProject.load(path)
    recipes = RecipeStore(path.parent / "saseok_video_recipes.json")
    return path, project, recipes


@mcp.tool()
def get_project_state() -> dict:
    """Read the current Saseok Studio project, characters, scenes and voice modes."""
    path, project, recipes = _load()
    return {
        "project_path": str(path),
        "title": project.title,
        "fps": project.fps,
        "output_size": [project.width, project.height],
        "characters": {
            name: {"voice_mode": profile.mode, "voice": profile.voice_name}
            for name, profile in project.characters.items()
        },
        "shots": [
            {
                "id": shot.id,
                "scene_id": shot.scene_id,
                "start": shot.start,
                "duration": shot.duration,
                "visual": shot.visual,
                "generation_status": shot.generation_status,
                "quality_score": shot.quality_score,
                "quality_flags": shot.quality_flags,
            }
            for shot in project.shots
        ],
        "scenes": [
            {
                "id": scene.id,
                "title": scene.title,
                "duration": scene.duration,
                "preset": recipes.get(scene.id).preset,
                "backend": recipes.get(scene.id).inference.backend,
                "creative_prompt": recipes.get(scene.id).inference.creative_prompt,
            }
            for scene in project.scenes
        ],
    }


@mcp.tool()
def preview_instruction(instruction: str, scene_id: int | None = None) -> dict:
    """Preview how a Korean or English director instruction would change the project."""
    _, project, _ = _load()
    plan = plan_instruction(instruction, project, current_scene_id=scene_id)
    return {
        "scene_id": plan.scene_id,
        "instruction": plan.instruction,
        "actions": [asdict(x) for x in plan.actions],
        "summary": plan.text(),
    }


@mcp.tool()
def apply_instruction(instruction: str, scene_id: int | None = None) -> dict:
    """Apply a director instruction to scene, motion, camera, quality or voice settings."""
    path, project, recipes = _load()
    plan = plan_instruction(instruction, project, current_scene_id=scene_id)
    changed = apply_plan(plan, project, path, recipes)
    return {
        "applied": changed,
        "scene_id": plan.scene_id,
        "instruction": instruction,
    }


@mcp.tool()
def set_scene_prompt(scene_id: int, instruction: str) -> dict:
    """Set the full natural-language creative/action/dialogue direction for one scene."""
    path, project, recipes = _load()
    if not any(x.id == scene_id for x in project.scenes):
        raise ValueError(f"장면 {scene_id}을 찾을 수 없습니다.")
    recipe = recipes.get(scene_id)
    recipe.inference.creative_prompt = instruction.strip()
    recipes.save()
    return {"scene_id": scene_id, "creative_prompt": recipe.inference.creative_prompt}


@mcp.tool()
def set_scene_quality(
    scene_id: int,
    preset: str = "high",
    output_resolution: str = "1080p",
    sharpness: int = 50,
    fps: int = 24,
) -> dict:
    """Set scene quality with high-level controls while keeping advanced settings editable."""
    _, project, recipes = _load()
    if not any(x.id == scene_id for x in project.scenes):
        raise ValueError(f"장면 {scene_id}을 찾을 수 없습니다.")
    if preset not in {"fast", "high", "cinematic"}:
        raise ValueError("preset은 fast/high/cinematic 중 하나여야 합니다.")
    if output_resolution not in {"720p", "1080p", "1440p", "4k"}:
        raise ValueError("output_resolution은 720p/1080p/1440p/4k 중 하나여야 합니다.")
    recipe = apply_preset(recipes.get(scene_id), preset)
    recipe.post.upscale = True
    recipe.post.upscale_target = output_resolution
    recipe.post.sharpness = max(0, min(100, sharpness))
    recipe.inference.fps = fps
    recipe.post.interpolation_fps = fps
    recipes.save()
    return {
        "scene_id": scene_id,
        "preset": preset,
        "output_resolution": output_resolution,
        "sharpness": recipe.post.sharpness,
        "fps": fps,
    }


@mcp.tool()
def set_voice_mode(character: str, mode: str) -> dict:
    """Switch a character between AI voice, friend/external recording, or mute."""
    path, project, recipes = _load()
    if character not in project.characters:
        raise ValueError(f"캐릭터를 찾을 수 없습니다: {character}")
    if mode not in {"ai", "external", "muted"}:
        raise ValueError("mode는 ai/external/muted 중 하나여야 합니다.")
    project.profile(character).mode = mode
    project.save(path)
    return {"character": character, "mode": mode}


@mcp.tool()
def get_scene_generation_prompt(scene_id: int) -> str:
    """Return the final character-aware, dialogue-aware prompt that a video backend should receive."""
    _, project, recipes = _load()
    return build_scene_generation_prompt(project, scene_id, recipes.get(scene_id))


@mcp.tool()
def get_scene_performance_plan(scene_id: int) -> str:
    """Return shot-by-shot acting, gaze, dialogue and reaction timing."""
    _, project, recipes = _load()
    return performance_plan_text(project, scene_id, recipes.get(scene_id))


@mcp.tool()
def get_shot_generation_prompt(shot_id: str) -> str:
    """Return the final concise LTX prompt for one shot."""
    _, project, recipes = _load()
    shot = project.shot(shot_id)
    return build_shot_prompt(project, shot, recipes.get(shot.scene_id))


@mcp.tool()
def set_shot_quality(
    shot_id: str,
    score: float,
    flags: list[str] | None = None,
) -> dict:
    """Store a quality score and failure flags so only bad shots are regenerated."""
    path, project, _ = _load()
    shot = mark_shot_quality(project, shot_id, score, flags)
    project.save(path)
    return asdict(shot)


@mcp.tool()
def get_regeneration_plan(scene_id: int, threshold: float = 72.0) -> list[dict]:
    """Return only the low-quality generated shots worth another AI call."""
    _, project, recipes = _load()
    return [
        asdict(x)
        for x in regeneration_plan(project, scene_id, recipes.get(scene_id), threshold)
    ]


@mcp.tool()
def run_ltx_shot(shot_id: str) -> dict:
    """Generate one shot with local LTX-Video when LTX_VIDEO_HOME and CUDA are available."""
    path, project, recipes = _load()
    ok, detail = ltx_available()
    if not ok:
        raise RuntimeError(detail)
    shot = project.shot(shot_id)
    recipe = recipes.get(shot.scene_id)
    if recipe.inference.backend != "ltx-2b":
        raise ValueError("현재 직접 실행기는 ltx-2b 백엔드만 지원합니다.")
    job = build_job(project, shot, recipe, path.parent)
    shot.generation_status = "generating"
    project.save(path)
    try:
        output = run_job(job, cwd=detail)
        shot.visual = str(output.relative_to(path.parent)).replace("\\", "/")
        shot.generation_status = "ready"
        shot.quality_score = None
        shot.quality_flags = []
        project.save(path)
        return {"shot_id": shot.id, "output": str(output), "num_frames": job.num_frames}
    except Exception:
        shot.generation_status = "failed"
        project.save(path)
        raise


@mcp.tool()
def submit_colab_shot(shot_id: str) -> dict:
    """Queue one shot for the Google Drive-backed Colab GPU worker."""
    path, project, recipes = _load()
    shot = project.shot(shot_id)
    recipe = recipes.get(shot.scene_id)
    if recipe.inference.backend != "ltx-2b":
        raise ValueError("현재 Colab 워커는 ltx-2b 백엔드만 직접 실행합니다.")
    queue = _remote_queue(path)
    job = queue.submit_shot(project, shot, recipe, path.parent)
    shot.generation_status = "queued"
    project.save(path)
    return {
        "job_id": job["job_id"],
        "shot_id": shot.id,
        "status": job["status"],
        "queue_root": str(queue.root),
    }


@mcp.tool()
def get_colab_jobs(limit: int = 20) -> dict:
    """Return recent Colab GPU jobs and current worker heartbeat state."""
    path, _, _ = _load()
    queue = _remote_queue(path)
    jobs = queue.list_jobs()[: max(1, min(100, int(limit)))]
    workers = [
        {
            "worker_id": x.worker_id,
            "status": x.status,
            "gpu": x.gpu,
            "updated_at": x.updated_at,
            "current_job": x.current_job,
            "online": x.online,
        }
        for x in queue.worker_states()
    ]
    return {
        "queue_root": str(queue.root),
        "worker_summary": queue.worker_summary(),
        "workers": workers,
        "jobs": jobs,
    }


@mcp.tool()
def sync_colab_results() -> dict:
    """Copy completed Colab videos into media/generated and attach them to their shots."""
    path, project, _ = _load()
    queue = _remote_queue(path)
    synced = queue.sync_all_done(project, path)
    return {
        "count": len(synced),
        "files": [str(x) for x in synced],
    }


@mcp.tool()
def retry_colab_job(job_id: str) -> dict:
    """Retry a failed or cancelled Colab job."""
    path, _, _ = _load()
    return _remote_queue(path).retry(job_id)


@mcp.tool()
def cancel_colab_job(job_id: str) -> dict:
    """Request cancellation of a queued or running Colab job."""
    path, _, _ = _load()
    return _remote_queue(path).cancel(job_id)


@mcp.tool()
def get_dialogue_audit() -> str:
    """Audit dialogue density and flag silent or unusually sparse long scenes."""
    _, project, _ = _load()
    return audit_text(project)


@mcp.tool()
def get_generation_plan() -> str:
    """Return planned AI video calls and cache reuse before generation."""
    path, project, recipes = _load()
    return plan_text(build_plan(project, path.parent, recipes))


@mcp.resource("saseok://project")
def project_resource() -> str:
    """Current project state as JSON."""
    return json.dumps(get_project_state(), ensure_ascii=False, indent=2)


@mcp.resource("saseok://scene/{scene_id}")
def scene_resource(scene_id: str) -> str:
    """One scene's current generation settings as JSON."""
    _, project, recipes = _load()
    sid = int(scene_id)
    scene = next((x for x in project.scenes if x.id == sid), None)
    if scene is None:
        raise ValueError(f"장면 {sid}을 찾을 수 없습니다.")
    return json.dumps(
        {
            "scene": asdict(scene),
            "video_recipe": asdict(recipes.get(sid)),
            "shots": [asdict(x) for x in project.scene_shots(sid)],
            "dialogue": [asdict(x) for x in project.dialogue if x.scene_id == sid],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.prompt()
def direct_scene(scene_id: str, instruction: str) -> str:
    """Build a safe director request that previews changes before applying them."""
    return (
        f"Saseok Studio의 장면 {scene_id}을 수정한다.\n"
        f"감독 지시: {instruction}\n\n"
        "먼저 preview_instruction 도구로 변경 계획을 확인하고, "
        "의도와 일치하면 apply_instruction을 호출하라. "
        "대사/행동/카메라의 세부 지시는 삭제하지 말고 creative_prompt에 보존하라."
    )


if __name__ == "__main__":
    mcp.run()
