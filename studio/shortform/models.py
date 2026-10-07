from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelineMode(str, Enum):
    GENERATE = "generate"
    CLIP = "clip"


class ProviderPreference(str, Enum):
    AUTO = "auto"
    LOCAL = "local"
    CLOUD = "cloud"


class StepKind(str, Enum):
    PLAN = "plan"
    IMAGE_GENERATE = "image_generate"
    VIDEO_GENERATE = "video_generate"
    CLIP_DETECT = "clip_detect"
    REFRAME = "reframe"
    MOTION = "motion"
    AUDIO = "audio"
    LIP_SYNC = "lip_sync"
    CAPTIONS = "captions"
    QUALITY_REVIEW = "quality_review"
    RENDER = "render"


@dataclass(frozen=True)
class MediaInput:
    kind: str
    value: str
    role: str = "source"


@dataclass(frozen=True)
class ShortformRequest:
    title: str
    mode: PipelineMode = PipelineMode.GENERATE
    prompt: str = ""
    target_duration_sec: float = 30.0
    aspect_ratio: str = "9:16"
    language: str = "ko-KR"
    provider: ProviderPreference = ProviderPreference.AUTO
    media: tuple[MediaInput, ...] = ()
    enable_lip_sync: bool = False
    enable_voice: bool = True
    enable_captions: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineStep:
    id: str
    kind: StepKind
    provider: ProviderPreference
    depends_on: tuple[str, ...] = ()
    required: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelinePlan:
    request: ShortformRequest
    steps: tuple[PipelineStep, ...]

    def step(self, step_id: str) -> PipelineStep:
        for item in self.steps:
            if item.id == step_id:
                return item
        raise KeyError(step_id)

    def validate(self) -> None:
        known: set[str] = set()
        for step in self.steps:
            missing = [dep for dep in step.depends_on if dep not in known]
            if missing:
                raise ValueError(
                    f"{step.id} depends on steps that have not been declared yet: {missing}"
                )
            if step.id in known:
                raise ValueError(f"duplicate step id: {step.id}")
            known.add(step.id)
