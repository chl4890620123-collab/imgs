from __future__ import annotations

from pathlib import Path

from .clipping import Highlight
from .transcription import Transcript, TranscriptSegment


def _ass_time(seconds: float) -> str:
    value = max(0.0, float(seconds))
    centis = int(round(value * 100))
    h, rem = divmod(centis, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _segments_for_clip(transcript: Transcript, clip: Highlight) -> list[TranscriptSegment]:
    out = []
    for seg in transcript.segments:
        if seg.end <= clip.start or seg.start >= clip.end:
            continue
        out.append(seg)
    return out


def write_ass_for_clip(
    transcript: Transcript,
    clip: Highlight,
    output: str | Path,
    *,
    width: int = 1080,
    height: int = 1920,
    font_name: str = "Noto Sans CJK KR",
) -> Path:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    font_size = max(44, round(height * 0.040))
    margin_v = max(120, round(height * 0.13))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000D7FF,&H00111111,&H70000000,-1,0,0,0,100,100,0,0,3,2.4,0,2,70,70,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events: list[str] = []
    for seg in _segments_for_clip(transcript, clip):
        start = max(0.0, seg.start - clip.start)
        end = min(clip.duration, seg.end - clip.start)
        if end <= start:
            continue

        if seg.words:
            karaoke = []
            for word in seg.words:
                ws = max(seg.start, word.start)
                we = min(seg.end, word.end)
                dur_cs = max(1, int(round(max(0.03, we - ws) * 100)))
                karaoke.append(r"{\k" + str(dur_cs) + "}" + _escape(word.text))
            text = " ".join(karaoke)
        else:
            text = _escape(seg.text)

        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )

    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out
