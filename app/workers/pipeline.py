"""Synchronous fact-check pipeline — runs in a thread executor."""
from app.database import SyncSessionLocal
from app.models import Check, Claim, Source


def run(check_id: str) -> None:
    from app.workers import extractor, transcriber, claim_extractor, matcher, verifier
    from app.workers.matcher import embed

    def _set_status(db, check, status: str):
        check.status = status
        db.commit()

    with SyncSessionLocal() as db:
        check = db.get(Check, check_id)
        if check is None:
            return

        try:
            _set_status(db, check, "extracting")
            content = extractor.extract(check.url)
            check.platform = content.platform
            check.author_handle = content.author_handle
            check.caption = content.caption
            db.commit()

            _set_status(db, check, "transcribing")
            transcript = transcriber.transcribe(content.video_url)
            check.transcript = transcript
            db.commit()

            _set_status(db, check, "analyzing")
            claim_texts = claim_extractor.extract_claims(content.caption, transcript)

            if not claim_texts:
                check.status = "done"
                check.verdict = "verified"
                db.commit()
                return

            _set_status(db, check, "verifying")
            verdicts: list[str] = []
            scores: list[float] = []

            for claim_text in claim_texts:
                claim = Claim(check_id=check_id, text=claim_text)
                db.add(claim)
                db.flush()

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

                try:
                    claim.embedding = embed(claim_text)
                except Exception:
                    pass

                verdicts.append(claim.verdict)
                c = claim.confidence or 0.5
                scores.append(c if claim.verdict == "verified" else 1.0 - c)
                db.commit()

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

        except Exception as exc:
            check.status = "failed"
            check.error = str(exc)
            db.commit()
            raise
