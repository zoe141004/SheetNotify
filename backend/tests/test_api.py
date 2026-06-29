"""HTTP-layer API tests via ASGI transport (no database required).

Uses httpx.ASGITransport, which does NOT run the app lifespan, so these tests
exercise routing, auth gating, and schema generation without a live DB.
"""

import asyncio

import httpx

import main


def _request(method: str, path: str, headers: dict | None = None) -> httpx.Response:
    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=headers or {})

    return asyncio.run(_run())


def test_health_ok():
    response = _request("GET", "/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root_ok():
    response = _request("GET", "/")
    assert response.status_code == 200
    assert response.json()["service"] == "SheetNotify API"


def test_protected_endpoints_require_auth():
    for path in ("/api/sheets/subscriptions", "/api/logs", "/api/auth/me"):
        response = _request("GET", path)
        assert response.status_code in (401, 403), f"{path} not protected"


def test_invalid_jwt_rejected():
    response = _request(
        "GET", "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_openapi_schema_served():
    response = _request("GET", "/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
