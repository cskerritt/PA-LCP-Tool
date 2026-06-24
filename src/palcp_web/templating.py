"""Jinja2 setup: shared template environment, filters, and flash messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .config import settings

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _money(value: Any) -> str:
    try:
        return "${:,.2f}".format(float(value))
    except (TypeError, ValueError):
        return ""


def _money0(value: Any) -> str:
    try:
        return "${:,.0f}".format(float(value))
    except (TypeError, ValueError):
        return ""


def _pct(value: Any) -> str:
    try:
        return "{:.2f}%".format(float(value) * 100.0)
    except (TypeError, ValueError):
        return ""


templates.env.filters["money"] = _money
templates.env.filters["money0"] = _money0
templates.env.filters["pct"] = _pct


# --------------------------------------------------------------------------- #
# Flash messages (one-shot, stored in the session)
# --------------------------------------------------------------------------- #
def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flashes", []).append([category, message])


def _pop_flashes(request: Request) -> list[list[str]]:
    return request.session.pop("_flashes", [])


def render(request: Request, name: str, user=None, status_code: int = 200,
           **context: Any):
    """Render a template with the shared globals injected."""
    ctx = {
        "user": user,
        "app_name": settings.app_name,
        "flashes": _pop_flashes(request),
        **context,
    }
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def render_partial(request: Request, name: str, **context: Any):
    """Render a fragment template (no flash popping, for HTMX swaps)."""
    return templates.TemplateResponse(request, name, dict(context))
