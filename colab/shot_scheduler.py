"""Small, independently checkpointed GPU render bursts.

No CUDA/model imports. Each render command is bounded, and status is persisted
on Drive so interruptions cannot accidentally mark a clip as complete.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class RenderResult:
    returncode: int
    output_tail: str
    elapsed_seconds: float
    timed_out: bool = False


def write_checkpoint(path: str | Path, status: str, **details) -> dict:
    """Persist an *informational* status. Validated video is the sole completion authority."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat(), **details}
    staging = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with staging.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staging, path)
    finally:
        staging.unlink(missing_ok=True)
    return data


def can_start_another_clip(
    completed_in_batch: int,
    max_shots: int,
    elapsed_seconds: float,
    max_batch_seconds: float,
    average_clip_seconds: float | None = None,
) -> bool:
    """Conservative decision; never launch a job with insufficient time budget."""
    if max_shots < 1 or completed_in_batch >= max_shots:
        return False
    if max_batch_seconds <= 0:  # Explicitly disable the batch clock if requested.
        return True
    remaining = max_batch_seconds - elapsed_seconds
    if remaining <= 0:
        return False
    if completed_in_batch and average_clip_seconds is not None:
        return remaining >= max(60.0, average_clip_seconds * 1.25)
    return True


def run_render_command(command: Sequence[str], cwd: str | Path, timeout_seconds: float) -> RenderResult:
    """Run one CLI command, terminate its process group on a hard timeout."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    started = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(
            list(command), cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
        elapsed = time.monotonic() - started
        log.seek(0, os.SEEK_END)
        length = log.tell()
        log.seek(max(0, length - 6000))
        tail = log.read().decode("utf-8", errors="replace")
    return RenderResult(
        returncode=124 if timed_out else proc.returncode,
        output_tail=tail,
        elapsed_seconds=elapsed,
        timed_out=timed_out,
    )
