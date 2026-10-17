"""Pluggable cache with an in-memory TTL implementation.

Redis is deliberately not a dependency: it would add a moving part to every demo
start-up to serve capabilities (captcha TTL, login-failure counters, dictionary
caching) that fit comfortably in process memory. `CacheBackend` exists so that
swapping Redis in later is one new class plus one line at the bottom of this file.

Multi-worker caveat: a process-local cache means two uvicorn workers each hold
their own copy. That is the point at which Redis stops being optional — and the
point at which the abstraction pays for itself.
"""

import asyncio
import time
from typing import Any, Protocol


class CacheBackend(Protocol):
    """The contract every cache implementation must satisfy."""

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def incr(self, key: str, ttl: int | None = None) -> int: ...

    async def clear(self) -> None: ...


class MemoryCache:
    """Process-local TTL cache.

    Expiry is lazy: it is evaluated on read, and expired entries are also swept
    opportunistically whenever the store grows past `prune_threshold`. No
    background task is used — a stray sweeper task outliving its event loop causes
    more trouble than the memory it reclaims.
    """

    def __init__(self, prune_threshold: int = 64) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._lock = asyncio.Lock()
        self._prune_threshold = prune_threshold

    # -- internals --------------------------------------------------------
    @staticmethod
    def _expires_at(ttl: int | None) -> float | None:
        return None if ttl is None else time.monotonic() + ttl

    @staticmethod
    def _is_expired(expires_at: float | None) -> bool:
        return expires_at is not None and time.monotonic() >= expires_at

    def _prune(self) -> None:
        for key in [
            key
            for key, (_, expires_at) in self._store.items()
            if self._is_expired(expires_at)
        ]:
            self._store.pop(key, None)

    # -- contract ---------------------------------------------------------
    async def get(self, key: str) -> Any | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._is_expired(expires_at):
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            if len(self._store) >= self._prune_threshold:
                self._prune()
            self._store[key] = (value, self._expires_at(ttl))

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def incr(self, key: str, ttl: int | None = None) -> int:
        """Atomically increment, creating the key at 1 when absent or expired.

        The lock is held across the whole read-modify-write: login-failure counting
        is hit concurrently, and a lost update there would unlock an account early.
        An existing key keeps its original expiry.
        """
        async with self._lock:
            entry = self._store.get(key)
            if entry is not None and self._is_expired(entry[1]):
                entry = None

            if entry is None:
                self._store[key] = (1, self._expires_at(ttl))
                return 1

            value = int(entry[0]) + 1
            self._store[key] = (value, entry[1])
            return value

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


#: The process-wide cache. Swapping to Redis is a one-line change here.
cache: CacheBackend = MemoryCache()
