from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from saseok_colab_runner import existing_valid_clip


def test_resume_ignores_zero_byte_clip_and_non_video_sidecar(tmp_path: Path):
    (tmp_path / "shot_01.mp4").write_bytes(b"")
    (tmp_path / "shot_01.json").write_text("{}", encoding="utf-8")
    assert existing_valid_clip(tmp_path, 1) is None


def test_resume_rejects_undecodable_clip(tmp_path: Path):
    clip = tmp_path / "shot_02.mp4"
    clip.write_bytes(b"x" * 3000)
    with patch("saseok_colab_runner.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "invalid")):
        assert existing_valid_clip(tmp_path, 2) is None


def test_resume_accepts_clip_only_when_ffprobe_finds_video(tmp_path: Path):
    clip = tmp_path / "shot_03.mp4"
    clip.write_bytes(b"x" * 3000)
    with patch("saseok_colab_runner.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "video\n", "")):
        assert existing_valid_clip(tmp_path, 3) == clip
