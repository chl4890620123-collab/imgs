from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityPreset:
    key: str
    label: str
    width: int
    height: int
    fps: int
    crf: int
    encoder_preset: str
    audio_bitrate: str
    loudnorm: bool
    unsharp_amount: float


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "preview": QualityPreset(
        key="preview",
        label="미리보기",
        width=720,
        height=1280,
        fps=30,
        crf=21,
        encoder_preset="medium",
        audio_bitrate="160k",
        loudnorm=False,
        unsharp_amount=0.15,
    ),
    "high": QualityPreset(
        key="high",
        label="고화질",
        width=1080,
        height=1920,
        fps=30,
        crf=16,
        encoder_preset="slow",
        audio_bitrate="192k",
        loudnorm=True,
        unsharp_amount=0.22,
    ),
    "cinematic": QualityPreset(
        key="cinematic",
        label="최고화질",
        width=1080,
        height=1920,
        fps=30,
        crf=14,
        encoder_preset="slower",
        audio_bitrate="256k",
        loudnorm=True,
        unsharp_amount=0.18,
    ),
}


def get_quality_preset(key: str) -> QualityPreset:
    try:
        return QUALITY_PRESETS[key]
    except KeyError as exc:
        raise ValueError(f"알 수 없는 숏폼 품질 프리셋: {key}") from exc
