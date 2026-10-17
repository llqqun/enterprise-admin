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
    """An HTTP client wired straight to the ASGI app (no network, no server)."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
