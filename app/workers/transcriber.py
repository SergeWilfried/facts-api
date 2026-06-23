"""Download a video and transcribe its audio via OpenAI Whisper API."""
import os
import tempfile
from typing import Optional

import httpx
from openai import OpenAI

from app.config import settings

_client = OpenAI(api_key=settings.openai_api_key)


def transcribe(video_url: Optional[str]) -> Optional[str]:
    """Return the transcript text, or None if no video URL was provided."""
    if not video_url:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "video.mp4")

        with httpx.stream("GET", video_url, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(video_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        with open(video_path, "rb") as audio_file:
            response = _client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

    return response if isinstance(response, str) else response.text
