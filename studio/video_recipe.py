from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class InferenceSettings:
    backend: str = "ltx-2b"
    width: int = 768
    height: int = 432
    duration_sec: float = 6.0
    fps: int = 24
    steps: int = 12
    guidance: float = 4.0
    seed: int = 1
    motion_strength: int = 58
    character_lock: int = 82
    creative_prompt: str = ""
    camera_prompt: str = "slow cinematic push-in"
    negative_prompt: str = "flicker, duplicate limbs, warped face, text, watermark"
    start_frame: str | None = None
    end_frame: str | None = None
    character_reference: str | None = None


@dataclass
class LocalPostSettings:
    upscale: bool = True
    upscale_target: str = "1080p"
    interpolation: bool = True
    interpolation_fps: int = 48
    stabilization: int = 20
    camera_zoom: int = 8
    camera_pan_x: int = 0
    camera_pan_y: int = 0
    shake: int = 0
    contrast: int = 50
    saturation: int = 45
    sharpness: int = 50
    film_grain: int = 12
    motion_blur: int = 18
    vignette: int = 10
    speed_percent: int = 100


@dataclass
class VideoRecipe:
    scene_id: int
    preset: str = "high"
    call_budget: int = 2
    inference: InferenceSettings = field(default_factory=InferenceSettings)
    post: LocalPostSettings = field(default_factory=LocalPostSettings)

    def inference_fingerprint(self, project_root: str | Path | None = None) -> str:
        """Only settings that really require a model call are hashed.

        Color, subtitles, audio, zoom/pan, interpolation and upscaling are local
        post operations, so changing them never throws away an expensive AI clip.
        """
        payload = asdict(self.inference)
        root = Path(project_root) if project_root else None
        for key in ("start_frame", "end_frame", "character_reference"):
            value = payload.get(key)
            if not value:
                continue
            p = Path(value)
            if root and not p.is_absolute():
                p = root / p
            if p.exists() and p.is_file():
                stat = p.stat()
                payload[key] = {
                    "path": str(value),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]


PRESETS: dict[str, dict] = {
    "fast": {
        "label": "빠르게",
        "call_budget": 1,
        "backend": "ltx-2b",
        "size": (640, 360),
        "steps": 8,
        "duration": 5.0,
        "motion": 50,
        "character_lock": 76,
    },
    "high": {
        "label": "고화질",
        "call_budget": 2,
        "backend": "ltx-2b",
        "size": (768, 432),
        "steps": 12,
        "duration": 6.0,
        "motion": 58,
        "character_lock": 84,
    },
    "cinematic": {
        "label": "시네마틱",
        "call_budget": 2,
        "backend": "ltx-2b",
        "size": (832, 480),
        "steps": 16,
        "duration": 6.0,
        "motion": 62,
        "character_lock": 88,
    },
}


def apply_preset(recipe: VideoRecipe, preset: str) -> VideoRecipe:
    spec = PRESETS[preset]
    recipe.preset = preset
    recipe.call_budget = spec["call_budget"]
    inf = recipe.inference
    inf.backend = spec["backend"]
    inf.width, inf.height = spec["size"]
    inf.steps = spec["steps"]
    inf.duration_sec = spec["duration"]
    inf.motion_strength = spec["motion"]
    inf.character_lock = spec["character_lock"]
    return recipe


class RecipeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.recipes: dict[int, VideoRecipe] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for key, item in raw.items():
            inf = InferenceSettings(**item.get("inference", {}))
            post = LocalPostSettings(**item.get("post", {}))
            self.recipes[int(key)] = VideoRecipe(
                scene_id=int(item.get("scene_id", key)),
                preset=item.get("preset", "high"),
                call_budget=int(item.get("call_budget", 2)),
                inference=inf,
                post=post,
            )

    def get(self, scene_id: int) -> VideoRecipe:
        if scene_id not in self.recipes:
            self.recipes[scene_id] = apply_preset(VideoRecipe(scene_id), "high")
        return self.recipes[scene_id]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {str(k): asdict(v) for k, v in sorted(self.recipes.items())}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def estimate_calls(scene_count: int, preset: str) -> int:
    return scene_count * int(PRESETS[preset]["call_budget"])
