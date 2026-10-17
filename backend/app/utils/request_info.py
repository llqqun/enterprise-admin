"""Request metadata helpers: caller address and a coarse user-agent reading."""

from fastapi import Request

UNKNOWN = "Unknown"

# Order matters: an Edge UA also contains "Chrome/", and a Chrome UA also contains
# "Safari/". Most specific first.
_BROWSERS: tuple[tuple[str, str], ...] = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
    ("Trident/", "Internet Explorer"),
    ("MSIE", "Internet Explorer"),
    ("curl/", "curl"),
    ("python-httpx", "httpx"),
    ("HTTPie", "HTTPie"),
)

_OSES: tuple[tuple[str, str], ...] = (
    ("windows nt 10", "Windows 10/11"),
    ("windows nt 6.3", "Windows 8.1"),
    ("windows nt 6.1", "Windows 7"),
    ("windows", "Windows"),
    ("android", "Android"),
    ("iphone", "iOS"),
    ("ipad", "iOS"),
    ("mac os x", "macOS"),
    ("linux", "Linux"),
)


def client_ip(request: Request) -> str:
    """Best-effort caller address.

    `X-Forwarded-For` is honoured so a deployment behind a reverse proxy records
    the real caller; only the first hop is read. The header is client-supplied and
    therefore untrusted — it is audit metadata, never an authorisation input.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    return request.client.host if request.client else UNKNOWN


def parse_user_agent(user_agent: str | None) -> tuple[str, str]:
    """Return `(browser, os)`, or `(Unknown, Unknown)` when nothing matches.

    Deliberately coarse: this only ever feeds an audit column, so a wrong guess
    costs nothing and a dependency would cost maintenance.
    """
    ua = user_agent or ""
    lowered = ua.lower()

    browser = next((name for token, name in _BROWSERS if token in ua), UNKNOWN)
    os_name = next((name for token, name in _OSES if token in lowered), UNKNOWN)
    return browser, os_name
