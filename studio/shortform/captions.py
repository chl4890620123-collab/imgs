from __future__ import annotations

from pathlib import Path

from .clipping import Highlight
from .transcription import Transcript, TranscriptSegment, TranscriptWord


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
    return [
        seg
        for seg in transcript.segments
        if seg.end > clip.start and seg.start < clip.end
    ]


def _chunk_words(
    words: tuple[TranscriptWord, ...],
    *,
    max_chars: int = 22,
    max_duration: float = 2.8,
) -> list[tuple[TranscriptWord, ...]]:
    chunks: list[tuple[TranscriptWord, ...]] = []
    current: list[TranscriptWord] = []
    chars = 0
    start = None

    for word in words:
        text = word.text.strip()
        if not text:
            continue
        next_chars = chars + len(text) + (1 if current else 0)
        chunk_start = start if start is not None else word.start
        next_duration = max(0.0, word.end - chunk_start)
        if current and (next_chars > max_chars or next_duration > max_duration):
            chunks.append(tuple(current))
            current = []
            chars = 0
            start = None

        if not current:
            start = word.start
        current.append(word)
        chars += len(text) + (1 if len(current) > 1 else 0)

        if text.endswith((".", "!", "?", "。", "！", "？")) and len(current) >= 2:
            chunks.append(tuple(current))
            current = []
            chars = 0
            start = None

    if current:
        chunks.append(tuple(current))
    return chunks


def _plain_chunks(seg: TranscriptSegment, max_chars: int = 22) -> list[tuple[float, float, str]]:
    text = seg.text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [(seg.start, seg.end, text)]

    # When word timestamps are unavailable, split text by whitespace and divide
    # the original segment time proportionally. This keeps subtitles readable.
    tokens = text.split()
    if len(tokens) <= 1:
        return [(seg.start, seg.end, text)]

    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for token in tokens:
        next_count = count + len(token) + (1 if current else 0)
        if current and next_count > max_chars:
            chunks.append(" ".join(current))
            current = []
            count = 0
        current.append(token)
        count += len(token) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append(" ".join(current))

    total_chars = max(1, sum(len(x) for x in chunks))
    cursor = seg.start
    out = []
    for idx, chunk in enumerate(chunks):
        if idx == len(chunks) - 1:
            end = seg.end
        else:
            ratio = len(chunk) / total_chars
            end = min(seg.end, cursor + (seg.end - seg.start) * ratio)
        out.append((cursor, max(cursor + 0.35, end), chunk))
        cursor = end
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
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000D7FF,&H00111111,&H78000000,-1,0,0,0,100,100,0,0,3,2.8,0,2,80,80,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events: list[str] = []
    for seg in _segments_for_clip(transcript, clip):
        if seg.words:
            for words in _chunk_words(seg.words):
                start_abs = max(clip.start, words[0].start)
                end_abs = min(clip.end, words[-1].end)
                if end_abs <= start_abs:
                    continue
                karaoke = []
                for word in words:
                    ws = max(start_abs, word.start)
                    we = min(end_abs, word.end)
                    dur_cs = max(1, int(round(max(0.03, we - ws) * 100)))
                    karaoke.append(r"{\k" + str(dur_cs) + "}" + _escape(word.text))
                events.append(
                    "Dialogue: 0,"
                    f"{_ass_time(start_abs - clip.start)},"
                    f"{_ass_time(end_abs - clip.start)},"
                    "Default,,0,0,0,,"
                    + " ".join(karaoke)
                )
        else:
            for start_abs, end_abs, text in _plain_chunks(seg):
                start_abs = max(clip.start, start_abs)
                end_abs = min(clip.end, end_abs)
                if end_abs <= start_abs:
                    continue
                events.append(
                    "Dialogue: 0,"
                    f"{_ass_time(start_abs - clip.start)},"
                    f"{_ass_time(end_abs - clip.start)},"
                    f"Default,,0,0,0,,{_escape(text)}"
                )

    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out
