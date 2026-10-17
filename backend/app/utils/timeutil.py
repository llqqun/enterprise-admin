"""Time helpers.

The application stores naive UTC datetimes in MySQL `DATETIME` columns, and MySQL
itself runs with `default-time-zone='+00:00'` so server-side `now()` agrees. Both
sides must therefore produce the same thing; this module is the one place that
decides what "now" means.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching the column type."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
