import pytest
from httpx import AsyncClient


async def test_register_returns_token(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"email": "new@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "hunter2"}
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


async def test_login_returns_token(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "mypassword"},
    )
    resp = await client.post(
        "/auth/token",
        data={"username": "login@example.com", "password": "mypassword"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"email": "wrongpw@example.com", "password": "correct"},
    )
    resp = await client.post(
        "/auth/token",
        data={"username": "wrongpw@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient):
    resp = await client.post(
        "/auth/token",
        data={"username": "ghost@example.com", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_protected_route_without_token_returns_401(client: AsyncClient):
    resp = await client.get("/checks/")
    assert resp.status_code == 401


async def test_protected_route_with_invalid_token_returns_401(client: AsyncClient):
    resp = await client.get(
        "/checks/",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert resp.status_code == 401
