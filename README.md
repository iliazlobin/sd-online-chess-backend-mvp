# Online Chess — Backend MVP

Real-time two-player chess game server with WebSocket gameplay, PostgreSQL persistence, and declarative matchmaking.

## Quickstart

```bash
# Start with Docker Compose (PostgreSQL + app)
docker compose up --build

# Health check
curl http://localhost:8010/healthz

# Run tests
pip install -e ".[dev]"
pytest -v
```

## Project layout

```
src/chess_mvp/       # Application package
├── main.py          # App factory, lifespan, /healthz
├── config.py        # pydantic-settings configuration
├── database.py      # async SQLAlchemy engine + session
├── auth.py          # Bearer token auth dependency
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic request/response DTOs
├── routers/         # HTTP handlers (thin)
├── services/        # Business logic
└── ws/              # WebSocket handling
```

## Tech stack

- Python 3.12 + FastAPI
- PostgreSQL 16 + asyncpg + SQLAlchemy 2.0 async
- python-chess for game logic
- Alembic for schema migrations
