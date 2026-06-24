"""FastAPI application entry point.

Run locally with::

    alembic upgrade head           # create / migrate the database
    uvicorn palcp_web.main:app --reload

On Railway the start command runs ``alembic upgrade head`` then uvicorn (see the
Dockerfile / scripts/start.sh).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .security import AuthRequired
from .templating import render
from .routers import auth, cases, items, pricing, rates, reports

logger = logging.getLogger("palcp_web")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.secret_key_was_generated:
        logger.warning(
            "SECRET_KEY is not set; using a random per-process key. Set SECRET_KEY "
            "in the environment so sessions survive restarts.")
    try:
        from .db import SessionLocal
        from .services import ensure_default_va_library
        with SessionLocal() as db:
            ensure_default_va_library(db)
    except Exception:  # pragma: no cover - never block startup on seeding
        logger.exception("Could not seed default VA pricing library")
    yield


app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None,
              lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    https_only=settings.session_https_only,
    same_site="lax",
    max_age=14 * 24 * 3600,
)

_static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

for r in (auth.router, cases.router, items.router, pricing.router,
          rates.router, reports.router):
    app.include_router(r)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}


@app.exception_handler(AuthRequired)
async def _auth_required_handler(request: Request, exc: AuthRequired):
    # HTMX needs a header redirect; normal requests get a 303.
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    accepts_html = "text/html" in request.headers.get("accept", "")
    if accepts_html and exc.status_code in (400, 403, 404):
        return render(request, "error.html", status_code=exc.status_code,
                      code=exc.status_code, detail=exc.detail)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
