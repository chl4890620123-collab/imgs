from __future__ import annotations

import json
import shutil
from pathlib import Path

from video_recipe import VideoRecipe


class VideoCache:
    """Cache expensive model outputs independently from local editing."""

    def __init__(self, project_root: str | Path):
        self.root = Path(project_root)
        self.cache_dir = self.root / "media" / "generated" / ".cache"
        self.index_path = self.cache_dir / "index.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index = self._load()

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self) -> None:
        self.index_path.write_text(
            json.dumps(self.index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def key(self, recipe: VideoRecipe, slot: int) -> str:
        return f"s{recipe.scene_id:02d}_c{slot:02d}_{recipe.inference_fingerprint(self.root)}"

    def lookup(self, recipe: VideoRecipe, slot: int) -> Path | None:
        key = self.key(recipe, slot)
        rel = self.index.get(key)
        if not rel:
            return None
        p = self.root / rel
        return p if p.exists() else None

    def put(self, recipe: VideoRecipe, slot: int, source: str | Path) -> Path:
        src = Path(source)
        key = self.key(recipe, slot)
        dst = self.cache_dir / f"{key}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        self.index[key] = str(dst.relative_to(self.root)).replace("\\", "/")
        self._save()
        return dst

    def missing_slots(self, recipe: VideoRecipe) -> list[int]:
        return [slot for slot in range(1, recipe.call_budget + 1) if self.lookup(recipe, slot) is None]
