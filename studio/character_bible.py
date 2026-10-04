from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterBible:
    name: str
    role: str
    visual_anchor: str
    speech_style: str
    action_style: str
    emotional_rule: str
    avoid: str

    def prompt_fragment(self) -> str:
        return (
            f"{self.name} ({self.role}). "
            f"Appearance anchor: {self.visual_anchor}. "
            f"Speech: {self.speech_style}. "
            f"Movement: {self.action_style}. "
            f"Emotion rule: {self.emotional_rule}. "
            f"Avoid: {self.avoid}."
        )


BIBLE: dict[str, CharacterBible] = {
    "서진우": CharacterBible(
        name="서진우",
        role="28-year-old Korean professional Go player displaced into a medieval war",
        visual_anchor="black hair, black suit, calm narrow focus, mud and rain accumulate after the transition",
        speech_style="short analytical sentences; rarely explains everything; uses precise spatial language and only occasional Go metaphors",
        action_style="small deliberate movements, scans terrain before moving, eyes lead before body follows",
        emotional_rule="fear and guilt appear as micro-expressions and pauses rather than shouting",
        avoid="heroic speeches, comedy, exaggerated anime reactions, constant Go jargon",
    ),
    "리아": CharacterBible(
        name="리아",
        role="25-year-old red-haired frontline commander",
        visual_anchor="wet red hair, battle-worn steel armor, practical red cloth, alert posture",
        speech_style="command-first, concise, physical and direct; distrust softens gradually into tactical respect",
        action_style="moves first and talks while acting; protects others without making a show of it",
        emotional_rule="anger is controlled by duty; concern appears through decisions more than confession",
        avoid="flirtatious banter, helpless reactions, long exposition",
    ),
    "테오": CharacterBible(
        name="테오",
        role="17-year-old brown-haired messenger",
        visual_anchor="young brown-haired runner, lighter armor, breathless from constant movement",
        speech_style="fast and concrete when reporting; becomes personal and less formal when family is involved",
        action_style="runs, points, looks between commanders, visibly reacts before recovering discipline",
        emotional_rule="fear is allowed, but he still completes the message or task",
        avoid="childish comedy, excessive stammering, military authority beyond his role",
    ),
    "카르만": CharacterBible(
        name="카르만",
        role="52-year-old veteran commander",
        visual_anchor="gray hair and beard, facial scar, dark heavy armor, economical movements",
        speech_style="few words with weight; skeptical questions; decisions framed in cost, time, and survivability",
        action_style="stands grounded, watches before issuing one decisive order",
        emotional_rule="care for soldiers is hidden under ruthless command discipline",
        avoid="rambling speeches, reckless rage, comic gruffness",
    ),
}


def get_character_bible(name: str) -> CharacterBible | None:
    # Inner-monologue aliases should inherit the same person.
    if name == "서진우_속말":
        name = "서진우"
    return BIBLE.get(name)


def dialogue_context(characters: list[str]) -> str:
    seen: list[str] = []
    chunks: list[str] = []
    for name in characters:
        base = "서진우" if name == "서진우_속말" else name
        if base in seen:
            continue
        seen.append(base)
        bible = get_character_bible(base)
        if bible:
            chunks.append(bible.prompt_fragment())
    return "\n".join(chunks)
