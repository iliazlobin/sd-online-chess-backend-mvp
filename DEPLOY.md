# Deploy — Online Chess Backend MVP

## Prerequisites

- Docker Engine 24+ with Compose v2 plugin
- Git
- A running PostgreSQL 16 instance (only for local dev without Docker)

## Quick start (Docker Compose)

```bash
# 1. Clone
git clone git@github.com:iliazlobin/sd-online-chess-backend-mvp.git
cd sd-online-chess-backend-mvp

# 2. Create env file from template (all defaults are safe for local dev)
cp .env.example .env

# 3. Build and start
docker compose up --build -d

# 4. Wait for migrations (Compose runs `alembic upgrade head` as part of app startup)
#    Check logs for migration output:
docker compose logs app

# 5. Verify health
curl http://localhost:8010/healthz
# Expected: {"status":"ok"}

# 6. Run tests
pip install -e ".[dev]"
pytest -v
```

## Teardown

```bash
docker compose down -v
```

Removing the `-v` flag keeps the Postgres data volume for reuse.

## Service layout

| Service | Container port | Host port (configurable) | Healthcheck |
|---------|---------------|--------------------------|-------------|
| `db`    | 5432          | not published            | `pg_isready` |
| `app`   | 8000          | `${APP_PORT:-8010}`      | `GET /healthz` |

Only `app` publishes a host port. Postgres is reachable over the compose-internal network at `db:5432`.

## Configuration

All settings are read from the environment / `.env` file. See `.env.example` for all keys and their defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://chess:chess@localhost:5432/chess_mvp` | PostgreSQL connection string |
| `APP_PORT` | `8000` | Port uvicorn listens on inside container |
| `DB_POOL_SIZE` | `10` | Async DB pool connections |
| `DB_MAX_IDLE_SECONDS` | `300` | Max idle before connection recycle |

Override any variable by setting it in `.env` or exporting it before `docker compose up`.

Alias for common port overrides:

```bash
APP_PORT=8010 docker compose up -d
```

## Healthchecks

- **Docker image:** built-in `HEALTHCHECK` via `curl http://localhost:8000/healthz`
- **Compose:** `db` healthcheck via `pg_isready`; `app` waits for `db` healthy before starting
- **Manual:** `curl http://localhost:${APP_PORT:-8010}/healthz`

## Logs

```bash
# All services
docker compose logs -f

# App only
docker compose logs -f app

# Database only
docker compose logs -f db
```

## Migrations

Alembic owns the schema. Migrations run on every `docker compose up` via the app startup sequence.
The application code does **not** call `create_all()` — schema changes are controlled through migration files.

To run migrations manually:

```bash
docker compose run --rm app alembic upgrade head
```

## Local development (without Docker)

```bash
# Requires a running PostgreSQL on localhost:5432
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Copy and adjust .env to point to your local PG
cp .env.example .env
# Edit .env: DATABASE_URL=postgresql+asyncpg://chess:chess@localhost:5432/chess_mvp

# Run migrations
alembic upgrade head

# Start server (port from APP_PORT env, default 8000)
uvicorn chess_mvp.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}

# In another terminal:
curl http://localhost:8000/healthz
pytest -v
```
