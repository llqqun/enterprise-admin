"""Cache abstraction: TTL semantics of the in-memory implementation."""

import asyncio

import pytest

from app.core.cache import MemoryCache


@pytest.fixture()
def cache() -> MemoryCache:
    return MemoryCache()


async def test_set_and_get(cache: MemoryCache) -> None:
    await cache.set("k", "v")

    assert await cache.get("k") == "v"


async def test_get_missing_returns_none(cache: MemoryCache) -> None:
    assert await cache.get("nope") is None


async def test_delete(cache: MemoryCache) -> None:
    await cache.set("k", "v")

    await cache.delete("k")

    assert await cache.get("k") is None


async def test_exists(cache: MemoryCache) -> None:
    await cache.set("k", "v")

    assert await cache.exists("k") is True
    assert await cache.exists("other") is False


async def test_expires_after_ttl(cache: MemoryCache) -> None:
    await cache.set("k", "v", ttl=1)

    assert await cache.get("k") == "v"
    await asyncio.sleep(1.1)
    assert await cache.get("k") is None


async def test_ttl_none_never_expires(cache: MemoryCache) -> None:
    await cache.set("k", "v", ttl=None)

    await asyncio.sleep(0.05)

    assert await cache.get("k") == "v"


async def test_expired_key_is_not_reported_as_existing(cache: MemoryCache) -> None:
    await cache.set("k", "v", ttl=1)

    await asyncio.sleep(1.1)

    assert await cache.exists("k") is False


async def test_incr_creates_and_increments(cache: MemoryCache) -> None:
    assert await cache.incr("counter") == 1
    assert await cache.incr("counter") == 2
    assert await cache.incr("counter") == 3


async def test_incr_respects_ttl(cache: MemoryCache) -> None:
    await cache.incr("counter", ttl=1)

    await asyncio.sleep(1.1)

    assert await cache.incr("counter", ttl=1) == 1


async def test_incr_is_atomic_under_concurrency(cache: MemoryCache) -> None:
    """Login-failure counting is hit concurrently; a lost update would unlock early."""
    await asyncio.gather(*(cache.incr("counter") for _ in range(50)))

    assert await cache.get("counter") == 50


async def test_clear_empties_cache(cache: MemoryCache) -> None:
    await cache.set("a", 1)
    await cache.set("b", 2)

    await cache.clear()

    assert await cache.get("a") is None
    assert await cache.get("b") is None


async def test_stores_arbitrary_values(cache: MemoryCache) -> None:
    payload = {"nested": [1, 2, {"three": 3}]}

    await cache.set("k", payload)

    assert await cache.get("k") == payload
