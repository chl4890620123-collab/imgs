from __future__ import annotations

from project import StudioProject
from character_bible import dialogue_context
from video_recipe import VideoRecipe


def build_scene_generation_prompt(
    project: StudioProject,
    scene_id: int,
    recipe: VideoRecipe,
) -> str:
    scene = next((x for x in project.scenes if x.id == scene_id), None)
    if scene is None:
        raise ValueError(f"장면 {scene_id}을 찾을 수 없습니다.")

    lines = [x for x in project.dialogue if x.scene_id == scene_id]
    characters = [x.character for x in lines]

    sections: list[str] = []
    if scene.description:
        sections.append(f"Scene foundation: {scene.description.strip()}.")

    bible = dialogue_context(characters)
    if bible:
        sections.append("Character continuity rules:\n" + bible)

    if recipe.inference.creative_prompt.strip():
        sections.append(
            "Director instruction, preserve its intent exactly:\n"
            + recipe.inference.creative_prompt.strip()
        )

    if scene.shot_prompts:
        chronological = "\n".join(
            f"{idx + 1}. {beat}" for idx, beat in enumerate(scene.shot_prompts)
        )
        sections.append(
            "Chronological visual/action beats. Maintain continuity between beats:\n"
            + chronological
        )

    if lines:
        dialogue = "\n".join(
            f"- {line.character}: {line.text}" for line in lines
        )
        sections.append(
            "Dialogue performance reference. Do not render these words as on-screen text. "
            "Use them to drive gaze, reaction timing, mouth movement, pauses and physical acting:\n"
            + dialogue
        )

    sections.append(
        f"Camera direction: {recipe.inference.camera_prompt}. "
        f"Motion strength {recipe.inference.motion_strength}/100. "
        f"Character continuity {recipe.inference.character_lock}/100."
    )
    sections.append(
        "Cinematic continuity rules: preserve face identity, hairstyle, costume, handedness, "
        "screen direction, weather, lighting direction, props and relative character positions. "
        "Actions must progress causally from the previous frame. Natural facial micro-expressions, "
        "weight shifts and eye lines. No subtitles, captions, logos or visible text."
    )

    return "\n\n".join(sections)
