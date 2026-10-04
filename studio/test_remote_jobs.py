from __future__ import annotations

import json
import tempfile
from pathlib import Path

from project import Scene, Shot, StudioProject
from remote_jobs import RemoteQueue, utc_now
from video_recipe import VideoRecipe, apply_preset


def project_fixture(root: Path) -> tuple[StudioProject, Path, Shot, VideoRecipe]:
    project_path = root / "project.json"
    shot = Shot(
        id="S09_SH01",
        scene_id=9,
        start=0.0,
        duration=4.0,
        prompt="Ria runs and pushes Jin-woo before an arrow lands",
    )
    project = StudioProject(
        title="test",
        scenes=[Scene(9, "이세계", 0.0, 4.0)],
        shots=[shot],
    )
    project.save(project_path)
    recipe = apply_preset(VideoRecipe(scene_id=9), "high")
    recipe.inference.backend = "ltx-2b"
    return project, project_path, shot, recipe


def test_submit_done_sync():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project, project_path, shot, recipe = project_fixture(root)
        queue = RemoteQueue(root / "drive" / "SASEOK_GPU_QUEUE")

        job = queue.submit_shot(project, shot, recipe, root)
        assert job["status"] == "queued"
        assert queue.latest_job_for_shot(shot.id)["job_id"] == job["job_id"]

        result = queue.root / job["output"]["result_file"]
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_bytes(b"fake-mp4-for-queue-test")
        queue.move_job(
            job["job_id"],
            "done",
            stage="ready_for_studio",
            progress=100,
            finished_at=utc_now(),
        )

        synced = queue.sync_all_done(project, project_path)
        assert len(synced) == 1
        assert synced[0].exists()
        loaded = StudioProject.load(project_path)
        assert loaded.shot(shot.id).generation_status == "ready"
        assert loaded.shot(shot.id).visual == "media/generated/S09_SH01.mp4"
        assert queue.find_job(job["job_id"])["synced_at"]


def test_cancel_and_retry():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project, _, shot, recipe = project_fixture(root)
        queue = RemoteQueue(root / "queue")
        job = queue.submit_shot(project, shot, recipe, root)

        cancelled = queue.cancel(job["job_id"])
        assert cancelled["status"] == "cancelled"
        retried = queue.retry(job["job_id"])
        assert retried["status"] == "queued"
        assert retried["retry"]["count"] == 1


def test_worker_heartbeat_summary():
    with tempfile.TemporaryDirectory() as td:
        queue = RemoteQueue(Path(td) / "queue")
        heartbeat = queue.workers / "colab-test.json"
        heartbeat.write_text(
            json.dumps(
                {
                    "worker_id": "colab-test",
                    "status": "idle",
                    "gpu": "Tesla T4",
                    "updated_at": utc_now(),
                    "current_job": None,
                }
            ),
            encoding="utf-8",
        )
        assert "Tesla T4" in queue.worker_summary()
        assert queue.worker_states()[0].online


if __name__ == "__main__":
    test_submit_done_sync()
    test_cancel_and_retry()
    test_worker_heartbeat_summary()
    print("remote queue ok")
