from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass
class VoiceProfile:
    mode: str = "ai"  # ai | external | muted
    model: str = "gemini-3.8-flash-lite-tts"
    voice_name: str = "Kore"
    age: int = 50
    pitch: int = 50
    speed: int = 50
    emotion: int = 50
    power: int = 50
    distance: int = 20
    direction: str = ""

    def style_text(self) -> str:
        def band(v: int, low: str, mid: str, high: str) -> str:
            return low if v < 34 else high if v > 66 else mid
        return ", ".join([
            band(self.age, "젊은 느낌", "자연스러운 성인", "성숙한 느낌"),
            band(self.pitch, "낮은 음역", "중간 음역", "높은 음역"),
            band(self.speed, "천천히", "보통 속도", "빠르게"),
            band(self.emotion, "감정 절제", "자연스러운 감정", "감정 강하게"),
            band(self.power, "작고 부드럽게", "일반 발성", "강한 발성"),
            band(self.distance, "마이크 가까이", "일반 거리", "멀리서 말하는 느낌"),
            self.direction.strip(),
        ]).strip(", ")


@dataclass
class DialogueLine:
    id: str
    scene_id: int
    character: str
    text: str
    start: float
    end: float
    ai_audio: Optional[str] = None
    external_audio: Optional[str] = None
    source_override: Optional[str] = None  # ai | external | muted | None


@dataclass
class Scene:
    id: int
    title: str
    start: float
    duration: float
    visual: Optional[str] = None
    description: Optional[str] = None
    shot_prompts: list[str] = field(default_factory=list)


@dataclass
class Shot:
    id: str
    scene_id: int
    start: float
    duration: float
    prompt: str
    reference_key: Optional[str] = None
    visual: Optional[str] = None
    generation_status: str = "pending"  # pending | queued | generating | ready | failed
    quality_score: Optional[float] = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class StudioProject:
    title: str
    fps: int = 24
    width: int = 1280
    height: int = 720
    characters: dict[str, VoiceProfile] = field(default_factory=dict)
    scenes: list[Scene] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    dialogue: list[DialogueLine] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "StudioProject":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        raw["characters"] = {k: VoiceProfile(**v) for k, v in raw.get("characters", {}).items()}
        raw["scenes"] = [Scene(**x) for x in raw.get("scenes", [])]
        raw["shots"] = [Shot(**x) for x in raw.get("shots", [])]
        raw["dialogue"] = [DialogueLine(**x) for x in raw.get("dialogue", [])]
        return cls(**raw)

    def save(self, path: str | Path) -> None:
        data = asdict(self)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def profile(self, character: str) -> VoiceProfile:
        if character not in self.characters:
            self.characters[character] = VoiceProfile()
        return self.characters[character]

    def scene_shots(self, scene_id: int) -> list[Shot]:
        return sorted(
            [x for x in self.shots if x.scene_id == scene_id],
            key=lambda x: x.start,
        )

    def shot(self, shot_id: str) -> Shot:
        found = next((x for x in self.shots if x.id == shot_id), None)
        if found is None:
            raise KeyError(shot_id)
        return found

    def line_audio(self, line: DialogueLine) -> Optional[str]:
        profile = self.profile(line.character)
        mode = line.source_override or profile.mode
        if mode == "muted":
            return None
        if mode == "external":
            return line.external_audio
        return line.ai_audio
