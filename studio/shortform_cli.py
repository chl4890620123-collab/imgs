from __future__ import annotations

import argparse
import json
from pathlib import Path

from shortform.clipping import find_highlights
from shortform.pipeline import run_local_clipping_pipeline
from shortform.quality_pipeline import analyze_quality_shortform, run_quality_shortform_pipeline


def _add_quality_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--quality", choices=["preview", "high", "cinematic"], default="high")
    parser.add_argument("--whisper-model", default="medium")
    parser.add_argument("--language", default="ko")
    parser.add_argument("--no-whisper", action="store_true")
    parser.add_argument(
        "--strict-transcript",
        action="store_true",
        help="Whisper가 준비되지 않았으면 fallback하지 않고 실패",
    )


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

    analyze_q = sub.add_parser(
        "analyze-quality",
        help="Whisper 의미 분석 + 피사체 보존 레이아웃으로 후보 분석",
    )
    analyze_q.add_argument("source")
    analyze_q.add_argument("--count", type=int, default=3)
    analyze_q.add_argument("--duration", type=float, default=30.0)
    _add_quality_options(analyze_q)

    render_q = sub.add_parser(
        "render-quality",
        help="자막/음량/피사체 보존/품질검증을 포함한 고품질 숏폼 렌더",
    )
    render_q.add_argument("source")
    render_q.add_argument("--output-dir", default="media/shorts-quality")
    render_q.add_argument("--count", type=int, default=3)
    render_q.add_argument("--duration", type=float, default=30.0)
    _add_quality_options(render_q)
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
    elif args.command == "render":
        payload = run_local_clipping_pipeline(
            source,
            Path(args.output_dir).expanduser().resolve(),
            num_highlights=max(1, min(20, args.count)),
            target_duration_sec=max(6.0, min(60.0, args.duration)),
            width=max(180, min(2160, args.width)),
            height=max(320, min(3840, args.height)),
            fps=max(1, min(60, args.fps)),
        )
    elif args.command == "analyze-quality":
        payload = analyze_quality_shortform(
            source,
            num_highlights=max(1, min(20, args.count)),
            target_duration_sec=max(6.0, min(60.0, args.duration)),
            use_whisper=not args.no_whisper,
            whisper_model=args.whisper_model,
            language=args.language or None,
            strict_transcript=args.strict_transcript,
        )
    else:
        payload = run_quality_shortform_pipeline(
            source,
            Path(args.output_dir).expanduser().resolve(),
            num_highlights=max(1, min(20, args.count)),
            target_duration_sec=max(6.0, min(60.0, args.duration)),
            quality=args.quality,
            use_whisper=not args.no_whisper,
            whisper_model=args.whisper_model,
            language=args.language or None,
            strict_transcript=args.strict_transcript,
        )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
