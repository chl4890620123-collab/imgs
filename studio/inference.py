from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoBackend:
    key: str
    name: str
    role: str
    min_vram_gb: int
    strengths: str
    caution: str


BACKENDS = [
    VideoBackend(
        "ltx-2b", "LTX-Video 2B Distilled", "기본/미리보기", 12,
        "빠른 I2V, 키프레임, 영상 연장, 반복 생성에 유리",
        "13B/최신 LTX-2 계열보다 절대 화질은 낮을 수 있음",
    ),
    VideoBackend(
        "hunyuan15", "HunyuanVideo-1.5 Step-Distilled", "품질 컷", 14,
        "480p I2V 8~12 step, 인물/동작 품질과 일관성에 유리",
        "14GB는 오프로딩 기준 최소치라 T4에서는 느릴 수 있음",
    ),
    VideoBackend(
        "wan22", "Wan 2.2 TI2V-5B", "고품질 시네마틱", 24,
        "복잡한 동작, 시네마틱 미학, T2V/I2V 모두 강함",
        "공식 단일 GPU 720p 기준 최소 24GB라 현재 T4 15GB에는 부적합",
    ),
    VideoBackend(
        "framepack", "FramePack F1/P1", "긴 장면/연장", 6,
        "긴 영상에서 컨텍스트 비용을 일정하게 유지, 진행 중 프레임 확인 가능",
        "공식적으로 RTX 30/40/50 계열 중심이며 Tesla T4는 검증 대상이 아님",
    ),
]


def recommended_for_vram(vram_gb: int) -> list[VideoBackend]:
    if vram_gb < 14:
        return [BACKENDS[0]]
    if vram_gb < 24:
        return [BACKENDS[0], BACKENDS[1]]
    return BACKENDS
