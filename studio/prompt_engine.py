from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from project import StudioProject
from video_recipe import RecipeStore, apply_preset


@dataclass(frozen=True)
class PromptAction:
    kind: str
    target: str
    value: object
    description: str


@dataclass
class PromptPlan:
    instruction: str
    scene_id: int | None
    actions: list[PromptAction] = field(default_factory=list)

    def text(self) -> str:
        if not self.actions:
            return "직접 변경할 설정은 찾지 못했습니다.\n대화/행동 지시는 장면 생성 프롬프트로 그대로 저장됩니다."
        return "\n".join(f"• {x.description}" for x in self.actions)


_RESOLUTIONS = {
    "720p": "720p",
    "1080p": "1080p",
    "1440p": "1440p",
    "4k": "4k",
    "2160p": "4k",
}


def _find_scene_id(text: str, fallback: int | None) -> int | None:
    m = re.search(r"(?:장면|씬|scene)\s*#?\s*(\d{1,3})", text, re.IGNORECASE)
    return int(m.group(1)) if m else fallback


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(word.lower() in low for word in words)


def plan_instruction(
    instruction: str,
    project: StudioProject,
    current_scene_id: int | None = None,
) -> PromptPlan:
    text = instruction.strip()
    scene_id = _find_scene_id(text, current_scene_id)
    plan = PromptPlan(instruction=text, scene_id=scene_id)

    if scene_id is not None:
        # Preserve the full natural-language direction. Even unsupported details are
        # passed unchanged to the future video backend instead of being discarded.
        plan.actions.append(PromptAction(
            "scene_prompt", f"scene:{scene_id}", text,
            f"장면 {scene_id} 생성 지시에 전체 프롬프트 저장",
        ))

        if _contains_any(text, ("시네마틱", "영화처럼", "cinematic")):
            plan.actions.append(PromptAction(
                "preset", f"scene:{scene_id}", "cinematic",
                f"장면 {scene_id} 품질 → 시네마틱",
            ))
        elif _contains_any(text, ("빠르게", "미리보기", "fast")):
            plan.actions.append(PromptAction(
                "preset", f"scene:{scene_id}", "fast",
                f"장면 {scene_id} 품질 → 빠르게",
            ))
        elif _contains_any(text, ("고화질", "high quality", "퀄리티 높게")):
            plan.actions.append(PromptAction(
                "preset", f"scene:{scene_id}", "high",
                f"장면 {scene_id} 품질 → 고화질",
            ))

        m = re.search(r"(?:fps|프레임)\s*[:=]?\s*(12|24|30|48|60)\b", text, re.IGNORECASE)
        if m:
            fps = int(m.group(1))
            plan.actions.append(PromptAction(
                "fps", f"scene:{scene_id}", fps,
                f"장면 {scene_id} 목표 FPS → {fps}",
            ))

        m = re.search(r"(?:동작\s*강도|motion(?:\s*strength)?)\s*[:=]?\s*(\d{1,3})", text, re.IGNORECASE)
        if m:
            value = max(0, min(100, int(m.group(1))))
            plan.actions.append(PromptAction(
                "motion", f"scene:{scene_id}", value,
                f"장면 {scene_id} 동작 강도 → {value}",
            ))
        elif _contains_any(text, ("더 역동적", "역동적으로", "동작 크게", "움직임 크게")):
            plan.actions.append(PromptAction(
                "motion_delta", f"scene:{scene_id}", 15,
                f"장면 {scene_id} 동작 강도 +15",
            ))
        elif _contains_any(text, ("움직임 줄", "동작 줄", "차분하게 움직")):
            plan.actions.append(PromptAction(
                "motion_delta", f"scene:{scene_id}", -15,
                f"장면 {scene_id} 동작 강도 -15",
            ))

        m = re.search(r"(?:캐릭터\s*일관성|얼굴\s*고정|character\s*lock)\s*[:=]?\s*(\d{1,3})", text, re.IGNORECASE)
        if m:
            value = max(0, min(100, int(m.group(1))))
            plan.actions.append(PromptAction(
                "character_lock", f"scene:{scene_id}", value,
                f"장면 {scene_id} 캐릭터 일관성 → {value}",
            ))

        m = re.search(r"(?:선명도|sharpness)\s*[:=]?\s*(\d{1,3})", text, re.IGNORECASE)
        if m:
            value = max(0, min(100, int(m.group(1))))
            plan.actions.append(PromptAction(
                "sharpness", f"scene:{scene_id}", value,
                f"장면 {scene_id} 선명도 → {value}",
            ))
        elif _contains_any(text, ("매우 선명", "더 선명", "선명하게")):
            plan.actions.append(PromptAction(
                "sharpness", f"scene:{scene_id}", 75,
                f"장면 {scene_id} 선명도 → 75",
            ))
        elif _contains_any(text, ("부드럽게", "소프트하게")):
            plan.actions.append(PromptAction(
                "sharpness", f"scene:{scene_id}", 35,
                f"장면 {scene_id} 선명도 → 35",
            ))

        low = text.lower()
        for token, target in _RESOLUTIONS.items():
            if token in low:
                plan.actions.append(PromptAction(
                    "output_resolution", f"scene:{scene_id}", target,
                    f"장면 {scene_id} 출력 화질 → {target.upper()}",
                ))
                break

        camera_match = re.search(
            r"(?:카메라|camera)\s*(?:는|를|:)?\s*([^\n,.]{2,100})",
            text,
            re.IGNORECASE,
        )
        if camera_match:
            camera = camera_match.group(1).strip()
            plan.actions.append(PromptAction(
                "camera", f"scene:{scene_id}", camera,
                f"장면 {scene_id} 카메라 지시 → {camera}",
            ))

    # Voice routing can target the whole character independently of the selected scene.
    for character in sorted(project.characters, key=len, reverse=True):
        if character not in text:
            continue
        if _contains_any(text, ("친구 녹음", "실제 성우", "외부 녹음")):
            plan.actions.append(PromptAction(
                "voice_mode", f"character:{character}", "external",
                f"{character} → 친구/외부 녹음 우선",
            ))
        elif _contains_any(text, ("목소리 끄", "음성 끄", "음소거")):
            plan.actions.append(PromptAction(
                "voice_mode", f"character:{character}", "muted",
                f"{character} → 음소거",
            ))
        elif _contains_any(text, ("ai 성우", "AI 성우", "ai 목소리", "AI 목소리")):
            plan.actions.append(PromptAction(
                "voice_mode", f"character:{character}", "ai",
                f"{character} → AI 성우",
            ))

    return plan


def apply_plan(
    plan: PromptPlan,
    project: StudioProject,
    project_path: str | Path,
    recipe_store: RecipeStore,
) -> list[str]:
    changed: list[str] = []

    for action in plan.actions:
        if action.target.startswith("scene:"):
            scene_id = int(action.target.split(":", 1)[1])
            recipe = recipe_store.get(scene_id)
            if action.kind == "scene_prompt":
                recipe.inference.creative_prompt = str(action.value)
            elif action.kind == "preset":
                apply_preset(recipe, str(action.value))
            elif action.kind == "fps":
                recipe.inference.fps = int(action.value)
                recipe.post.interpolation_fps = int(action.value)
            elif action.kind == "motion":
                recipe.inference.motion_strength = int(action.value)
            elif action.kind == "motion_delta":
                recipe.inference.motion_strength = max(
                    0, min(100, recipe.inference.motion_strength + int(action.value))
                )
            elif action.kind == "character_lock":
                recipe.inference.character_lock = int(action.value)
            elif action.kind == "sharpness":
                recipe.post.sharpness = int(action.value)
            elif action.kind == "output_resolution":
                recipe.post.upscale = True
                recipe.post.upscale_target = str(action.value)
            elif action.kind == "camera":
                recipe.inference.camera_prompt = str(action.value)
            changed.append(action.description)

        elif action.target.startswith("character:") and action.kind == "voice_mode":
            character = action.target.split(":", 1)[1]
            project.profile(character).mode = str(action.value)
            changed.append(action.description)

    recipe_store.save()
    project.save(project_path)
    return changed
