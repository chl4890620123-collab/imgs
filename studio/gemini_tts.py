from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

from project import DialogueLine, VoiceProfile


class GeminiTTS:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")

    def generate(self, line: DialogueLine, profile: VoiceProfile, out_file: str | Path) -> Path:
        out = Path(out_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{profile.model}:generateContent"
            f"?key={self.api_key}"
        )
        instruction = (
            f"한국어 성우 연기. 화자: {line.character}. "
            f"목소리 방향: {profile.style_text()}. "
            "대사는 바꾸거나 덧붙이지 말고 정확히 읽어라.\n"
            f"대사: {line.text}"
        )
        body = {
            "contents": [{"parts": [{"text": instruction}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": profile.voice_name}
                    }
                },
            },
        }
        r = requests.post(url, json=body, timeout=180)
        if not r.ok:
            raise RuntimeError(f"Gemini TTS 실패 {r.status_code}: {r.text[:1000]}")
        payload = r.json()
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                out.write_bytes(base64.b64decode(inline["data"]))
                return out
        raise RuntimeError("Gemini TTS 응답에서 오디오 데이터를 찾지 못했습니다.")
