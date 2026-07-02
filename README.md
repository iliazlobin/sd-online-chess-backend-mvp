# Online Chess — Backend MVP

Real-time two-player chess game server with WebSocket gameplay, server-authoritative move validation (via python-chess), PostgreSQL persistence, and declarative matchmaking.

[![Lint](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/lint.yml)
[![CI](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/ci.yml)
[![Functional](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml)

## Quickstart

```bash
# 1. Clone
git clone git@github.com:iliazlobin/sd-online-chess-backend-mvp.git
cd sd-online-chess-backend-mvp

# 2. Create env file (safe defaults for local dev)
cp .env.example .env

# 3. Build and start full stack
docker compose up --build -d

# 4. Wait for migrations + health
curl http://localhost:8010/healthz
# → {"status":"ok"}

# 5. Run acceptance tests
pip install -e ".[dev]"
pytest -v
```

## Architecture

```mermaid
flowchart TD
    Client["<b>Browser / Client</b>"] -->|REST: POST /players| RTR["<b>FastAPI Routers</b><br/>players / matchmaking / games / health"]
    Client -->|WS: ws://host/games/{id}| WS_H["<b>WebSocket Handler</b><br/>game_handler.py"]
    RTR -->|call| SVC["<b>Service Layer</b><br/>player / game / matchmaking / chess"]
    WS_H -->|recv/send| GM["<b>GameManager</b><br/>in-memory active games<br/>python-chess Board<br/>asyncio.Lock per game"]
    GM -->|validate moves| CHESS["<b>ChessService</b><br/>python-chess wrapper"]
    SVC -->|async queries| PG[("<b>PostgreSQL</b><br/>players / games / moves<br/>matchmaking_queue")]
    GM -->|persist moves| SVC
    style Client fill:#1a1a2e,color:#eee
    style PG fill:#336791,color:#fff
    style GM fill:#2d4f2d,color:#e0ffe0
```

**Key principle:** The FastAPI process owns all active-game state in memory. `python-chess` `Board` objects live inside the `GameManager` singleton. PostgreSQL is the durable store — every move is persisted, and on restart games reload from DB.

## API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/players` | none | Register a new player — returns `player_id` + bearer `token` |
| `POST` | `/matchmaking` | Bearer | Enter matchmaking queue or match with a waiting opponent |
| `WS` | `/games/{game_id}?token=` | query | WebSocket connection for real-time gameplay |
| `GET` | `/games/{game_id}` | Bearer | Get full game state + move history |
| `GET` | `/players/{id}/games` | Bearer | List a player's completed games |
| `GET` | `/healthz` | none | Health check |

### WebSocket Protocol

**Client → Server (JSON frames):**
```json
{"type": "move", "from": "e2", "to": "e4"}
{"type": "move", "from": "e7", "to": "e8", "promotion": "q"}
{"type": "resign"}
```

**Server → Client:**
| Event | When |
|-------|------|
| `game_state` | On connect — current FEN, player color, opponent ID |
| `move_made` | After a legal move — new FEN + legal moves count |
| `game_over` | Checkmate, stalemate, or resignation — winner and reason |
| `opponent_connected` | Opponent joins the game |
| `opponent_disconnected` | Opponent leaves the game |
| `error` | `ILLEGAL_MOVE`, `NOT_YOUR_TURN`, or invalid message |

### Error codes

| Code | Meaning |
|------|---------|
| `ILLEGAL_MOVE` | Move violates chess rules (e.g. pawn jumps 3 squares) |
| `NOT_YOUR_TURN` | Player tried to move when it was the opponent's turn |
| `INVALID_JSON` | Message body is not valid JSON |
| `UNKNOWN_MESSAGE_TYPE` | `type` field is not `move` or `resign` |

## Project layout

```
src/chess_mvp/          # Application package
├── main.py             # App factory, lifespan, /healthz, WS route
├── config.py           # pydantic-settings config (DATABASE_URL, APP_PORT, etc.)
├── database.py         # async SQLAlchemy engine + session factory
├── auth.py             # Bearer token auth middleware (FastAPI dependency)
├── models/             # SQLAlchemy ORM: Player, Game, Move, MatchmakingQueue
├── schemas/            # Pydantic request/response DTOs
├── routers/            # Thin HTTP handlers: players, games, matchmaking, health
├── services/           # Business logic: player, game, matchmaking, chess (python-chess)
└── ws/                 # WebSocket handler + GameManager singleton

alembic/                # Schema migrations (sole schema owner — no create_all)
tests/                  # White-box unit tests (app imports)
verify/acceptance/      # Black-box acceptance tests (HTTP/WS only, one per FR)

pyproject.toml          # Dependencies + tool config
Dockerfile              # Multi-stage build (python:3.12-slim)
docker-compose.yml      # db + app (Postgres 16, only app publishes host port)
```

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12, FastAPI, Starlette WebSocket |
| Database | PostgreSQL 16 via asyncpg + SQLAlchemy 2.0 async |
| Migrations | Alembic (sole schema owner) |
| Chess logic | python-chess (pure Python, no engine dependency) |
| Auth | Simple bearer tokens (UUID4, no OAuth for MVP) |
| Containers | Multi-stage Docker build, Docker Compose |
| CI/CD | GitHub Actions: lint (ruff), unit tests, functional (full-stack acceptance) |

## Acceptance test coverage

16 black-box test functions across 10 files covering all 8 functional requirements:

| FR | Requirement | Tests |
|----|-------------|-------|
| FR-1 | Register player | 201 with player_id+token; 409 on duplicate username |
| FR-2 | Matchmaking | First player waits (200); second triggers match (202, same game_id) |
| FR-3 | WebSocket connect | Valid token → game_state event; invalid token → HTTP 403 |
| FR-4 | Legal move | e2-e4 accepted, FEN advances; e2-e5 → ILLEGAL_MOVE; wrong turn → NOT_YOUR_TURN |
| FR-4 | Checkmate | Scholar's Mate → game_over "1-0 — White wins by checkmate" |
| FR-4 | Stalemate | 10-move stalemate sequence → game_over "½-½ — Draw" |
| FR-5 | Resign | Black resigns → "1-0 — White wins by resignation" |
| FR-6 | Get game state | 200 with full data; nonexistent game → 404 |
| FR-7 | List games | 200 with games array |
| FR-8 | Health check | `{"status":"ok"}` |

See [`DESIGN.md`](DESIGN.md) for the full design document, data model, and detailed test scenarios.

## Environment variables

See [`.env.example`](.env.example) for all keys and defaults. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://chess:chess@localhost:5432/chess_mvp` | PostgreSQL connection |
| `APP_PORT` | `8000` | Port inside container |
| `APP_PORT` (compose override) | `8010` | Host-mapped port |

## Deployment

See [`DEPLOY.md`](DEPLOY.md) for full Docker deployment instructions, healthchecks, migrations, and local dev setup.
