# Deploying the web app to Railway

The Phase-2 web app (`palcp_web`) is a single FastAPI service backed by
PostgreSQL. It is containerized (see `Dockerfile`) and configured for Railway via
`railway.json`.

## 1. Create the project and database

1. In Railway, **New Project → Deploy from GitHub repo** and select
   `cskerritt/pa-lcp-tool` (branch with this code).
2. Add a database: **New → Database → PostgreSQL**. Railway provisions it and
   exposes a `DATABASE_URL` variable.
3. In the web service's **Variables**, reference the database and set secrets:
   - `DATABASE_URL` → reference the Postgres plugin's variable
     (e.g. `${{Postgres.DATABASE_URL}}`).
   - `SECRET_KEY` → a long random string (used to sign session cookies). Generate
     one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - *(optional)* `SESSION_HTTPS_ONLY=1` (default) keeps session cookies
     HTTPS-only; set to `0` only for local HTTP testing.

Railway sets `PORT` automatically; the app binds to it.

## 2. Build & start

Railway builds the `Dockerfile` and runs `scripts/start.sh`, which:

1. runs `alembic upgrade head` to create/migrate the schema, then
2. starts `uvicorn palcp_web.main:app` on `$PORT`.

The healthcheck path is `/health`.

## 3. First use

Open the service URL, **Create an account**, then create a case, add care items
(or import a CSV), optionally upload pricing tables and apply a rate library, and
generate the Excel report.

## URL notes

Railway's `DATABASE_URL` looks like `postgresql://user:pass@host:port/db`. The
app rewrites it to `postgresql+psycopg://…` automatically (psycopg 3 driver), so
no manual change is needed.

## Running locally

```bash
python -m pip install -e ".[web,dev]"
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export SESSION_HTTPS_ONLY=0          # allow cookies over http://localhost
# Defaults to a local SQLite file if DATABASE_URL is unset:
alembic upgrade head
uvicorn palcp_web.main:app --reload
# → http://127.0.0.1:8000
```

To run against a local Postgres instead, set `DATABASE_URL` before the alembic
and uvicorn commands.

## Migrations

The schema is managed by Alembic (`alembic/`). After changing the SQLAlchemy
models, create a migration and commit it:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

The deploy runs `alembic upgrade head` on every start, so committed migrations
are applied automatically.
