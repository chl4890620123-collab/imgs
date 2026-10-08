from pathlib import Path
import tempfile

from shortform.captions import write_ass_for_clip
from shortform.clipping import Highlight
from shortform.quality import get_quality_preset
from shortform.semantic import choose_transcript_highlights
from shortform.transcription import Transcript, TranscriptSegment, TranscriptWord


def _transcript() -> Transcript:
    return Transcript(
        language="ko",
        segments=(
            TranscriptSegment(0.0, 7.0, "오늘은 평범한 이야기입니다."),
            TranscriptSegment(
                7.0,
                15.0,
                "근데 여기서 진짜 중요한 반전이 있습니다!",
                (
                    TranscriptWord(7.0, 7.5, "근데"),
                    TranscriptWord(7.5, 8.5, "여기서"),
                    TranscriptWord(8.5, 9.5, "진짜"),
                    TranscriptWord(9.5, 11.0, "중요한"),
                    TranscriptWord(11.0, 13.0, "반전이"),
                    TranscriptWord(13.0, 15.0, "있습니다!"),
                ),
            ),
            TranscriptSegment(15.0, 24.0, "왜 그런지 지금부터 이유를 보여드릴게요?"),
            TranscriptSegment(24.0, 33.0, "마지막에 결론을 확인해 보세요."),
        ),
    )


def test_quality_presets_are_vertical_and_quality_first():
    high = get_quality_preset("high")
    cinematic = get_quality_preset("cinematic")
    assert (high.width, high.height) == (1080, 1920)
    assert high.crf < 19
    assert cinematic.crf <= high.crf
    assert cinematic.encoder_preset in {"slow", "slower", "veryslow"}


def test_semantic_highlights_prefer_hooked_transcript():
    selected = choose_transcript_highlights(
        _transcript(),
        num_highlights=1,
        target_duration_sec=18,
    )
    assert len(selected) == 1
    clip = selected[0]
    assert clip.start <= 15 <= clip.end
    assert clip.score > 0.45


def test_ass_writer_uses_word_timing():
    transcript = _transcript()
    clip = Highlight(7.0, 24.0, 0.9, 1.0, 1.0)
    with tempfile.TemporaryDirectory() as td:
        path = write_ass_for_clip(transcript, clip, Path(td) / "caption.ass")
        text = path.read_text(encoding="utf-8")
        assert "[V4+ Styles]" in text
        assert "Dialogue:" in text
        assert r"{\k" in text
        assert "반전이" in text


if __name__ == "__main__":
    test_quality_presets_are_vertical_and_quality_first()
    test_semantic_highlights_prefer_hooked_transcript()
    test_ass_writer_uses_word_timing()
    print("ok")
