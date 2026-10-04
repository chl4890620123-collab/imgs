from pathlib import Path
import tempfile

from project import DialogueLine, Scene, StudioProject, VoiceProfile
from render import write_srt
from video_recipe import VideoRecipe, RecipeStore, apply_preset, estimate_calls
from prompt_engine import plan_instruction, apply_plan
from inference import available_backends, recommended_for_vram
from dialogue_audit import audit_dialogue


def test_voice_switching():
    p = StudioProject(title="x", characters={"A": VoiceProfile(mode="ai")})
    line = DialogueLine("L1", 1, "A", "hello", 1, 2, ai_audio="a.wav", external_audio="b.wav")
    p.dialogue.append(line)
    assert p.line_audio(line) == "a.wav"
    p.characters["A"].mode = "external"
    assert p.line_audio(line) == "b.wav"
    p.characters["A"].mode = "muted"
    assert p.line_audio(line) is None


def test_roundtrip_and_srt():
    p = StudioProject(
        title="x",
        scenes=[Scene(1, "s", 0, 3)],
        dialogue=[DialogueLine("L1", 1, "A", "안녕", 0.5, 2.0)],
    )
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "p.json"
        p.save(f)
        q = StudioProject.load(f)
        assert q.dialogue[0].text == "안녕"
        s = Path(td) / "x.srt"
        write_srt(q, s)
        assert "00:00:00,500" in s.read_text(encoding="utf-8")


def test_video_recipe_cache_key_ignores_local_post():
    recipe = apply_preset(VideoRecipe(scene_id=1), "high")
    first = recipe.inference_fingerprint()
    recipe.post.contrast = 90
    recipe.post.camera_zoom = 25
    assert recipe.inference_fingerprint() == first
    recipe.inference.seed += 1
    assert recipe.inference_fingerprint() != first
    assert estimate_calls(15, "high") == 30


def test_director_prompt_plan_and_apply():
    p = StudioProject(
        title="x",
        characters={"서진우": VoiceProfile(mode="ai")},
        scenes=[Scene(9, "이세계", 0, 10)],
    )
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project_file = root / "project.json"
        p.save(project_file)
        store = RecipeStore(root / "recipes.json")
        plan = plan_instruction(
            "장면 9에서 더 역동적으로, 캐릭터 일관성 90, 선명도 75, 1080p. "
            "카메라는 낮은 각도로 따라가. 서진우는 친구 녹음으로.",
            p,
            current_scene_id=9,
        )
        assert plan.scene_id == 9
        kinds = {x.kind for x in plan.actions}
        assert {"scene_prompt", "motion_delta", "character_lock", "sharpness", "output_resolution", "camera", "voice_mode"} <= kinds
        changed = apply_plan(plan, p, project_file, store)
        assert changed
        recipe = store.get(9)
        assert recipe.inference.creative_prompt.startswith("장면 9")
        assert recipe.inference.character_lock == 90
        assert recipe.post.sharpness == 75
        assert recipe.post.upscale_target == "1080p"
        assert p.characters["서진우"].mode == "external"


def test_korean_free_stack_excludes_hunyuan():
    keys = {x.key for x in available_backends("KR")}
    assert "hunyuan15" not in keys
    assert {"ltx-2b", "wan22", "framepack"} <= keys
    low_vram = {x.key for x in recommended_for_vram(15, "KR")}
    assert "ltx-2b" in low_vram
    assert "wan22" not in low_vram


def test_dialogue_audit():
    p = StudioProject(
        title="x",
        scenes=[Scene(1, "a", 0, 70), Scene(2, "b", 70, 60)],
        dialogue=[DialogueLine("L1", 1, "A", "안녕", 1, 2)],
    )
    result = audit_dialogue(p)
    assert result.total_lines == 1
    assert result.silent_scenes == (2,)
    assert set(result.sparse_scenes) == {1, 2}


if __name__ == "__main__":
    test_voice_switching()
    test_roundtrip_and_srt()
    test_video_recipe_cache_key_ignores_local_post()
    test_director_prompt_plan_and_apply()
    test_korean_free_stack_excludes_hunyuan()
    test_dialogue_audit()
    print("ok")
