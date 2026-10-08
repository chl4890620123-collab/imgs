from __future__ import annotations

import re

from .clipping import Highlight, _overlap
from .transcription import Transcript


HOOK_TERMS = (
    "왜", "근데", "그런데", "사실", "결국", "문제는", "핵심", "중요", "절대",
    "딱", "바로", "처음", "마지막", "비밀", "이유", "방법", "결론", "반전",
    "how", "why", "but", "actually", "secret", "reason", "important", "never",
)


def _text_score(text: str) -> float:
    value = text.strip()
    if not value:
        return 0.0
    lowered = value.lower()
    score = sum(1.0 for term in HOOK_TERMS if term in lowered)
    if "?" in value or "？" in value:
        score += 1.1
    if re.search(r"\d", value):
        score += 0.7
    if "!" in value or "！" in value:
        score += 0.45
    if value.endswith((".", "!", "?", "다.", "요.")):
        score += 0.25
    return score


def choose_transcript_highlights(
    transcript: Transcript,
    *,
    num_highlights: int = 3,
    target_duration_sec: float = 30.0,
    max_duration_sec: float = 60.0,
) -> list[Highlight]:
    segments = list(transcript.segments)
    if not segments:
        return []

    count = max(1, min(20, int(num_highlights)))
    target = max(8.0, min(float(target_duration_sec), float(max_duration_sec)))
    candidates: list[tuple[Highlight, str]] = []

    for i, first in enumerate(segments):
        start = first.start
        end = first.end
        texts = [first.text]
        j = i + 1
        while j < len(segments) and end - start < target:
            end = segments[j].end
            texts.append(segments[j].text)
            j += 1

        duration = max(0.1, end - start)
        if duration < min(6.0, target * 0.5):
            continue

        joined = " ".join(texts).strip()
        lexical = _text_score(joined)
        chars_per_sec = min(1.0, len(joined) / max(1.0, duration * 8.0))
        length_fit = max(0.0, 1.0 - abs(duration - target) / max(target, 1.0))
        sentence_complete = 1.0 if joined.endswith((".", "!", "?", "다.", "요.")) else 0.4
        score = (
            min(1.0, lexical / 3.0) * 0.40
            + chars_per_sec * 0.25
            + length_fit * 0.22
            + sentence_complete * 0.13
        )
        candidates.append((
            Highlight(
                start=float(start),
                end=float(min(end, start + max_duration_sec)),
                score=round(score, 6),
                speech_ratio=chars_per_sec,
                scene_density=min(1.0, lexical / 3.0),
            ),
            joined,
        ))

    chosen: list[Highlight] = []
    for candidate, _text in sorted(candidates, key=lambda x: x[0].score, reverse=True):
        if any(
            _overlap(candidate.start, candidate.end, old.start, old.end)
            > min(candidate.duration, old.duration) * 0.35
            for old in chosen
        ):
            continue
        chosen.append(candidate)
        if len(chosen) >= count:
            break

    return sorted(chosen, key=lambda x: x.start)
