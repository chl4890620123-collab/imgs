"""CPU-only regression checks for short GPU call / checkpoint orchestration."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from shot_scheduler import can_start_another_clip, run_render_command, write_checkpoint


class ShortBurstTests(unittest.TestCase):
    def test_job_count_limit_and_predictive_budget(self):
        self.assertTrue(can_start_another_clip(0, 2, 0, 3000))
        self.assertTrue(can_start_another_clip(1, 2, 900, 3000, 900))
        self.assertFalse(can_start_another_clip(1, 2, 1900, 3000, 900))
        self.assertFalse(can_start_another_clip(2, 2, 300, 3000, 100))
        self.assertFalse(can_start_another_clip(0, 2, 3000, 3000))
        self.assertTrue(can_start_another_clip(0, 2, 4000, 0))  # explicitly unbounded
        self.assertFalse(can_start_another_clip(0, 0, 0, 3000))

    def test_render_success_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            ok = run_render_command(
                [sys.executable, "-c", "print('completed')"],
                directory, timeout_seconds=5,
            )
            self.assertEqual(ok.returncode, 0)
            self.assertFalse(ok.timed_out)
            self.assertIn("completed", ok.output_tail)

            timed = run_render_command(
                [sys.executable, "-c", "import time;time.sleep(5)"],
                directory, timeout_seconds=0.3,
            )
            self.assertEqual(timed.returncode, 124)
            self.assertTrue(timed.timed_out)
            self.assertLess(timed.elapsed_seconds, 4.5)

    def test_checkpoint_survives_restart_and_is_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "state" / "scene_01_shot_01.json"
            write_checkpoint(p, "running", scene_id=1, shot_idx=1, attempt=1)
            self.assertEqual(json.loads(p.read_text())["status"], "running")
            write_checkpoint(p, "done", scene_id=1, shot_idx=1, clip="clips/scene_01/shot_01.mp4")
            status = json.loads(p.read_text())
            self.assertEqual(status["status"], "done")
            self.assertEqual(status["scene_id"], 1)
            self.assertFalse(list(p.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
