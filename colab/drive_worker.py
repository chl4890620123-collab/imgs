from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def frames_for_duration(duration_sec: float, fps: int) -> int:
    desired = max(9, round(duration_sec * fps))
    n = max(1, min(32, round((desired - 1) / 8)))
    return n * 8 + 1


class DriveWorker:
    def __init__(
        self,
        queue_root: Path,
        ltx_home: Path,
        poll_seconds: float = 5.0,
        worker_id: str | None = None,
    ):
        self.root = queue_root.resolve()
        self.ltx_home = ltx_home.resolve()
        self.poll_seconds = max(1.0, poll_seconds)
        self.worker_id = worker_id or f"colab-{socket.gethostname()}"
        self.queued = self.root / "jobs" / "queued"
        self.running = self.root / "jobs" / "running"
        self.done = self.root / "jobs" / "done"
        self.failed = self.root / "jobs" / "failed"
        self.cancelled = self.root / "jobs" / "cancelled"
        self.outputs = self.root / "outputs" / "shots"
        self.logs = self.root / "outputs" / "logs"
        self.heartbeat = self.root / "workers" / "heartbeat" / f"{self.worker_id}.json"
        for path in [
            self.queued, self.running, self.done, self.failed, self.cancelled,
            self.outputs, self.logs, self.heartbeat.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def gpu_snapshot(self) -> dict:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            row = result.stdout.strip().splitlines()[0]
            name, total, used, util, temp = [x.strip() for x in row.split(",", 4)]
            return {
                "gpu_name": name or "CUDA GPU",
                "memory_total_mb": float(total),
                "memory_used_mb": float(used),
                "gpu_utilization": float(util),
                "temperature_c": float(temp),
            }
        except Exception:
            return {
                "gpu_name": "unknown",
                "memory_total_mb": None,
                "memory_used_mb": None,
                "gpu_utilization": None,
                "temperature_c": None,
            }

    def gpu_name(self) -> str:
        return str(self.gpu_snapshot().get("gpu_name") or "unknown")

    def write_heartbeat(self, status: str, job_id: str | None = None) -> None:
        snapshot = self.gpu_snapshot()
        atomic_json(self.heartbeat, {
            "worker_id": self.worker_id,
            "status": status,
            "gpu": snapshot["gpu_name"],
            "memory_total_mb": snapshot["memory_total_mb"],
            "memory_used_mb": snapshot["memory_used_mb"],
            "gpu_utilization": snapshot["gpu_utilization"],
            "temperature_c": snapshot["temperature_c"],
            "current_job": job_id,
            "updated_at": utc_now(),
        })

    def pick_job(self) -> Path | None:
        candidates = []
        for path in self.queued.glob("*.json"):
            try:
                job = read_json(path)
                candidates.append((
                    -int(job.get("priority", 50)),
                    job.get("created_at", ""),
                    path,
                ))
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort()
        source = candidates[0][2]
        target = self.running / source.name
        try:
            source.replace(target)
        except FileNotFoundError:
            return None
        job = read_json(target)
        job.update({
            "status": "running",
            "stage": "claimed_by_worker",
            "progress": 5,
            "worker_id": self.worker_id,
            "started_at": job.get("started_at") or utc_now(),
            "updated_at": utc_now(),
        })
        atomic_json(target, job)
        return target

    def update(self, path: Path, **changes) -> dict:
        job = read_json(path)
        job.update(changes)
        job["updated_at"] = utc_now()
        atomic_json(path, job)
        return job

    def reference_path(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        path = self.root / rel
        return path if path.exists() else None

    def command(self, job: dict, output_dir: Path) -> list[str]:
        if job.get("backend") != "ltx-2b":
            raise RuntimeError(
                f"현재 Colab 워커는 ltx-2b만 직접 실행합니다: {job.get('backend')}"
            )
        inp = job["input"]
        config = self.ltx_home / inp.get(
            "pipeline_config", "configs/ltxv-2b-0.9.8-distilled.yaml"
        )
        cmd = [
            sys.executable,
            str(self.ltx_home / "inference.py"),
            "--prompt", str(inp["prompt"]),
            "--output_path", str(output_dir),
            "--height", str(inp["height"]),
            "--width", str(inp["width"]),
            "--num_frames", str(frames_for_duration(inp["duration_sec"], inp["fps"])),
            "--frame_rate", str(inp["fps"]),
            "--seed", str(inp["seed"]),
            "--negative_prompt", str(inp.get("negative_prompt", "")),
            "--pipeline_config", str(config),
        ]
        refs = job.get("references") or {}
        conditions: list[tuple[Path, int]] = []
        start = self.reference_path(refs.get("start_frame"))
        character = self.reference_path(refs.get("character_reference"))
        shot_ref = self.reference_path(refs.get("shot_reference"))
        end = self.reference_path(refs.get("end_frame"))
        for candidate in (start, character, shot_ref):
            if candidate and not conditions:
                conditions.append((candidate, 0))
        if end:
            frame_count = frames_for_duration(inp["duration_sec"], inp["fps"])
            conditions.append((end, max(0, frame_count - 1)))
        if conditions:
            cmd += ["--conditioning_media_paths", *[str(x[0]) for x in conditions]]
            cmd += ["--conditioning_start_frames", *[str(x[1]) for x in conditions]]
        return cmd

    def process(self, path: Path) -> None:
        job = read_json(path)
        job_id = job["job_id"]
        log_path = self.root / job["output"]["log_file"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_heartbeat("generating", job_id)

        if job.get("cancel_requested"):
            self.finish(path, "cancelled", stage="cancelled_before_generation")
            return

        with tempfile.TemporaryDirectory(prefix=f"saseok_{job_id}_") as td:
            output_dir = Path(td) / "out"
            output_dir.mkdir(parents=True, exist_ok=True)
            cmd = self.command(job, output_dir)
            self.update(path, stage="generate", progress=20)

            with log_path.open("a", encoding="utf-8") as log:
                log.write("\n=== " + utc_now() + " ===\n")
                log.write(" ".join(cmd[:2]) + " [arguments hidden in UI]\n")
                log.flush()
                started = time.perf_counter()
                frame_count = frames_for_duration(
                    job["input"]["duration_sec"],
                    job["input"]["fps"],
                )
                gpu_samples: list[dict] = []
                process = subprocess.Popen(
                    cmd,
                    cwd=self.ltx_home,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                while process.poll() is None:
                    time.sleep(3)
                    current = read_json(path)
                    snapshot = self.gpu_snapshot()
                    gpu_samples.append(snapshot)
                    if current.get("cancel_requested"):
                        process.terminate()
                        try:
                            process.wait(timeout=12)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        elapsed = max(0.001, time.perf_counter() - started)
                        self.finish(
                            path,
                            "cancelled",
                            stage="cancelled_during_generation",
                            metrics=self._metrics(gpu_samples, elapsed, frame_count),
                        )
                        return
                    self.update(path, stage="generate", progress=55)
                    self.write_heartbeat("generating", job_id)

                elapsed = max(0.001, time.perf_counter() - started)
                if not gpu_samples:
                    gpu_samples.append(self.gpu_snapshot())
                metrics = self._metrics(gpu_samples, elapsed, frame_count)
                self.update(path, metrics=metrics)

                if process.returncode != 0:
                    raise RuntimeError(f"LTX 종료 코드 {process.returncode}")

            clips = sorted(
                output_dir.glob("*.mp4"),
                key=lambda p: p.stat().st_mtime_ns,
            )
            if not clips:
                raise RuntimeError("LTX 출력 MP4를 찾지 못했습니다.")

            self.update(path, stage="copy_result", progress=92)
            result = self.root / job["output"]["result_file"]
            result.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clips[-1], result)
            current = read_json(path)
            metrics = dict(current.get("metrics") or {})
            metrics["output_bytes"] = result.stat().st_size
            metrics["output_megabytes"] = round(result.stat().st_size / 1024 / 1024, 3)
            self.finish(
                path,
                "done",
                stage="ready_for_studio",
                progress=100,
                finished_at=utc_now(),
                error=None,
                metrics=metrics,
            )

    @staticmethod
    def _metrics(samples: list[dict], elapsed: float, frame_count: int) -> dict:
        used = [
            float(x["memory_used_mb"])
            for x in samples
            if x.get("memory_used_mb") is not None
        ]
        util = [
            float(x["gpu_utilization"])
            for x in samples
            if x.get("gpu_utilization") is not None
        ]
        temps = [
            float(x["temperature_c"])
            for x in samples
            if x.get("temperature_c") is not None
        ]
        total = next(
            (float(x["memory_total_mb"]) for x in samples if x.get("memory_total_mb") is not None),
            None,
        )
        gpu_name = next(
            (str(x["gpu_name"]) for x in samples if x.get("gpu_name") not in {None, "unknown"}),
            "unknown",
        )
        return {
            "gpu_name": gpu_name,
            "gpu_memory_total_mb": total,
            "peak_vram_mb": max(used) if used else None,
            "avg_gpu_utilization": sum(util) / len(util) if util else None,
            "peak_temperature_c": max(temps) if temps else None,
            "elapsed_sec": elapsed,
            "frames": int(frame_count),
            "sec_per_frame": elapsed / frame_count if frame_count else None,
            "generated_frames_per_sec": frame_count / elapsed if elapsed else None,
            "sample_count": len(samples),
        }

    def finish(self, path: Path, state: str, **changes) -> None:
        job = read_json(path)
        job.update(changes)
        job["status"] = state
        job["updated_at"] = utc_now()
        target_folder = {
            "done": self.done,
            "failed": self.failed,
            "cancelled": self.cancelled,
        }[state]
        target = target_folder / path.name
        atomic_json(target, job)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def fail_or_retry(self, path: Path, exc: Exception) -> None:
        job = read_json(path)
        retry = dict(job.get("retry") or {})
        count = int(retry.get("count", 0))
        maximum = int(retry.get("max", 2))
        retry["count"] = count + 1
        job["retry"] = retry
        job["error"] = str(exc)
        job["updated_at"] = utc_now()
        if count < maximum:
            job.update({
                "status": "queued",
                "stage": "automatic_retry",
                "progress": 0,
                "worker_id": None,
            })
            target = self.queued / path.name
        else:
            job.update({
                "status": "failed",
                "stage": "failed",
                "finished_at": utc_now(),
            })
            target = self.failed / path.name
        atomic_json(target, job)
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def loop(self, once: bool = False) -> None:
        if not (self.ltx_home / "inference.py").exists():
            raise FileNotFoundError(self.ltx_home / "inference.py")
        self.write_heartbeat("idle")
        while True:
            job_path = self.pick_job()
            if job_path is None:
                self.write_heartbeat("idle")
                if once:
                    return
                time.sleep(self.poll_seconds)
                continue
            try:
                self.process(job_path)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.fail_or_retry(job_path, exc)
            finally:
                self.write_heartbeat("idle")
            if once:
                return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue-root",
        default="/content/drive/MyDrive/SASEOK_GPU_QUEUE",
    )
    parser.add_argument(
        "--ltx-home",
        default="/content/LTX-Video",
    )
    parser.add_argument("--poll", type=float, default=5.0)
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    worker = DriveWorker(
        Path(args.queue_root),
        Path(args.ltx_home),
        poll_seconds=args.poll,
        worker_id=args.worker_id,
    )
    worker.loop(once=args.once)


if __name__ == "__main__":
    main()
