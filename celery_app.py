"""Celery application and the main fact-check pipeline task."""
from celery import Celery

from app.config import settings

celery = Celery(
    "kaseto",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["celery_app"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery.task(bind=True, max_retries=2, default_retry_delay=10)
def run_check(self, check_id: str) -> dict:
    """
    Full pipeline:
      extract → transcribe → extract claims →
        for each claim: match (pgvector) or verify (Tavily + Claude)
    """
    from app.database import SyncSessionLocal
    from app.models import Check, Claim, Source
    from app.workers import extractor, transcriber, claim_extractor, matcher, verifier
    from app.workers.matcher import embed

    def _set_status(db, check, status: str):
        check.status = status
        db.commit()

    with SyncSessionLocal() as db:
        check = db.get(Check, check_id)
        if check is None:
            return {"error": "check not found"}

        try:
            # 1. Extract content from the social media URL
            _set_status(db, check, "extracting")
            content = extractor.extract(check.url)
            check.platform = content.platform
            check.author_handle = content.author_handle
            check.caption = content.caption
            db.commit()

            # 2. Transcribe video audio if available
            _set_status(db, check, "transcribing")
            transcript = transcriber.transcribe(content.video_url)
            check.transcript = transcript
            db.commit()

            # 3. Extract individual factual claims
            _set_status(db, check, "analyzing")
            claim_texts = claim_extractor.extract_claims(content.caption, transcript)

            if not claim_texts:
                check.status = "done"
                check.verdict = "verified"  # nothing verifiable found
                db.commit()
                return {"check_id": check_id, "verdict": "verified", "claims": 0}

            # 4. For each claim: try pgvector match first, fall back to full verification
            _set_status(db, check, "verifying")
            verdicts: list[str] = []
            scores: list[float] = []

            for claim_text in claim_texts:
                claim = Claim(check_id=check_id, text=claim_text)
                db.add(claim)
                db.flush()  # get claim.id without committing

                # Try to reuse a previous verified result
                match = matcher.find_similar(claim_text)
                if match:
                    claim.verdict = match.verdict
                    claim.confidence = match.similarity
                    claim.reasoning = f"Matched a previously verified claim (similarity {match.similarity:.2f})."
                else:
                    result = verifier.verify(claim_text)
                    claim.verdict = result.verdict
                    claim.confidence = result.confidence
                    claim.reasoning = result.reasoning

                    for s in result.sources:
                        db.add(Source(
                            claim_id=claim.id,
                            title=s["title"],
                            url=s["url"],
                            snippet=s["snippet"],
                            stance=s["stance"],
                        ))

                # Store embedding for future matching
                try:
                    from pgvector.sqlalchemy import Vector
                    claim.embedding = embed(claim_text)
                except Exception:
                    pass  # non-fatal: embedding just won't be stored

                verdicts.append(claim.verdict)
                # For truth score: verified claims contribute their confidence;
                # false/misleading claims contribute (1 - confidence) since high
                # confidence in a false claim means low truth.
                c = claim.confidence or 0.5
                scores.append(c if claim.verdict == "verified" else 1.0 - c)
                db.commit()

            # 5. Roll up an overall verdict: false > misleading > verified
            if "false" in verdicts:
                overall = "false"
            elif "misleading" in verdicts:
                overall = "misleading"
            else:
                overall = "verified"

            check.verdict = overall
            check.score = sum(scores) / len(scores) if scores else None
            check.status = "done"
            db.commit()
            return {"check_id": check_id, "verdict": overall, "claims": len(verdicts)}

        except Exception as exc:
            check.status = "failed"
            check.error = str(exc)
            db.commit()
            raise self.retry(exc=exc)
