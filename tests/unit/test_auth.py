"""Test auth middleware and health endpoint."""
import os
import pytest
from httpx import AsyncClient, ASGITransport
from contextlib import asynccontextmanager


@pytest.fixture
def app_no_auth(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("NIGHTSCOUT_URL", "http://localhost:9999")
    import importlib
    import src.server as srv
    importlib.reload(srv)
    return srv.app


@pytest.fixture
def app_with_auth(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-secret-token")
    monkeypatch.setenv("NIGHTSCOUT_URL", "http://localhost:9999")
    import importlib
    import src.server as srv
    importlib.reload(srv)
    return srv.app


@asynccontextmanager
async def lifespan_client(app):
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


MCP_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    }
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


# --- Health endpoint ---

@pytest.mark.asyncio
async def test_health_returns_ok(app_no_auth):
    transport = ASGITransport(app=app_no_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_health_bypasses_auth(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200


# --- Auth: rejected requests ---

@pytest.mark.asyncio
async def test_mcp_without_token_rejected(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp", json=MCP_INIT, headers=MCP_HEADERS)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_with_wrong_bearer_rejected(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/mcp", json=MCP_INIT,
            headers={**MCP_HEADERS, "Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_with_wrong_path_token_rejected(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/mcp/wrong-token", json=MCP_INIT, headers=MCP_HEADERS)
        assert resp.status_code == 401


# --- Auth: accepted requests via Bearer header ---

@pytest.mark.asyncio
async def test_mcp_with_correct_bearer(app_with_auth):
    async with lifespan_client(app_with_auth) as client:
        resp = await client.post(
            "/mcp", json=MCP_INIT,
            headers={**MCP_HEADERS, "Authorization": "Bearer test-secret-token"},
        )
        assert resp.status_code == 200


# --- Auth: accepted requests via token in path ---

@pytest.mark.asyncio
async def test_mcp_with_correct_path_token(app_with_auth):
    async with lifespan_client(app_with_auth) as client:
        resp = await client.post(
            "/mcp/test-secret-token", json=MCP_INIT, headers=MCP_HEADERS,
        )
        assert resp.status_code == 200


# --- No auth mode ---

@pytest.mark.asyncio
async def test_mcp_no_auth_when_token_not_set(app_no_auth):
    async with lifespan_client(app_no_auth) as client:
        resp = await client.post("/mcp", json=MCP_INIT, headers=MCP_HEADERS)
        assert resp.status_code == 200
