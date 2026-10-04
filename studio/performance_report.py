from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class PerformanceRow:
    backend: str
    gpu: str
    resolution: str
    jobs: int
    success_rate: float
    avg_elapsed_sec: float | None
    avg_sec_per_frame: float | None
    avg_peak_vram_mb: float | None
    avg_gpu_utilization: float | None


def _avg(values: list[float]) -> float | None:
    return mean(values) if values else None


def build_performance_rows(jobs: Iterable[dict]) -> list[PerformanceRow]:
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for job in jobs:
        if job.get("status") not in {"done", "failed"}:
            continue
        inp = job.get("input") or {}
        metrics = job.get("metrics") or {}
        backend = str(job.get("backend") or "unknown")
        gpu = str(metrics.get("gpu_name") or "unknown")
        resolution = f"{inp.get('width', '?')}x{inp.get('height', '?')}"
        groups[(backend, gpu, resolution)].append(job)

    rows: list[PerformanceRow] = []
    for (backend, gpu, resolution), items in sorted(groups.items()):
        elapsed = [
            float((x.get("metrics") or {}).get("elapsed_sec"))
            for x in items
            if (x.get("metrics") or {}).get("elapsed_sec") is not None
        ]
        sec_per_frame = [
            float((x.get("metrics") or {}).get("sec_per_frame"))
            for x in items
            if (x.get("metrics") or {}).get("sec_per_frame") is not None
        ]
        peak_vram = [
            float((x.get("metrics") or {}).get("peak_vram_mb"))
            for x in items
            if (x.get("metrics") or {}).get("peak_vram_mb") is not None
        ]
        util = [
            float((x.get("metrics") or {}).get("avg_gpu_utilization"))
            for x in items
            if (x.get("metrics") or {}).get("avg_gpu_utilization") is not None
        ]
        successes = sum(1 for x in items if x.get("status") == "done")
        rows.append(PerformanceRow(
            backend=backend,
            gpu=gpu,
            resolution=resolution,
            jobs=len(items),
            success_rate=successes / len(items) * 100.0,
            avg_elapsed_sec=_avg(elapsed),
            avg_sec_per_frame=_avg(sec_per_frame),
            avg_peak_vram_mb=_avg(peak_vram),
            avg_gpu_utilization=_avg(util),
        ))
    return rows


def report_text(jobs: Iterable[dict]) -> str:
    rows = build_performance_rows(jobs)
    if not rows:
        return "완료/실패된 Colab 성능 기록이 아직 없습니다."

    lines = ["Colab GPU 성능 리포트"]
    for row in rows:
        elapsed = "-" if row.avg_elapsed_sec is None else f"{row.avg_elapsed_sec:.1f}s"
        spf = "-" if row.avg_sec_per_frame is None else f"{row.avg_sec_per_frame:.3f}s/frame"
        vram = "-" if row.avg_peak_vram_mb is None else f"{row.avg_peak_vram_mb:.0f}MB"
        util = "-" if row.avg_gpu_utilization is None else f"{row.avg_gpu_utilization:.0f}%"
        lines.append(
            f"- {row.backend} / {row.gpu} / {row.resolution}: "
            f"{row.jobs}건, 성공 {row.success_rate:.0f}%, "
            f"평균 {elapsed}, {spf}, peak VRAM {vram}, GPU {util}"
        )
    return "\n".join(lines)
