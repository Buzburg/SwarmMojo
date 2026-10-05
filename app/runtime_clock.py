"""Explicitly zoned current time, including hosts without an IANA database."""
from datetime import datetime, timezone
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def current_time() -> str:
    try:
        zone = ZoneInfo(os.getenv("TZ", "America/Chicago"))
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return datetime.now(zone).isoformat()
