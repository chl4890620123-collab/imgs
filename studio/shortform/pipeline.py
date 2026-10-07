from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .clipping import Highlight, find_highlights
from .reframe import render_vertical_clip


def run_local_clipping_pipeline(
    source: str | Path,
    output_dir: str | Path,
    *,
    num_highlights: int = 3,
    target_duration_sec: float = 30.0,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> dict:
    src = Path(source).resolve()
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    highlights = find_highlights(
        src,
        num_highlights=num_highlights,
        target_duration_sec=target_duration_sec,
    )
    outputs = []
    for idx, highlight in enumerate(highlights, 1):
        dest = out_dir / f"short_{idx:02d}.mp4"
        render_vertical_clip(
            src,
            highlight,
            dest,
            width=width,
            height=height,
            fps=fps,
        )
        outputs.append(
            {
                "index": idx,
                "file": str(dest),
                "highlight": highlight.to_dict(),
            }
        )

    return {
        "source": str(src),
        "output_dir": str(out_dir),
        "count": len(outputs),
        "outputs": outputs,
    }
