from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from full_episode import EXPECTED_SHOTS, episode_videos_ready, submit_full_episode
from project import Scene, Shot, StudioProject
from remote_jobs import RemoteQueue
from video_recipe import RecipeStore


class FullEpisodeTests(unittest.TestCase):
    def make_project(self, root: Path):
        scenes = [Scene(i, f"Scene {i}", (i - 1) * 8, 8) for i in range(1, 16)]
        shots = [
            Shot(f"S{scene_id:02d}_SH{n:02d}", scene_id, (scene_id - 1) * 8 + n - 1,
                 1, "cinematic action")
            for scene_id in range(1, 16) for n in range(1, 9)
        ]
        project = StudioProject(title="test", scenes=scenes, shots=shots)
        path = root / "project.json"
        project.save(path)
        return project, path, RecipeStore(root / "recipes.json")

    def test_queues_all_120_shots_not_scene_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, path, recipes = self.make_project(root)
            queue = RemoteQueue(root / "queue")
            result = submit_full_episode(project, path, recipes, queue)
            self.assertEqual(EXPECTED_SHOTS, result.submitted)
            self.assertEqual(120, len(queue.list_jobs(["queued"])))

    def test_reuses_video_and_does_not_duplicate_active_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, path, recipes = self.make_project(root)
            video = root / "media" / "generated" / "S01_SH01.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            project.shot("S01_SH01").visual = "media/generated/S01_SH01.mp4"
            queue = RemoteQueue(root / "queue")
            first = submit_full_episode(project, path, recipes, queue)
            second = submit_full_episode(project, path, recipes, queue)
            self.assertEqual(119, first.submitted)
            self.assertEqual(0, second.submitted)
            self.assertEqual(1, second.reused_videos)

    def test_rejects_non_ltx_backend_and_non_120_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, path, recipes = self.make_project(root)
            recipes.get(2).inference.backend = "unsupported"
            with self.assertRaises(ValueError):
                submit_full_episode(project, path, recipes, RemoteQueue(root / "queue"))
            recipes.get(2).inference.backend = "ltx-2b"
            project.shots.pop()
            with self.assertRaises(ValueError):
                submit_full_episode(project, path, recipes, RemoteQueue(root / "queue"))

    def test_ready_requires_all_120_existing_video_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project, _, _ = self.make_project(root)
            self.assertFalse(episode_videos_ready(project, root))


if __name__ == "__main__":
    unittest.main()
