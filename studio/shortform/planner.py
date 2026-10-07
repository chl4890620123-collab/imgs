from __future__ import annotations

from .models import (
    PipelineMode,
    PipelinePlan,
    PipelineStep,
    ProviderPreference,
    ShortformRequest,
    StepKind,
)


def _provider(request: ShortformRequest) -> ProviderPreference:
    # AUTO is intentionally preserved here. Runtime provider resolution can choose
    # local first without the planner pretending a backend is installed.
    return request.provider


def build_shortform_plan(request: ShortformRequest) -> PipelinePlan:
    if request.target_duration_sec <= 0:
        raise ValueError("target_duration_sec must be greater than zero")
    if request.aspect_ratio != "9:16":
        raise ValueError("shortform foundation currently supports 9:16 output only")

    provider = _provider(request)
    steps: list[PipelineStep] = [
        PipelineStep(
            id="plan",
            kind=StepKind.PLAN,
            provider=ProviderPreference.LOCAL,
            params={
                "title": request.title,
                "prompt": request.prompt,
                "duration_sec": request.target_duration_sec,
                "language": request.language,
            },
        )
    ]

    if request.mode == PipelineMode.CLIP:
        steps.extend(
            [
                PipelineStep(
                    id="clip_detect",
                    kind=StepKind.CLIP_DETECT,
                    provider=provider,
                    depends_on=("plan",),
                ),
                PipelineStep(
                    id="reframe",
                    kind=StepKind.REFRAME,
                    provider=ProviderPreference.LOCAL,
                    depends_on=("clip_detect",),
                    params={"aspect_ratio": "9:16"},
                ),
            ]
        )
        visual_tail = "reframe"
    else:
        image_inputs = [m for m in request.media if m.kind == "image"]
        if not image_inputs:
            steps.append(
                PipelineStep(
                    id="image_generate",
                    kind=StepKind.IMAGE_GENERATE,
                    provider=provider,
                    depends_on=("plan",),
                    required=False,
                )
            )
            visual_dep = "image_generate"
        else:
            visual_dep = "plan"

        steps.append(
            PipelineStep(
                id="video_generate",
                kind=StepKind.VIDEO_GENERATE,
                provider=provider,
                depends_on=(visual_dep,),
                params={
                    "reuse_existing_shot_cache": True,
                    "target_duration_sec": request.target_duration_sec,
                },
            )
        )
        steps.append(
            PipelineStep(
                id="motion",
                kind=StepKind.MOTION,
                provider=provider,
                depends_on=("video_generate",),
                required=False,
            )
        )
        visual_tail = "motion"

    audio_tail: str | None = None
    if request.enable_voice:
        steps.append(
            PipelineStep(
                id="audio",
                kind=StepKind.AUDIO,
                provider=provider,
                depends_on=("plan",),
            )
        )
        audio_tail = "audio"

    if request.enable_lip_sync:
        deps = [visual_tail]
        if audio_tail:
            deps.append(audio_tail)
        steps.append(
            PipelineStep(
                id="lip_sync",
                kind=StepKind.LIP_SYNC,
                provider=provider,
                depends_on=tuple(deps),
            )
        )
        visual_tail = "lip_sync"

    if request.enable_captions:
        deps = (audio_tail,) if audio_tail else ("plan",)
        steps.append(
            PipelineStep(
                id="captions",
                kind=StepKind.CAPTIONS,
                provider=ProviderPreference.LOCAL,
                depends_on=deps,
            )
        )

    review_deps = [visual_tail]
    if request.enable_captions:
        review_deps.append("captions")
    steps.append(
        PipelineStep(
            id="quality_review",
            kind=StepKind.QUALITY_REVIEW,
            provider=ProviderPreference.LOCAL,
            depends_on=tuple(review_deps),
        )
    )
    steps.append(
        PipelineStep(
            id="render",
            kind=StepKind.RENDER,
            provider=ProviderPreference.LOCAL,
            depends_on=("quality_review",),
            params={"aspect_ratio": "9:16"},
        )
    )

    plan = PipelinePlan(request=request, steps=tuple(steps))
    plan.validate()
    return plan
