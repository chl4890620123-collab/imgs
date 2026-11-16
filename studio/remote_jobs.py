from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from performance import build_shot_prompt, choose_generation_shots
from project import Shot, StudioProject
from video_recipe import VideoRecipe


JOB_STATES = ("queued", "running", "done", "failed", "cancelled")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def default_queue_root(project_dir: str | Path) -> Path:
    configured = os.getenv("SASEOK_COLAB_QUEUE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(project_dir).resolve() / ".colab_queue"


@dataclass(frozen=True)
class WorkerState:
    worker_id: str
    status: str
    gpu: str
    updated_at: str
    current_job: str | None = None

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - parse_time(self.updated_at))

    @property
    def online(self) -> bool:
        return self.age_seconds < 90.0


class RemoteQueue:
    """Filesystem queue designed for a Google Drive-synced folder.

    The desktop app and Colab worker only exchange small JSON files and staged
    references. Generated videos are copied back from outputs/ when complete.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.jobs = {state: self.root / "jobs" / state for state in JOB_STATES}
        self.assets = self.root / "assets"
        self.outputs = self.root / "outputs" / "shots"
        self.logs = self.root / "outputs" / "logs"
        self.workers = self.root / "workers" / "heartbeat"
        for path in [*self.jobs.values(), self.assets, self.outputs, self.logs, self.workers]:
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
        ) as handle:
            handle.write(payload)
            temp = Path(handle.name)
        temp.replace(path)

    @staticmethod
    def read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _job_path(self, job_id: str, state: str) -> Path:
        return self.jobs[state] / f"{job_id}.json"

    def find_job_path(self, job_id: str) -> Path | None:
        for state in JOB_STATES:
            path = self._job_path(job_id, state)
            if path.exists():
                return path
        return None

    def find_job(self, job_id: str) -> dict | None:
        path = self.find_job_path(job_id)
        if not path:
            return None
        try:
            return self.read_json(path)
        except Exception:
            return None

    def list_jobs(self, states: Iterable[str] = JOB_STATES) -> list[dict]:
        found: list[dict] = []
        for state in states:
            folder = self.jobs[state]
            if not folder.exists():
                continue
            for path in folder.glob("*.json"):
                try:
                    found.append(self.read_json(path))
                except Exception:
                    continue
        return sorted(
            found,
            key=lambda item: parse_time(item.get("created_at")),
            reverse=True,
        )

    def latest_job_for_shot(self, shot_id: str) -> dict | None:
        jobs = [x for x in self.list_jobs() if x.get("shot_id") == shot_id]
        return jobs[0] if jobs else None

    def submit_scene_priority(
        self,
        project: StudioProject,
        scene_id: int,
        recipe: VideoRecipe,
        project_dir: str | Path,
        max_retries: int = 2,
    ) -> list[dict]:
        """Queue only the highest-value shots up to the scene call budget."""
        jobs: list[dict] = []
        selected = choose_generation_shots(project, scene_id, recipe)
        for plan in selected:
            shot = project.shot(plan.shot_id)
            latest = self.latest_job_for_shot(shot.id)
            if latest and latest.get("status") in {"queued", "running"}:
                continue
            jobs.append(
                self.submit_shot(
                    project,
                    shot,
                    recipe,
                    project_dir,
                    max_retries=max_retries,
                )
            )
        return jobs

    def recover_stale_running(
        self,
        timeout_seconds: float = 300.0,
    ) -> list[dict]:
        """Recover jobs left in running when a Colab runtime disappears.

        A running job is only reclaimed when its own update timestamp is stale
        and the worker heartbeat is absent/stale, reducing false recovery during
        normal Drive sync latency.
        """
        timeout_seconds = max(60.0, float(timeout_seconds))
        workers = {x.worker_id: x for x in self.worker_states()}
        recovered: list[dict] = []

        for path in list(self.jobs["running"].glob("*.json")):
            try:
                job = self.read_json(path)
            except Exception:
                continue
            age = time.time() - parse_time(job.get("updated_at"))
            if age < timeout_seconds:
                continue

            worker_id = str(job.get("worker_id") or "")
            worker = workers.get(worker_id)
            if worker is not None and worker.online:
                continue

            retry = dict(job.get("retry") or {})
            count = int(retry.get("count", 0))
            maximum = int(retry.get("max", 2))
            retry["count"] = count + 1
            job["retry"] = retry
            job["worker_id"] = None
            job["cancel_requested"] = False
            job["error"] = "Colab 워커 heartbeat가 끊겨 실행 중 작업을 자동 회수했습니다."
            job["updated_at"] = utc_now()

            if count < maximum:
                job["status"] = "queued"
                job["stage"] = "recovered_from_stale_worker"
                job["progress"] = 0
                target = self.jobs["queued"] / path.name
            else:
                job["status"] = "failed"
                job["stage"] = "stale_worker_retry_exhausted"
                job["finished_at"] = utc_now()
                target = self.jobs["failed"] / path.name

            self._atomic_json(target, job)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            recovered.append(job)
        return recovered

    def _stage_reference(
        self,
        job_id: str,
        project_dir: Path,
        value: str | None,
        label: str,
    ) -> str | None:
        if not value:
            return None
        source = Path(value)
        if not source.is_absolute():
            source = project_dir / source
        if not source.exists() or not source.is_file():
            return None
        dst_dir = self.assets / job_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower() or ".bin"
        dst = dst_dir / f"{label}{suffix}"
        shutil.copy2(source, dst)
        return str(dst.relative_to(self.root)).replace("\\", "/")

    def submit_shot(
        self,
        project: StudioProject,
        shot: Shot,
        recipe: VideoRecipe,
        project_dir: str | Path,
        max_retries: int = 2,
    ) -> dict:
        root = Path(project_dir).resolve()
        job_id = (
            f"JOB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{shot.id}_{uuid.uuid4().hex[:6]}"
        )
        refs = {
            "start_frame": self._stage_reference(
                job_id, root, recipe.inference.start_frame, "start_frame"
            ),
            "end_frame": self._stage_reference(
                job_id, root, recipe.inference.end_frame, "end_frame"
            ),
            "character_reference": self._stage_reference(
                job_id,
                root,
                recipe.inference.character_reference,
                "character_reference",
            ),
        }
        if shot.reference_key:
            candidate = root / shot.reference_key
            if candidate.exists():
                refs["shot_reference"] = self._stage_reference(
                    job_id, root, str(candidate), "shot_reference"
                )

        job = {
            "schema_version": 1,
            "job_id": job_id,
            "project_title": project.title,
            "scene_id": shot.scene_id,
            "shot_id": shot.id,
            "backend": recipe.inference.backend,
            "status": "queued",
            "stage": "waiting_for_worker",
            "progress": 0,
            "priority": 50,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "worker_id": None,
            "cancel_requested": False,
            "input": {
                "prompt": build_shot_prompt(project, shot, recipe),
                "negative_prompt": recipe.inference.negative_prompt,
                "width": recipe.inference.width,
                "height": recipe.inference.height,
                "fps": recipe.inference.fps,
                "duration_sec": min(shot.duration, recipe.inference.duration_sec),
                "steps": recipe.inference.steps,
                "guidance": recipe.inference.guidance,
                "seed": recipe.inference.seed,
                "motion_strength": recipe.inference.motion_strength,
                "character_lock": recipe.inference.character_lock,
                "pipeline_config": "configs/ltxv-2b-0.9.8-distilled.yaml",
            },
            "references": refs,
            "output": {
                "result_file": f"outputs/shots/{job_id}.mp4",
                "log_file": f"outputs/logs/{job_id}.log",
            },
            "retry": {"count": 0, "max": int(max_retries)},
            "error": None,
        }
        self._atomic_json(self._job_path(job_id, "queued"), job)
        return job

    def update_job(self, job_id: str, **changes) -> dict:
        path = self.find_job_path(job_id)
        if not path:
            raise KeyError(job_id)
        job = self.read_json(path)
        job.update(changes)
        job["updated_at"] = utc_now()
        self._atomic_json(path, job)
        return job

    def move_job(self, job_id: str, target_state: str, **changes) -> dict:
        if target_state not in JOB_STATES:
            raise ValueError(target_state)
        source = self.find_job_path(job_id)
        if not source:
            raise KeyError(job_id)
        job = self.read_json(source)
        job.update(changes)
        job["status"] = target_state
        job["updated_at"] = utc_now()
        target = self._job_path(job_id, target_state)
        self._atomic_json(target, job)
        if source != target:
            try:
                source.unlink()
            except FileNotFoundError:
                pass
        return job

    def cancel(self, job_id: str) -> dict:
        path = self.find_job_path(job_id)
        if not path:
            raise KeyError(job_id)
        job = self.read_json(path)
        if job.get("status") == "queued":
            return self.move_job(
                job_id,
                "cancelled",
                cancel_requested=True,
                stage="cancelled_before_start",
                progress=0,
            )
        job["cancel_requested"] = True
        job["stage"] = "cancel_requested"
        job["updated_at"] = utc_now()
        self._atomic_json(path, job)
        return job

    def retry(self, job_id: str) -> dict:
        path = self.find_job_path(job_id)
        if not path:
            raise KeyError(job_id)
        job = self.read_json(path)
        if job.get("status") not in {"failed", "cancelled"}:
            raise ValueError("실패/취소 작업만 재시도할 수 있습니다.")
        retry = dict(job.get("retry") or {})
        retry["count"] = int(retry.get("count", 0)) + 1
        job["retry"] = retry
        job["status"] = "queued"
        job["stage"] = "waiting_for_worker"
        job["progress"] = 0
        job["cancel_requested"] = False
        job["worker_id"] = None
        job["error"] = None
        job["updated_at"] = utc_now()
        target = self._job_path(job_id, "queued")
        self._atomic_json(target, job)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return job

    def sync_result(
        self,
        job_id: str,
        project: StudioProject,
        project_path: str | Path,
    ) -> Path:
        job = self.find_job(job_id)
        if not job or job.get("status") != "done":
            raise ValueError("완료된 작업이 아닙니다.")
        result_rel = job.get("output", {}).get("result_file")
        if not result_rel:
            raise ValueError("결과 파일 경로가 없습니다.")
        source = self.root / result_rel
        if not source.exists():
            raise FileNotFoundError(source)

        project_file = Path(project_path).resolve()
        project_dir = project_file.parent
        shot = project.shot(job["shot_id"])
        dest = project_dir / "media" / "generated" / f"{shot.id}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        shot.visual = str(dest.relative_to(project_dir)).replace("\\", "/")
        shot.generation_status = "ready"
        project.save(project_file)

        if not job.get("synced_at"):
            self.update_job(job_id, synced_at=utc_now(), stage="synced_to_studio")
        return dest

    def sync_all_done(
        self,
        project: StudioProject,
        project_path: str | Path,
    ) -> list[Path]:
        synced: list[Path] = []
        shot_ids = {x.id for x in project.shots}
        for job in self.list_jobs(["done"]):
            if job.get("shot_id") not in shot_ids:
                continue
            if job.get("synced_at"):
                continue
            try:
                synced.append(self.sync_result(job["job_id"], project, project_path))
            except (FileNotFoundError, ValueError, KeyError):
                continue
        return synced

    def worker_states(self) -> list[WorkerState]:
        states: list[WorkerState] = []
        for path in self.workers.glob("*.json"):
            try:
                raw = self.read_json(path)
                states.append(WorkerState(
                    worker_id=str(raw.get("worker_id", path.stem)),
                    status=str(raw.get("status", "unknown")),
                    gpu=str(raw.get("gpu", "unknown")),
                    updated_at=str(raw.get("updated_at", "")),
                    current_job=raw.get("current_job"),
                ))
            except Exception:
                continue
        return sorted(states, key=lambda x: x.updated_at, reverse=True)

    def worker_summary(self) -> str:
        states = self.worker_states()
        online = [x for x in states if x.online]
        if not online:
            return "Colab 워커 오프라인"
        worker = online[0]
        suffix = f" / {worker.current_job}" if worker.current_job else ""
        return f"{worker.worker_id}: {worker.gpu} / {worker.status}{suffix}"
