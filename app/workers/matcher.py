"""Find similar previously-verified claims via pgvector cosine similarity."""
from typing import Optional
from dataclasses import dataclass

from openai import OpenAI
from sqlalchemy import text

from app.config import settings
from app.database import SyncSessionLocal

_openai = OpenAI(api_key=settings.openai_api_key)
_EMBED_MODEL = "text-embedding-3-small"
_SIMILARITY_THRESHOLD = 0.88


@dataclass
class MatchedClaim:
    claim_id: str
    text: str
    verdict: str
    similarity: float


def embed(text_: str) -> list[float]:
    response = _openai.embeddings.create(model=_EMBED_MODEL, input=text_)
    return response.data[0].embedding


def find_similar(claim_text: str) -> Optional[MatchedClaim]:
    """Return the most similar already-verified claim, or None if below threshold."""
    vector = embed(claim_text)
    vector_literal = "[" + ",".join(str(v) for v in vector) + "]"

    with SyncSessionLocal() as db:
        rows = db.execute(
            text(
                """
                SELECT c.id, c.text, c.verdict,
                       1 - (c.embedding <=> :vec::vector) AS similarity
                FROM claims c
                WHERE c.verdict IS NOT NULL
                  AND c.embedding IS NOT NULL
                  AND 1 - (c.embedding <=> :vec::vector) >= :threshold
                ORDER BY similarity DESC
                LIMIT 1
                """
            ),
            {"vec": vector_literal, "threshold": _SIMILARITY_THRESHOLD},
        ).fetchall()

    if not rows:
        return None

    row = rows[0]
    return MatchedClaim(
        claim_id=str(row.id),
        text=row.text,
        verdict=row.verdict,
        similarity=float(row.similarity),
    )
