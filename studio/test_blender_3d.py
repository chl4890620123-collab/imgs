"""Non-GPU tests for Blender 3D project integration and resumable frames."""
from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from blender_3d import (
    add_model_asset, attach_start_frame, init_workspace, load_spec,
    project_and_shot, valid_png, workspace,
)
from project import Scene, Shot, StudioProject


def fake_valid_png(path: Path) -> None:
    """Construct a 1x1 PNG with correct chunks and CRCs for checkpoint testing."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(
            ">I", zlib.crc32(kind + data) & 0xFFFFFFFF
        )

    raw = b"\x00\xff\x00\x00"
    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class BlenderIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project_file = self.root / "saseok_studio_project.json"
        StudioProject(
            title="3D smoke test", fps=12, width=320, height=180,
            scenes=[Scene(id=1, title="Test", start=0.0, duration=1.0)],
            shots=[Shot(id="S01_SH01", scene_id=1, start=0.0,
                        duration=1.0, prompt="3D turntable")],
        ).save(self.project_file)

    def test_initial_scene_and_repeat_are_non_destructive(self):
        path = init_workspace(self.project_file, "S01_SH01")
        spec = load_spec(path, self.root)
        self.assertEqual(spec["frames"], 12)
        self.assertEqual(spec["width"], 320)
        self.assertTrue(any(item["keyframes"] for item in spec["objects"]
                            if item.get("type") == "cube"))
        path.write_text(path.read_text() + " ", encoding="utf-8")
        self.assertEqual(init_workspace(self.project_file, "S01_SH01"), path)
        self.assertTrue(path.read_text().endswith(" "))

    def test_model_import_remains_inside_project_and_keeps_original(self):
        model = self.root / "actor.glb"
        model.write_bytes(b"placeholder GLB file")
        imported = add_model_asset(self.project_file, "S01_SH01", model)
        self.assertTrue(imported.exists())
        self.assertEqual(imported.parent.name, "models")
        spec = load_spec(self.root / "media/3d/S01_SH01/scene.json", self.root)
        self.assertEqual(spec["objects"][-1]["type"], "import")
        self.assertEqual(spec["objects"][-1]["source"],
                         "media/3d/S01_SH01/models/actor.glb")
        (self.root / "media/3d/S01_SH01/scene.blend").write_bytes(b"blend")
        with self.assertRaises(RuntimeError):
            add_model_asset(self.project_file, "S01_SH01", model)

    def test_rejects_path_traversal_and_invalid_scene_specs(self):
        with self.assertRaises(ValueError):
            project_and_shot(self.project_file, "../../bad")
        path = init_workspace(self.project_file, "S01_SH01")
        spec = load_spec(path, self.root)
        spec["objects"].append({"type": "import", "source": "../../secret.glb"})
        path.write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_spec(path, self.root)

    def test_corrupted_image_is_not_a_checkpoint(self):
        p = self.root / "frame.png"
        fake_valid_png(p)
        self.assertTrue(valid_png(p))
        raw = p.read_bytes()
        p.write_bytes(raw[:-8])
        self.assertFalse(valid_png(p))
        p.write_bytes(raw[:-12] + b"012345678901")
        self.assertFalse(valid_png(p))

    def test_ai_start_frame_rejects_stale_scene(self):
        init_workspace(self.project_file, "S01_SH01")
        folder = workspace(self.root, "S01_SH01")
        blend = folder / "scene.blend"
        blend.write_bytes(b"placeholder blend")
        fake_valid_png(folder / "preview.png")
        with self.assertRaises(FileNotFoundError):
            attach_start_frame(self.project_file, "S01_SH01")


if __name__ == "__main__":
    unittest.main()
