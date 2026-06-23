import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, MagicMock

from app.models import Check, User
from app.api.auth import _hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db: AsyncSession, email: str, plan: str = "free", checks_used: int = 0) -> User:
    user = User(email=email, hashed_password=_hash("pass"), plan=plan, checks_used=checks_used)
    db.add(user)
    await db.commit()   # must commit so the app's separate session can see the row
    await db.refresh(user)
    return user


async def _login(client: AsyncClient, email: str) -> dict:
    resp = await client.post("/auth/token", data={"username": email, "password": "pass"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# POST /checks/
# ---------------------------------------------------------------------------

async def test_create_check_returns_202_and_pending_status(
    client: AsyncClient, db: AsyncSession
):
    await _make_user(db, "creator@test.com")
    headers = await _login(client, "creator@test.com")

    with patch("celery_app.run_check") as mock_task:
        mock_task.delay = MagicMock()
        resp = await client.post("/checks/", json={"url": "https://tiktok.com/video/1"}, headers=headers)

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending"
    assert body["url"] == "https://tiktok.com/video/1"
    assert "id" in body
    mock_task.delay.assert_called_once_with(body["id"])


async def test_create_check_increments_checks_used(
    client: AsyncClient, db: AsyncSession
):
    user = await _make_user(db, "counter@test.com", checks_used=0)
    headers = await _login(client, "counter@test.com")

    with patch("celery_app.run_check") as mock_task:
        mock_task.delay = MagicMock()
        await client.post("/checks/", json={"url": "https://tiktok.com/v/1"}, headers=headers)

    await db.refresh(user)
    assert user.checks_used == 1


async def test_create_check_free_tier_limit_returns_402(
    client: AsyncClient, db: AsyncSession
):
    await _make_user(db, "limited@test.com", plan="free", checks_used=3)
    headers = await _login(client, "limited@test.com")

    resp = await client.post("/checks/", json={"url": "https://tiktok.com/v/1"}, headers=headers)
    assert resp.status_code == 402
    assert "limit" in resp.json()["detail"].lower()


async def test_create_check_pro_user_bypasses_limit(
    client: AsyncClient, db: AsyncSession
):
    await _make_user(db, "pro@test.com", plan="yearly", checks_used=100)
    headers = await _login(client, "pro@test.com")

    with patch("celery_app.run_check") as mock_task:
        mock_task.delay = MagicMock()
        resp = await client.post("/checks/", json={"url": "https://tiktok.com/v/1"}, headers=headers)

    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# GET /checks/
# ---------------------------------------------------------------------------

async def test_list_checks_returns_empty_for_new_user(
    client: AsyncClient, db: AsyncSession
):
    await _make_user(db, "empty@test.com")
    headers = await _login(client, "empty@test.com")

    resp = await client.get("/checks/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_checks_returns_only_own_checks(
    client: AsyncClient, db: AsyncSession
):
    user_a = await _make_user(db, "usera@test.com")
    user_b = await _make_user(db, "userb@test.com")

    # Give user_a a check directly in DB
    check = Check(url="https://tiktok.com/a", user_id=user_a.id, status="done")
    db.add(check)
    await db.commit()

    headers_b = await _login(client, "userb@test.com")
    resp = await client.get("/checks/", headers=headers_b)

    assert resp.status_code == 200
    assert resp.json() == []  # user_b sees nothing


# ---------------------------------------------------------------------------
# GET /checks/{id}
# ---------------------------------------------------------------------------

async def test_get_check_returns_check(client: AsyncClient, db: AsyncSession):
    user = await _make_user(db, "getter@test.com")
    check = Check(url="https://x.com/post/1", user_id=user.id, status="done", verdict="verified")
    db.add(check)
    await db.commit()
    await db.refresh(check)

    headers = await _login(client, "getter@test.com")
    resp = await client.get(f"/checks/{check.id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(check.id)
    assert body["verdict"] == "verified"
    assert body["claims"] == []


async def test_get_check_wrong_user_returns_404(client: AsyncClient, db: AsyncSession):
    owner = await _make_user(db, "owner@test.com")
    other = await _make_user(db, "other@test.com")

    check = Check(url="https://x.com/1", user_id=owner.id, status="done")
    db.add(check)
    await db.commit()
    await db.refresh(check)

    headers_other = await _login(client, "other@test.com")
    resp = await client.get(f"/checks/{check.id}", headers=headers_other)
    assert resp.status_code == 404


async def test_get_check_nonexistent_returns_404(client: AsyncClient, db: AsyncSession):
    await _make_user(db, "nobody@test.com")
    headers = await _login(client, "nobody@test.com")

    resp = await client.get(f"/checks/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
