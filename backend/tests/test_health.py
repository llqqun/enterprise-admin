"""Health endpoint: the smoke test that proves the app assembles and serves."""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"


async def test_health_sets_request_id_header(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.headers.get("X-Request-Id")
