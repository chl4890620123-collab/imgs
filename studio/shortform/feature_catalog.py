from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FeatureStatus(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    PLANNED = "planned"


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    label: str
    status: FeatureStatus
    existing_modules: tuple[str, ...] = ()
    notes: str = ""


FEATURES: dict[str, FeatureDefinition] = {
    "image": FeatureDefinition(
        "image",
        "Image",
        FeatureStatus.PARTIAL,
        ("project.py", "scene_prompt.py"),
        "참조 이미지 흐름은 있으나 범용 이미지 생성 provider는 아직 분리 전",
    ),
    "video": FeatureDefinition(
        "video",
        "Video",
        FeatureStatus.READY,
        ("ltx_runner.py", "remote_jobs.py", "video_cache.py"),
        "LTX/Colab Shot 생성과 재사용 경로가 존재",
    ),
    "audio": FeatureDefinition(
        "audio",
        "Audio / TTS",
        FeatureStatus.READY,
        ("audio.py", "gemini_tts.py"),
        "AI 음성과 외부 녹음 교체 지원",
    ),
    "clipping": FeatureDefinition(
        "clipping",
        "AI Clipping",
        FeatureStatus.PLANNED,
        (),
        "긴 영상에서 하이라이트 후보를 찾는 단계 추가 예정",
    ),
    "motion": FeatureDefinition(
        "motion",
        "Motion",
        FeatureStatus.PARTIAL,
        ("prompt_engine.py", "performance.py", "video_recipe.py"),
        "행동/카메라/연기 지시는 존재하며 전용 motion provider는 추후 분리",
    ),
    "lip_sync": FeatureDefinition(
        "lip_sync",
        "Lip Sync",
        FeatureStatus.PLANNED,
        (),
        "음성-입모양 동기화 provider 연결 예정",
    ),
    "cinema": FeatureDefinition(
        "cinema",
        "Cinema Controls",
        FeatureStatus.PARTIAL,
        ("video_recipe.py", "scene_prompt.py"),
        "camera_prompt는 존재하며 렌즈/초점/DOF 메타를 확장할 예정",
    ),
    "workflow": FeatureDefinition(
        "workflow",
        "Workflow",
        FeatureStatus.READY,
        ("generation_plan.py", "remote_jobs.py"),
        "이번 PipelinePlan이 상위 오케스트레이션 계약 역할",
    ),
    "agent": FeatureDefinition(
        "agent",
        "Agent / Director Prompt",
        FeatureStatus.PARTIAL,
        ("prompt_engine.py", "mcp_server.py"),
        "자연어 변경 계획은 구현되어 있고 숏폼 전체 planner와 연결 예정",
    ),
    "mcp": FeatureDefinition(
        "mcp",
        "MCP",
        FeatureStatus.READY,
        ("mcp_server.py",),
        "프로젝트/Shot/Colab 제어 도구가 이미 존재",
    ),
}
