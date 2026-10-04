from pathlib import Path
import tempfile

from project import DialogueLine, Scene, Shot, StudioProject, VoiceProfile
from render import write_srt
from video_recipe import VideoRecipe, RecipeStore, apply_preset, estimate_calls
from prompt_engine import plan_instruction, apply_plan
from inference import available_backends, recommended_for_vram
from dialogue_audit import audit_dialogue
from scene_prompt import build_scene_generation_prompt
from performance import build_scene_performance_events, build_shot_prompt, choose_generation_shots
from quality_review import mark_shot_quality, regeneration_plan
from ltx_runner import frames_for_duration


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
    assert {"ltx-2b", "wan22"} <= keys
    assert "framepack" not in keys
    low_vram = {x.key for x in recommended_for_vram(15, "KR")}
    assert "ltx-2b" in low_vram
    assert "wan22" not in low_vram
    cinematic = apply_preset(VideoRecipe(scene_id=1), "cinematic")
    assert cinematic.inference.backend == "ltx-2b"


def test_scene_prompt_uses_character_dialogue_and_action():
    p = StudioProject(
        title="x",
        characters={"서진우": VoiceProfile(), "리아": VoiceProfile()},
        scenes=[
            Scene(
                9, "이세계", 0, 10,
                description="rainy battlefield",
                shot_prompts=["Ria runs toward Jin-woo", "Ria tackles Jin-woo before an arrow lands"],
            )
        ],
        dialogue=[
            DialogueLine("L1", 9, "리아", "엎드려!", 1, 2),
            DialogueLine("L2", 9, "서진우", "여긴…….", 2, 3),
        ],
    )
    recipe = apply_preset(VideoRecipe(scene_id=9), "high")
    recipe.inference.creative_prompt = "리아가 실제로 진우를 밀치며 둘의 위치가 바뀐다."
    prompt = build_scene_generation_prompt(p, 9, recipe)
    assert "frontline commander" in prompt
    assert "professional Go player" in prompt
    assert "엎드려!" in prompt
    assert "Ria tackles Jin-woo" in prompt
    assert "No subtitles" in prompt




def test_performance_timeline_and_shot_prompt():
    p = StudioProject(
        title="x",
        characters={"리아": VoiceProfile(), "서진우": VoiceProfile()},
        scenes=[Scene(9, "이세계", 0, 12, description="rainy battlefield")],
        shots=[
            Shot("S09_SH01", 9, 0, 6, "Ria sees an incoming arrow and runs toward Jin-woo"),
            Shot("S09_SH02", 9, 6, 6, "Ria collides with Jin-woo and both hit the mud"),
        ],
        dialogue=[
            DialogueLine("L1", 9, "리아", "엎드려!", 2.0, 3.0),
            DialogueLine("L2", 9, "서진우", "여긴…….", 3.4, 4.2),
        ],
    )
    recipe = apply_preset(VideoRecipe(scene_id=9), "high")
    events = build_scene_performance_events(p, 9)
    assert any(x.kind == "pre_reaction" for x in events)
    assert any(x.kind == "listener_reaction" for x in events)
    prompt = build_shot_prompt(p, p.shot("S09_SH01"), recipe)
    assert "엎드려!" in prompt
    assert "frontline commander" in prompt
    assert len(prompt.split()) <= 190
    chosen = choose_generation_shots(p, 9, recipe)
    assert 1 <= len(chosen) <= recipe.call_budget


def test_selective_regeneration():
    p = StudioProject(
        title="x",
        scenes=[Scene(1, "s", 0, 12)],
        shots=[
            Shot("S01_SH01", 1, 0, 6, "a", visual="a.mp4", generation_status="ready"),
            Shot("S01_SH02", 1, 6, 6, "b", visual="b.mp4", generation_status="ready"),
        ],
    )
    recipe = apply_preset(VideoRecipe(scene_id=1), "high")
    mark_shot_quality(p, "S01_SH01", 91, [])
    mark_shot_quality(p, "S01_SH02", 58, ["face_drift", "motion_jitter"])
    plan = regeneration_plan(p, 1, recipe)
    assert [x.shot_id for x in plan] == ["S01_SH02"]


def test_ltx_frame_count():
    assert frames_for_duration(6.0, 24) == 145
    assert frames_for_duration(20.0, 60) <= 257


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
    test_scene_prompt_uses_character_dialogue_and_action()
    test_performance_timeline_and_shot_prompt()
    test_selective_regeneration()
    test_ltx_frame_count()
    print("ok")
