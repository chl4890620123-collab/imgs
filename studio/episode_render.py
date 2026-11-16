from __future__ import annotations

import sys
from pathlib import Path

from project import StudioProject
from render import render


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: episode_render.py PROJECT_JSON OUTPUT_MP4", file=sys.stderr)
        return 2
    project_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    render(StudioProject.load(project_path), project_path.parent, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
