from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import PipelineStep, ProviderPreference


@dataclass(frozen=True)
class ProviderCapability:
    step: str
    available: bool
    reason: str = ""


class ShortformProvider(Protocol):
    name: str
    preference: ProviderPreference

    def supports(self, step: PipelineStep) -> ProviderCapability:
        ...

    def run(self, step: PipelineStep) -> dict:
        ...


def resolve_provider(
    requested: ProviderPreference,
    *,
    local_available: bool,
    cloud_available: bool,
) -> ProviderPreference:
    if requested == ProviderPreference.LOCAL:
        if not local_available:
            raise RuntimeError("requested local provider is not available")
        return ProviderPreference.LOCAL

    if requested == ProviderPreference.CLOUD:
        if not cloud_available:
            raise RuntimeError("requested cloud provider is not available")
        return ProviderPreference.CLOUD

    if local_available:
        return ProviderPreference.LOCAL
    if cloud_available:
        return ProviderPreference.CLOUD
    raise RuntimeError("no provider is available")
