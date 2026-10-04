from pathlib import Path
import tempfile

from project import DialogueLine, Scene, StudioProject, VoiceProfile
from render import write_srt
from video_recipe import VideoRecipe, apply_preset, estimate_calls


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


if __name__ == "__main__":
    test_voice_switching()
    test_roundtrip_and_srt()
    test_video_recipe_cache_key_ignores_local_post()
    print("ok")
