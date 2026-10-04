from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from performance_report import build_performance_rows, report_text
from remote_jobs import RemoteQueue


def main() -> None:
    parser = argparse.ArgumentParser(description="Saseok Colab GPU benchmark report")
    parser.add_argument("queue_root", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, default=None)
    args = parser.parse_args()

    queue = RemoteQueue(args.queue_root)
    jobs = queue.list_jobs(["done", "failed"])
    rows = build_performance_rows(jobs)
    print(report_text(jobs))

    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(
            json.dumps([asdict(x) for x in rows], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 저장: {args.json_path}")


if __name__ == "__main__":
    main()
