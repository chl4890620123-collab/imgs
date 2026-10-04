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
    license_name: str
    usable_in_south_korea: bool = True


BACKENDS = [
    VideoBackend(
        "ltx-2b", "LTX-Video 2B Distilled", "기본/미리보기", 12,
        "빠른 I2V, 키프레임, 영상 연장, 반복 생성에 유리",
        "13B/최신 LTX-2 계열보다 절대 화질은 낮을 수 있음",
        "LTXV Open Weights License 0.X (code: Apache-2.0)",
    ),
    VideoBackend(
        "hunyuan15", "HunyuanVideo-1.5 Step-Distilled", "품질 컷", 14,
        "480p I2V 8~12 step, 인물/동작 품질과 일관성에 유리",
        "라이선스가 대한민국을 적용 지역에서 제외하므로 한국 사용 프로젝트에는 사용하지 않음",
        "Tencent Hunyuan Community License",
        False,
    ),
    VideoBackend(
        "wan22", "Wan 2.2 TI2V-5B", "고품질 시네마틱", 24,
        "복잡한 동작, 시네마틱 미학, T2V/I2V 모두 강함",
        "공식 단일 GPU 720p 기준 최소 24GB라 현재 T4 15GB에는 부적합",
        "Apache-2.0",
    ),
    VideoBackend(
        "framepack", "FramePack F1/P1", "긴 장면/연장", 6,
        "긴 영상에서 컨텍스트 비용을 일정하게 유지, 진행 중 프레임 확인 가능",
        "코드는 Apache-2.0이나 공식 구현이 HunyuanVideo 가중치에 의존하며 해당 가중치 라이선스는 대한민국을 제외",
        "Apache-2.0 code + Tencent Hunyuan model license",
        False,
    ),
]


def available_backends(region: str = "KR") -> list[VideoBackend]:
    region = region.strip().upper()
    if region in {"KR", "KOR", "SOUTH KOREA", "REPUBLIC OF KOREA"}:
        return [x for x in BACKENDS if x.usable_in_south_korea]
    return list(BACKENDS)


def recommended_for_vram(vram_gb: int, region: str = "KR") -> list[VideoBackend]:
    allowed = available_backends(region)
    return [x for x in allowed if x.min_vram_gb <= vram_gb]
