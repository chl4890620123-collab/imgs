from __future__ import annotations

import json
from pathlib import Path

from .captions import write_ass_for_clip
from .clipping import Highlight, find_highlights
from .quality import get_quality_preset
from .quality_gate import validate_vertical_output
from .reframe import render_vertical_clip
from .semantic import choose_transcript_highlights
from .subject import recommend_layout
from .transcription import Transcript, faster_whisper_available, transcribe_video


def _clip_text(transcript: Transcript | None, clip: Highlight) -> str:
    if transcript is None:
        return ""
    values = [
        seg.text
        for seg in transcript.segments
        if seg.end > clip.start and seg.start < clip.end
    ]
    return " ".join(values).strip()


def analyze_quality_shortform(
    source: str | Path,
    *,
    num_highlights: int = 3,
    target_duration_sec: float = 30.0,
    use_whisper: bool = True,
    whisper_model: str = "medium",
    language: str | None = "ko",
    strict_transcript: bool = False,
) -> dict:
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(src)

    transcript: Transcript | None = None
    transcript_error: str | None = None
    if use_whisper:
        ok, detail = faster_whisper_available()
        if ok:
            transcript = transcribe_video(src, model_size=whisper_model, language=language)
        else:
            transcript_error = detail
            if strict_transcript:
                raise RuntimeError(detail)

    if transcript is not None:
        highlights = choose_transcript_highlights(
            transcript,
            num_highlights=num_highlights,
            target_duration_sec=target_duration_sec,
        )
        method = "faster-whisper transcript + hook/coherence scoring"
        if not highlights:
            highlights = find_highlights(
                src,
                num_highlights=num_highlights,
                target_duration_sec=target_duration_sec,
            )
            method += " -> scene/speech fallback"
    else:
        highlights = find_highlights(
            src,
            num_highlights=num_highlights,
            target_duration_sec=target_duration_sec,
        )
        method = "scene-change + speech-density fallback"

    rows = []
    for clip in highlights:
        layout = recommend_layout(src, clip)
        rows.append({
            "highlight": clip.to_dict(),
            "text": _clip_text(transcript, clip),
            "layout": {
                "mode": layout.layout,
                "confidence": layout.confidence,
                "reason": layout.reason,
                "detected_ratio": layout.detected_ratio,
                "mean_face_x": layout.mean_face_x,
                "face_x_spread": layout.face_x_spread,
            },
        })

    return {
        "source": str(src),
        "method": method,
        "transcript_available": transcript is not None,
        "transcript_error": transcript_error,
        "transcript": transcript.to_dict() if transcript is not None else None,
        "candidates": rows,
    }


def run_quality_shortform_pipeline(
    source: str | Path,
    output_dir: str | Path,
    *,
    num_highlights: int = 3,
    target_duration_sec: float = 30.0,
    quality: str = "high",
    use_whisper: bool = True,
    whisper_model: str = "medium",
    language: str | None = "ko",
    strict_transcript: bool = False,
) -> dict:
    src = Path(source).expanduser().resolve()
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    preset = get_quality_preset(quality)

    analysis = analyze_quality_shortform(
        src,
        num_highlights=num_highlights,
        target_duration_sec=target_duration_sec,
        use_whisper=use_whisper,
        whisper_model=whisper_model,
        language=language,
        strict_transcript=strict_transcript,
    )

    transcript = None
    if analysis.get("transcript"):
        from .transcription import TranscriptSegment, TranscriptWord
        raw = analysis["transcript"]
        transcript = Transcript(
            language=str(raw.get("language") or "unknown"),
            segments=tuple(
                TranscriptSegment(
                    start=float(seg["start"]),
                    end=float(seg["end"]),
                    text=str(seg["text"]),
                    words=tuple(
                        TranscriptWord(
                            start=float(word["start"]),
                            end=float(word["end"]),
                            text=str(word["text"]),
                        )
                        for word in seg.get("words", [])
                    ),
                )
                for seg in raw.get("segments", [])
            ),
        )

    outputs = []
    for idx, row in enumerate(analysis["candidates"], 1):
        h = row["highlight"]
        clip = Highlight(
            start=float(h["start"]),
            end=float(h["end"]),
            score=float(h["score"]),
            speech_ratio=float(h["speech_ratio"]),
            scene_density=float(h["scene_density"]),
        )
        ass = None
        if transcript is not None:
            ass = out_dir / f"short_{idx:02d}.ass"
            write_ass_for_clip(
                transcript,
                clip,
                ass,
                width=preset.width,
                height=preset.height,
            )

        dest = out_dir / f"short_{idx:02d}_{quality}.mp4"
        render_vertical_clip(
            src,
            clip,
            dest,
            layout=row["layout"]["mode"],
            quality=quality,
            subtitles_ass=ass,
        )
        inspection = validate_vertical_output(
            dest,
            expected_width=preset.width,
            expected_height=preset.height,
            min_duration=max(1.0, min(clip.duration * 0.8, clip.duration - 0.1)),
        )
        outputs.append({
            "index": idx,
            "file": str(dest),
            "subtitle_file": str(ass) if ass else None,
            "highlight": clip.to_dict(),
            "text": row["text"],
            "layout": row["layout"],
            "inspection": inspection.to_dict(),
        })

    manifest = {
        "source": str(src),
        "output_dir": str(out_dir),
        "quality": quality,
        "method": analysis["method"],
        "transcript_available": analysis["transcript_available"],
        "transcript_error": analysis["transcript_error"],
        "count": len(outputs),
        "outputs": outputs,
    }
    manifest_path = out_dir / "shortform_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest["manifest"] = str(manifest_path)
    return manifest
