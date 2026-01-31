# utils/time_utils.py
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TZ_TAIPEI = ZoneInfo("Asia/Taipei")


def now_utc() -> datetime:
    """Timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    """UTC aware ISO string, e.g. 2026-01-03T07:12:34.123456+00:00"""
    return now_utc().isoformat()


def ensure_aware_utc(dt: datetime) -> datetime:
    """
    Ensure dt is timezone-aware in UTC.
    - naive -> assume UTC
    - aware -> convert to UTC
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_utc_iso(iso_str: str) -> str:
    """
    Ensure an ISO string becomes UTC aware ISO.
    - if iso_str has no tzinfo -> assume UTC
    - if iso_str has tzinfo -> convert to UTC
    """
    dt = datetime.fromisoformat(iso_str)
    dt = ensure_aware_utc(dt)
    return dt.isoformat()


def parse_taipei_input_to_utc_iso(s: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Parse user input as Asia/Taipei and convert to UTC aware ISO.
    Input example: '2026-12-24 11:00'
    """
    local_dt = datetime.strptime(s.strip(), fmt).replace(tzinfo=TZ_TAIPEI)
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.isoformat()


def fmt_taipei(iso_str: str, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Format DB timestamptz (ISO) into Asia/Taipei string.
    If iso_str is naive ISO, we assume it's UTC.
    """
    dt = datetime.fromisoformat(iso_str)
    dt = ensure_aware_utc(dt)
    return dt.astimezone(TZ_TAIPEI).strftime(fmt)
