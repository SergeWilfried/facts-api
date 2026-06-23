import asyncio
from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models import Check, Claim, CheckCreate, CheckOut, User

router = APIRouter()

FREE_DAILY_LIMIT = 20


async def _load_check(db: AsyncSession, check_id) -> Check:
    result = await db.execute(
        select(Check)
        .where(Check.id == check_id)
        .options(selectinload(Check.claims).selectinload(Claim.sources))
    )
    return result.scalar_one()


@router.post("/", response_model=CheckOut, status_code=200)
async def create_check(
    body: CheckCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Return cached result if this URL was already successfully checked
    cached = await db.execute(
        select(Check)
        .where(Check.url == body.url, Check.status == "done")
        .options(selectinload(Check.claims).selectinload(Claim.sources))
        .order_by(Check.created_at.desc())
        .limit(1)
    )
    if hit := cached.scalar_one_or_none():
        return hit

    if user.plan == "free" and user.checks_used >= FREE_DAILY_LIMIT:
        raise HTTPException(status_code=402, detail="Free tier limit reached. Upgrade to Pro.")

    check = Check(url=body.url, user_id=user.id, status="pending")
    db.add(check)
    user.checks_used = (user.checks_used or 0) + 1
    await db.commit()

    from app.workers.pipeline import run
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(run, str(check.id)))

    return await _load_check(db, check.id)


@router.get("/", response_model=list[CheckOut])
async def list_checks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Check)
        .where(Check.user_id == user.id)
        .options(selectinload(Check.claims).selectinload(Claim.sources))
        .order_by(Check.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/{check_id}", response_model=CheckOut)
async def get_check(
    check_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Check)
        .where(Check.id == check_id, Check.user_id == user.id)
        .options(selectinload(Check.claims).selectinload(Claim.sources))
    )
    check = result.scalar_one_or_none()
    if check is None:
        raise HTTPException(status_code=404, detail="Check not found")
    return check
