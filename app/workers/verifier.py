"""Verify a claim: web search via Tavily, then verdict via Claude."""
import json
from dataclasses import dataclass

import anthropic
from tavily import TavilyClient

from app.config import settings

_tavily = TavilyClient(api_key=settings.tavily_api_key)
_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

_SYSTEM = """You are a fact-checking assistant. You will be given a factual claim and a set of \
web search results. Determine whether the claim is:
- "verified": clearly supported by reliable sources
- "false": clearly contradicted by reliable sources
- "misleading": partially true but missing important context, or exaggerated

Respond ONLY with valid JSON in this exact shape:
{
  "verdict": "verified" | "false" | "misleading",
  "confidence": 0.0-1.0,
  "reasoning": "one or two sentences explaining the verdict"
}"""


@dataclass
class VerificationResult:
    verdict: str
    confidence: float
    reasoning: str
    sources: list[dict]  # [{title, url, snippet, stance}]


def verify(claim_text: str) -> VerificationResult:
    search_response = _tavily.search(
        query=claim_text,
        search_depth="advanced",
        max_results=6,
        include_answer=False,
    )
    results = search_response.get("results", [])

    sources_block = "\n\n".join(
        f"[{i+1}] {r.get('title', '')}\nURL: {r['url']}\n{r.get('content', '')[:400]}"
        for i, r in enumerate(results)
    )

    message = _claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Claim: {claim_text}\n\nSearch results:\n{sources_block}",
            }
        ],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw.strip())

    verdict = parsed["verdict"]
    sources = [
        {
            "title": r.get("title"),
            "url": r["url"],
            "snippet": r.get("content", "")[:300],
            "stance": _infer_stance(verdict, r),
        }
        for r in results
    ]

    return VerificationResult(
        verdict=verdict,
        confidence=float(parsed.get("confidence", 0.8)),
        reasoning=parsed.get("reasoning", ""),
        sources=sources,
    )


def _infer_stance(overall_verdict: str, result: dict) -> str:
    """Heuristic: mark all sources as supporting the overall verdict.
    A more sophisticated version would ask Claude to score each source individually."""
    if overall_verdict == "verified":
        return "supports"
    if overall_verdict == "false":
        return "contradicts"
    return "neutral"
