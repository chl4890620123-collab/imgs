from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TranscriptWord:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: tuple[TranscriptWord, ...] = ()

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": [asdict(x) for x in self.words],
        }


@dataclass(frozen=True)
class Transcript:
    language: str
    segments: tuple[TranscriptSegment, ...]

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "segments": [x.to_dict() for x in self.segments],
        }


def faster_whisper_available() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
        return True, "faster-whisper 사용 가능"
    except Exception:
        return (
            False,
            "고품질 자동 자막/의미 분석에는 faster-whisper가 필요합니다. "
            "python -m pip install -r studio/requirements-quality.txt",
        )


def transcribe_video(
    video: str | Path,
    *,
    model_size: str = "medium",
    language: str | None = "ko",
) -> Transcript:
    ok, detail = faster_whisper_available()
    if not ok:
        raise RuntimeError(detail)

    from faster_whisper import WhisperModel

    source = Path(video).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)

    model = WhisperModel(model_size, device="auto", compute_type="auto")
    segments_iter, info = model.transcribe(
        str(source),
        language=language or None,
        vad_filter=True,
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=True,
    )

    segments: list[TranscriptSegment] = []
    for item in segments_iter:
        words = tuple(
            TranscriptWord(
                start=float(word.start or item.start or 0.0),
                end=float(word.end or item.end or 0.0),
                text=str(word.word or "").strip(),
            )
            for word in (item.words or [])
            if str(word.word or "").strip()
        )
        text = str(item.text or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(item.start or 0.0),
                end=float(item.end or 0.0),
                text=text,
                words=words,
            )
        )

    detected = str(getattr(info, "language", None) or language or "unknown")
    return Transcript(language=detected, segments=tuple(segments))
