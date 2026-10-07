from shortform.clipping import _choose_highlights
from shortform.reframe import vertical_filter


def test_highlight_scoring_prefers_spoken_scene_dense_window():
    highlights = _choose_highlights(
        duration=90,
        scene_changes=[9, 12, 16, 55, 80],
        silences=[(30, 50), (70, 90)],
        num_highlights=2,
        target_duration_sec=20,
    )
    assert len(highlights) == 2
    assert any(x.start <= 12 <= x.end for x in highlights)
    assert all(0 <= x.start < x.end <= 90 for x in highlights)


def test_vertical_filter_is_9_by_16_center_crop():
    value = vertical_filter(1080, 1920)
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in value
    assert "crop=1080:1920" in value


if __name__ == "__main__":
    test_highlight_scoring_prefers_spoken_scene_dense_window()
    test_vertical_filter_is_9_by_16_center_crop()
    print("ok")
