from shortform import (
    MediaInput,
    PipelineMode,
    ProviderPreference,
    ShortformRequest,
    StepKind,
    build_shortform_plan,
)
from shortform.feature_catalog import FEATURES, FeatureStatus
from shortform.providers import resolve_provider


def test_generate_shortform_plan_is_local_post_first():
    plan = build_shortform_plan(
        ShortformRequest(
            title="demo",
            prompt="어두운 미스터리 숏폼",
            provider=ProviderPreference.AUTO,
            enable_lip_sync=True,
        )
    )
    kinds = [step.kind for step in plan.steps]
    assert StepKind.VIDEO_GENERATE in kinds
    assert StepKind.LIP_SYNC in kinds
    assert kinds[-2:] == [StepKind.QUALITY_REVIEW, StepKind.RENDER]
    assert plan.step("render").provider == ProviderPreference.LOCAL


def test_clip_plan_skips_video_generation():
    plan = build_shortform_plan(
        ShortformRequest(
            title="clip",
            mode=PipelineMode.CLIP,
            media=(MediaInput(kind="video", value="source.mp4"),),
        )
    )
    kinds = {step.kind for step in plan.steps}
    assert StepKind.CLIP_DETECT in kinds
    assert StepKind.REFRAME in kinds
    assert StepKind.VIDEO_GENERATE not in kinds


def test_auto_provider_prefers_local_when_available():
    assert resolve_provider(
        ProviderPreference.AUTO,
        local_available=True,
        cloud_available=True,
    ) == ProviderPreference.LOCAL


def test_feature_catalog_does_not_overclaim_missing_features():
    assert FEATURES["video"].status == FeatureStatus.READY
    assert FEATURES["clipping"].status == FeatureStatus.PLANNED
    assert FEATURES["lip_sync"].status == FeatureStatus.PLANNED
