"""Extract discrete factual claims from caption + transcript."""
import json
import logging
from typing import Optional

from app.workers import llm

logger = logging.getLogger(__name__)

_SYSTEM = """You are a fact-checking assistant. Given the text content of a social media post or article, \
extract every distinct factual claim that can be independently verified. \
Ignore opinions, predictions, and calls to action. \
Return ONLY a JSON array of strings, each string being one claim. No explanation, no markdown. \
Example: ["Honey never expires", "Archaeologists found 3000-year-old honey in Egypt"]"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences, handling both ```json and ``` variants."""
    if "```" not in text:
        return text
    # Find content between first and last fence
    parts = text.split("```")
    if len(parts) >= 3:
        inner = parts[1]
        if inner.startswith("json"):
            inner = inner[4:]
        return inner.strip()
    return text


def extract_claims(caption: Optional[str], transcript: Optional[str]) -> list[str]:
    content = "\n\n".join(filter(None, [caption, transcript]))
    if not content.strip():
        return []

    raw = llm.complete(system=_SYSTEM, user=f"Post content:\n{content}")
    logger.info("LLM raw response for claim extraction: %r", raw[:500] if raw else "<empty>")

    text = _strip_fences(raw).strip()

    if not text:
        logger.warning("LLM returned empty content for claim extraction")
        return []

    try:
        claims: list[str] = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("LLM response is not valid JSON, got: %r", text[:300])
        return []

    return [c for c in claims if isinstance(c, str) and c.strip()]
