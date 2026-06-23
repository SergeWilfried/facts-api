from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models import Check, Claim, CheckCreate, CheckOut, Source, User

router = APIRouter()

FREE_DAILY_LIMIT = 3


@router.post("/", response_model=CheckOut, status_code=202)
async def create_check(
    body: CheckCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.plan == "free" and user.checks_used >= FREE_DAILY_LIMIT:
        raise HTTPException(status_code=402, detail="Free tier limit reached. Upgrade to Pro.")

    check = Check(url=body.url, user_id=user.id, status="pending")
    db.add(check)
    user.checks_used = (user.checks_used or 0) + 1
    await db.commit()
    await db.refresh(check)

    from celery_app import run_check  # lazy — avoids Redis connect on startup
    run_check.delay(str(check.id))

    return check


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
