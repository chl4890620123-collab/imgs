from __future__ import annotations

import argparse
import json
from pathlib import Path

from shortform.clipping import find_highlights
from shortform.pipeline import run_local_clipping_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Saseok Shortform Factory")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="긴 영상의 숏폼 후보 구간 분석")
    analyze.add_argument("source")
    analyze.add_argument("--count", type=int, default=3)
    analyze.add_argument("--duration", type=float, default=30.0)

    render = sub.add_parser("render", help="후보 구간을 9:16 MP4로 렌더")
    render.add_argument("source")
    render.add_argument("--output-dir", default="media/shorts")
    render.add_argument("--count", type=int, default=3)
    render.add_argument("--duration", type=float, default=30.0)
    render.add_argument("--width", type=int, default=1080)
    render.add_argument("--height", type=int, default=1920)
    render.add_argument("--fps", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = Path(args.source).expanduser().resolve()

    if args.command == "analyze":
        highlights = find_highlights(
            source,
            num_highlights=max(1, min(20, args.count)),
            target_duration_sec=max(6.0, min(60.0, args.duration)),
        )
        payload = {
            "source": str(source),
            "provider": "local",
            "highlights": [x.to_dict() for x in highlights],
        }
    else:
        payload = run_local_clipping_pipeline(
            source,
            Path(args.output_dir).expanduser().resolve(),
            num_highlights=max(1, min(20, args.count)),
            target_duration_sec=max(6.0, min(60.0, args.duration)),
            width=max(180, min(2160, args.width)),
            height=max(320, min(3840, args.height)),
            fps=max(1, min(60, args.fps)),
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
