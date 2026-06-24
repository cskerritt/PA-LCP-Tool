"""Small helpers for coercing HTML form values to typed Python values."""

from __future__ import annotations

from typing import Optional


def opt_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def opt_int(value: Optional[str]) -> Optional[int]:
    f = opt_float(value)
    return int(f) if f is not None else None


def as_bool(value: Optional[str]) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def clean(value: Optional[str]) -> str:
    return "" if value is None else str(value).strip()
