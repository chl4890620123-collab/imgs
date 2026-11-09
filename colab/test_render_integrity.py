"""CPU-only regression tests for resumable Colab clip checkpoints."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from render_integrity import episode_progress, is_valid_video, persist_validated_clip, valid_shot


class RenderIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "source.mp4"

    def make_video(self):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("ffmpeg/ffprobe not installed")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc2=size=128x128:rate=15",
             "-t", "1.0", "-c:v", "mpeg4", "-q:v", "4", self.video.as_posix()],
            check=True, capture_output=True, timeout=60,
        )

    def test_rejects_zero_and_truncated_files(self):
        empty = self.root / "empty.mp4"
        empty.write_bytes(b"")
        invalid = self.root / "truncated.mp4"
        invalid.write_bytes(b"x" * 16000)
        self.assertFalse(is_valid_video(empty))
        self.assertFalse(is_valid_video(invalid))

    def test_restart_skips_only_complete_valid_clips(self):
        self.make_video()
        clips_root = self.root / "clips"
        folder = clips_root / "scene_01"
        folder.mkdir(parents=True)
        episode = {"scenes": [{"id": 1, "shots": [("a", "x"), ("a", "y")]}]}
        (folder / "shot_02.mp4").write_bytes(b"broken" * 4000)
        self.assertEqual(episode_progress(episode, clips_root), (0, 2))
        self.assertIsNone(valid_shot(clips_root, 1, 2))
        persist_validated_clip(self.video, folder / "shot_01.mp4")
        self.assertEqual(episode_progress(episode, clips_root), (1, 2))
        self.assertFalse(is_valid_video(self.video, minimum_duration=10.0))
        self.assertTrue(is_valid_video(self.video, minimum_duration=0.5))
        self.assertIsNotNone(valid_shot(clips_root, 1, 1))
        self.assertEqual(list(folder.glob("*.part")), [])

    def test_atomic_copy_rejects_invalid_source(self):
        invalid = self.root / "broken.mp4"
        invalid.write_bytes(b"not video" * 5000)
        with self.assertRaises(ValueError):
            persist_validated_clip(invalid, self.root / "clips/scene_01/shot_01.mp4")
        self.assertFalse((self.root / "clips/scene_01/shot_01.mp4").exists())


if __name__ == "__main__":
    unittest.main()
