from __future__ import annotations

from dataclasses import dataclass
from math import inf

from character_bible import get_character_bible
from project import DialogueLine, Shot, StudioProject
from video_recipe import VideoRecipe


@dataclass(frozen=True)
class PerformanceEvent:
    time: float
    end: float
    kind: str
    character: str | None
    instruction: str
    dialogue_id: str | None = None


@dataclass(frozen=True)
class ShotPerformancePlan:
    shot_id: str
    start: float
    end: float
    events: tuple[PerformanceEvent, ...]
    prompt: str


def _speech_action(line: DialogueLine) -> str:
    text = line.text.strip()
    if not text:
        return "speaks naturally"
    if text.endswith("!") or "!" in text:
        return "speech begins while the body is already moving; strong breath, direct eye-line, decisive gesture"
    if text.endswith("?"):
        return "brief eye contact before the question; restrained head movement; listen for the answer"
    if "……" in text or "..." in text:
        return "hesitation is visible in the eyes and breath before the words finish"
    return "small eye and head movement leads the line; natural mouth motion and restrained gesture"


def build_scene_performance_events(project: StudioProject, scene_id: int) -> list[PerformanceEvent]:
    scene = next((x for x in project.scenes if x.id == scene_id), None)
    if scene is None:
        raise ValueError(f"장면 {scene_id}을 찾을 수 없습니다.")

    lines = sorted(
        [x for x in project.dialogue if x.scene_id == scene_id],
        key=lambda x: x.start,
    )
    events: list[PerformanceEvent] = []

    for line in lines:
        bible = get_character_bible(line.character)
        pre = max(scene.start, line.start - 0.42)
        post = min(scene.start + scene.duration, line.end + 0.32)

        if bible:
            events.append(PerformanceEvent(
                pre,
                line.start,
                "pre_reaction",
                line.character,
                f"{line.character}: prepare the line with {bible.action_style}; emotion follows: {bible.emotional_rule}",
                line.id,
            ))

        events.append(PerformanceEvent(
            line.start,
            line.end,
            "speech",
            line.character,
            f'{line.character} says "{line.text}". {_speech_action(line)}',
            line.id,
        ))

        events.append(PerformanceEvent(
            line.end,
            post,
            "reaction",
            line.character,
            f"{line.character}: let the facial expression and body settle naturally after the line; do not freeze immediately",
            line.id,
        ))

    # Give the listener a visible reaction to the previous speaker.
    for prev, nxt in zip(lines, lines[1:]):
        if prev.character != nxt.character:
            t0 = min(prev.end + 0.06, nxt.start - 0.05)
            t1 = min(nxt.start, t0 + 0.35)
            if t1 > t0:
                events.append(PerformanceEvent(
                    t0,
                    t1,
                    "listener_reaction",
                    nxt.character,
                    f"{nxt.character}: react silently to {prev.character} before speaking; eyes move first, then a small head/body response",
                    nxt.id,
                ))

    return sorted(events, key=lambda x: (x.time, x.end, x.kind))


def _overlaps(start: float, end: float, event: PerformanceEvent) -> bool:
    return event.end > start and event.time < end


def build_shot_prompt(
    project: StudioProject,
    shot: Shot,
    recipe: VideoRecipe,
    max_words: int = 190,
) -> str:
    scene = next((x for x in project.scenes if x.id == shot.scene_id), None)
    if scene is None:
        raise ValueError(f"장면 {shot.scene_id}을 찾을 수 없습니다.")

    end = shot.start + shot.duration
    events = [x for x in build_scene_performance_events(project, shot.scene_id) if _overlaps(shot.start, end, x)]

    names: list[str] = []
    for event in events:
        if event.character and event.character not in names:
            names.append(event.character)

    compact_characters: list[str] = []
    for name in names:
        bible = get_character_bible(name)
        if bible:
            compact_characters.append(
                f"{name}: {bible.visual_anchor}; movement {bible.action_style}; {bible.emotional_rule}"
            )

    event_text = " ".join(x.instruction for x in events)
    parts = [
        shot.prompt.strip(),
        " ".join(compact_characters),
        event_text,
        recipe.inference.creative_prompt.strip(),
        (
            f"Camera: {recipe.inference.camera_prompt}. "
            f"Motion {recipe.inference.motion_strength}/100, identity consistency {recipe.inference.character_lock}/100. "
            "Continuous causal action, natural weight shift, eye-lines, facial micro-expressions, cloth and hair reacting to motion. "
            "No frozen pose, no slideshow, no duplicated body parts, no subtitles or visible text."
        ),
    ]
    prompt = " ".join(x for x in parts if x).strip()
    words = prompt.split()
    if len(words) > max_words:
        prompt = " ".join(words[:max_words])
    return prompt


def build_scene_performance_plan(
    project: StudioProject,
    scene_id: int,
    recipe: VideoRecipe,
) -> list[ShotPerformancePlan]:
    events = build_scene_performance_events(project, scene_id)
    plans: list[ShotPerformancePlan] = []
    for shot in project.scene_shots(scene_id):
        end = shot.start + shot.duration
        shot_events = tuple(x for x in events if _overlaps(shot.start, end, x))
        plans.append(ShotPerformancePlan(
            shot_id=shot.id,
            start=shot.start,
            end=end,
            events=shot_events,
            prompt=build_shot_prompt(project, shot, recipe),
        ))
    return plans


def choose_generation_shots(
    project: StudioProject,
    scene_id: int,
    recipe: VideoRecipe,
) -> list[ShotPerformancePlan]:
    plans = build_scene_performance_plan(project, scene_id, recipe)

    def score(plan: ShotPerformancePlan) -> tuple[int, int, float]:
        speech = sum(1 for x in plan.events if x.kind == "speech")
        action_words = sum(
            1
            for word in ("run", "sprint", "shout", "arrow", "attack", "retreat", "cavalry", "push", "falls", "turns")
            if word in plan.prompt.lower()
        )
        return (speech * 10 + action_words * 3 + len(plan.events), len(plan.prompt), -plan.start)

    ranked = sorted(plans, key=score, reverse=True)
    return ranked[: max(1, recipe.call_budget)]


def performance_plan_text(project: StudioProject, scene_id: int, recipe: VideoRecipe) -> str:
    chosen = {x.shot_id for x in choose_generation_shots(project, scene_id, recipe)}
    rows = []
    for plan in build_scene_performance_plan(project, scene_id, recipe):
        marker = "AI 생성 우선" if plan.shot_id in chosen else "캐시/보간/기존 소스 우선"
        rows.append(
            f"{plan.shot_id} {plan.start:.1f}-{plan.end:.1f}s | {marker} | 연기 이벤트 {len(plan.events)}개"
        )
        for event in plan.events:
            rows.append(
                f"  - {event.time:.2f}s {event.kind}"
                + (f" / {event.character}" if event.character else "")
                + f": {event.instruction}"
            )
    return "\n".join(rows)
