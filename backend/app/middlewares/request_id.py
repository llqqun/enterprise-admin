"""Request correlation id.

Written as a plain ASGI middleware rather than Starlette's `BaseHTTPMiddleware`:
this only needs to touch the scope and the response headers, so there is no
reason to pay for a task group and a wrapped receive channel per request.
"""

import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders

REQUEST_ID_HEADER = "X-Request-Id"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class RequestIdMiddleware:
    """Attach a correlation id to `request.state` and to the response headers.

    An inbound `X-Request-Id` is honoured so a caller (or a reverse proxy) can
    correlate its own trace with ours.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        request_id = headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex

        # Starlette's Request.state reads from scope["state"]; creating it here
        # keeps the value available to route handlers.
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
