from __future__ import annotations

import tempfile
from pathlib import Path

from drive_worker import DriveWorker
from project import Scene, Shot, StudioProject
from remote_jobs import RemoteQueue
from video_recipe import VideoRecipe, apply_preset


FAKE_INFERENCE = r'''
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--output_path", required=True)
args, _ = parser.parse_known_args()
out = Path(args.output_path)
out.mkdir(parents=True, exist_ok=True)
(out / "fake_generated.mp4").write_bytes(b"fake-generated-video")
'''


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        queue_root = root / "queue"
        ltx_home = root / "LTX-Video"
        ltx_home.mkdir(parents=True)
        (ltx_home / "inference.py").write_text(FAKE_INFERENCE, encoding="utf-8")

        project = StudioProject(
            title="worker-test",
            scenes=[Scene(9, "이세계", 0.0, 4.0)],
            shots=[
                Shot(
                    "S09_SH01",
                    9,
                    0.0,
                    4.0,
                    "Ria runs toward Jin-woo before an arrow lands",
                )
            ],
        )
        shot = project.shot("S09_SH01")
        recipe = apply_preset(VideoRecipe(scene_id=9), "fast")
        recipe.inference.backend = "ltx-2b"

        queue = RemoteQueue(queue_root)
        job = queue.submit_shot(project, shot, recipe, root)

        worker = DriveWorker(
            queue_root,
            ltx_home,
            poll_seconds=1,
            worker_id="ci-worker",
        )
        worker.loop(once=True)

        done = queue.find_job(job["job_id"])
        assert done is not None
        assert done["status"] == "done"
        assert done["stage"] == "ready_for_studio"
        metrics = done.get("metrics") or {}
        assert metrics.get("elapsed_sec") is not None
        assert metrics.get("frames") is not None
        assert metrics.get("sec_per_frame") is not None
        assert metrics.get("output_bytes") == len(b"fake-generated-video")
        output = queue.root / done["output"]["result_file"]
        assert output.exists()
        print("drive worker integration ok")


if __name__ == "__main__":
    main()
