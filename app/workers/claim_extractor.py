"""Extract discrete factual claims from caption + transcript using Claude."""
import json
from typing import Optional

import anthropic

from app.config import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM = """You are a fact-checking assistant. Given the text content of a social media post, \
extract every distinct factual claim that can be independently verified. \
Ignore opinions, predictions, and calls to action. \
Return a JSON array of strings, each string being one claim. \
Example: ["Honey never expires", "Archaeologists found 3000-year-old honey in Egypt"]"""


def extract_claims(caption: Optional[str], transcript: Optional[str]) -> list[str]:
    content = "\n\n".join(filter(None, [caption, transcript]))
    if not content.strip():
        return []

    message = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": f"Post content:\n{content}"}],
    )

    text = message.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    claims: list[str] = json.loads(text)
    return [c for c in claims if isinstance(c, str) and c.strip()]
