"""Extract discrete factual claims from caption + transcript."""
import json
from typing import Optional

from app.workers import llm

_SYSTEM = """You are a fact-checking assistant. Given the text content of a social media post or article, \
extract every distinct factual claim that can be independently verified. \
Ignore opinions, predictions, and calls to action. \
Return a JSON array of strings, each string being one claim. \
Example: ["Honey never expires", "Archaeologists found 3000-year-old honey in Egypt"]"""


def extract_claims(caption: Optional[str], transcript: Optional[str]) -> list[str]:
    content = "\n\n".join(filter(None, [caption, transcript]))
    if not content.strip():
        return []

    text = llm.complete(system=_SYSTEM, user=f"Post content:\n{content}")
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    claims: list[str] = json.loads(text)
    return [c for c in claims if isinstance(c, str) and c.strip()]
