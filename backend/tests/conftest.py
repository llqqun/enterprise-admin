"""Shared pytest fixtures.

Async tests need no decorator: `pytest.ini` sets `asyncio_mode = auto` and
`pythonpath = .`, so `app` is importable and every `async def test_*` runs.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired straight to the ASGI app (no network, no server).

    `raise_app_exceptions=False` mirrors what a real server does: Starlette's
    ServerErrorMiddleware renders the 500 response and *then* re-raises so the
    server can log it. A real client sees the response, so the test client must
    too — otherwise the "unhandled exception" tests could never observe the
    handler's output.
    """
    app = create_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
