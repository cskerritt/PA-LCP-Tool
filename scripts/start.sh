#!/usr/bin/env sh
# Railway / container entrypoint: run migrations, then start the server.
set -e

echo "[start] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[start] Launching uvicorn on port ${PORT:-8000}..."
exec uvicorn palcp_web.main:app --host 0.0.0.0 --port "${PORT:-8000}"
