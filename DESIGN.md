# Online Chess — Backend MVP Design

> **Build:** sd-online-chess-backend-mvp-v2026.07.02.1
> **Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · python-chess
> **Acceptance suite:** `verify/acceptance/` (black-box, 10 files, 16 tests) — the fixed contract for the MVP.

---

## 1. Goals & scope

Build a real-time two-player chess game server where players register, find an opponent via declarative matchmaking, and play a full legal-move-validated game over WebSocket.

### In scope

- Player registration (`POST /players`)
- Simple matchmaking — request a game via API, get matched to an available opponent
- Real-time chess gameplay over WebSocket (`ws://host/games/{game_id}`)
- Server-authoritative move validation (all legal moves: piece movement, capture, castling, en passant, pawn promotion including under-promotion)
- Check, checkmate, and stalemate detection
- Game result (White wins / Black wins / Draw) with resignation support
- Game state persistence in PostgreSQL
- Player game history (`GET /players/{id}/games`)

### Out of scope

- Rating / Glicko-2 / leaderboard
- Tournaments
- Game replay
- Anti-cheat engine
- Correspondence chess
- Spectator mode
- AI opponent
- Multi-node scaling / Redis pub/sub

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Client (Browser)                   │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  White tab   │  │  Black tab   │                 │
│  │  ws://...    │  │  ws://...    │                 │
│  └──────┬───────┘  └──────┬───────┘                 │
└─────────┼─────────────────┼──────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Service                     │
│                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │ REST     │  │  WebSocket   │  │  GameManager  │ │
│  │ routers  │  │  handlers    │  │  (in-memory)  │ │
│  └────┬─────┘  └──────┬───────┘  └───────┬───────┘ │
│       │               │                   │         │
│       ▼               ▼                   ▼         │
│  ┌──────────────────────────────────────────────┐   │
│  │              Service Layer                    │   │
│  │  player_service | game_service | chess_svc   │   │
│  │  matchmaking_service                         │   │
│  └──────────────────────┬───────────────────────┘   │
│                         │                           │
│                         ▼                           │
│  ┌──────────────────────────────────────────────┐   │
│  │              PostgreSQL (asyncpg)             │   │
│  │  players | games | moves | matchmaking_queue │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Key principle:** The FastAPI process owns all active-game state in memory. `python-chess` `Board` objects live inside the `GameManager` singleton (a dict of `game_id → GameState` with per-game `asyncio.Lock`). PostgreSQL is the durable store — every move is persisted, and on restart games reload from DB.

---

## 3. API contracts

### 3.1 REST endpoints

| Method | Path | Auth | Request | Success | Errors |
|--------|------|------|---------|---------|--------|
| `POST` | `/players` | none | `{}` or `{"username": "alice"}` | `201` `{player_id, token}` | `409` duplicate username |
| `POST` | `/matchmaking` | Bearer | `{}` | `200 {status:"waiting"}` or `202 {game_id, ws_url}` | `403` invalid token |
| `GET` | `/games/{game_id}` | Bearer | — | `200 {game_id, fen, status, players, moves[]}` | `404` not found, `403` invalid token |
| `GET` | `/players/{id}/games` | Bearer | — | `200 {games: [...]}` | `403` invalid token |
| `GET` | `/healthz` | none | — | `200 {"status":"ok"}` | — |

**Auth middleware:** Extract `Authorization: Bearer *** Look up player by token in the `players` table. If missing/invalid, return `403`. WebSocket connections authenticate via `?token=<uuid>` query parameter — invalid/missing token returns HTTP `403` at the upgrade handshake.

### 3.2 WebSocket protocol (`ws://host/games/{game_id}?token=<token>`)

All messages are JSON-encoded, one object per frame.

**Client → Server:**

```json
{"type": "move", "from": "e2", "to": "e4"}
{"type": "move", "from": "e7", "to": "e8", "promotion": "q"}
{"type": "resign"}
```

**Server → Client:**

```json
// On connect — the current board + player identity
{
  "type": "game_state",
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  "your_color": "white",
  "players": {"white": "<uuid>", "black": "<uuid>"}
}

// After a legal move (sent to the moving player only)
{
  "type": "move_made",
  "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
  "legal_next_moves": 30
}

// On invalid move (sent to the sender only)
{"type": "error", "code": "ILLEGAL_MOVE"}
{"type": "error", "code": "NOT_YOUR_TURN"}

// Connection lifecycle (sent to affected player)
{"type": "opponent_connected"}
{"type": "opponent_disconnected"}

// Game end (broadcast to both players)
{"type": "game_over", "result": "1-0 — White wins by resignation"}
{"type": "game_over", "result": "1-0 — White wins by checkmate"}
{"type": "game_over", "result": "½-½ — Draw by stalemate"}
```

**Connection lifecycle events:**

When player A connects and player B hasn't joined yet, player A receives:
1. `game_state` (with `your_color`)
2. `opponent_disconnected`

When player B then connects:
- Player B receives `game_state`
- Player A receives `opponent_connected`

**Error codes:**

| Code | Meaning | Trigger |
|------|---------|---------|
| `ILLEGAL_MOVE` | Move violates chess rules | Pawn can't jump 3 squares, etc. |
| `NOT_YOUR_TURN` | Player moved out of turn | Black moves on move 1 |
| `GAME_OVER` | Game is already finished | Move or resign on a finished game |
| `INVALID_JSON` | Message is not valid JSON | Client sends malformed data |

---

## 4. Data model

All tables live in PostgreSQL. Migrations managed by Alembic (sole schema owner — `create_all()` is deliberately absent).

```sql
-- One row per registered player. Token doubles as bearer credential.
CREATE TABLE players (
    player_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token       TEXT NOT NULL UNIQUE DEFAULT gen_random_uuid()::text,
    username    TEXT UNIQUE,              -- optional, NULL if anonymous
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per game. FEN is the authoritative board state.
CREATE TABLE games (
    game_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    white_player    UUID NOT NULL REFERENCES players(player_id),
    black_player    UUID NOT NULL REFERENCES players(player_id),
    status          TEXT NOT NULL DEFAULT 'active',  -- active | finished
    result          TEXT,                             -- NULL until finished
    fen             TEXT NOT NULL,                    -- current board FEN
    pgn             TEXT NOT NULL DEFAULT '',         -- accumulated PGN
    termination     TEXT,              -- checkmate | stalemate | resignation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

-- Every half-move. fen_before/fen_after allow replay without replaying PGN.
CREATE TABLE moves (
    move_id     BIGSERIAL PRIMARY KEY,
    game_id     UUID NOT NULL REFERENCES games(game_id),
    player_id   UUID NOT NULL REFERENCES players(player_id),
    move_number INT NOT NULL,           -- ply counter (1, 2, 3...)
    from_square TEXT NOT NULL,          -- algebraic: "e2"
    to_square   TEXT NOT NULL,          -- algebraic: "e4"
    promotion   TEXT,                   -- "q"|"r"|"b"|"n" or NULL
    fen_before  TEXT NOT NULL,
    fen_after   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lightweight queue for matchmaking. Rows deleted once a match is formed.
CREATE TABLE matchmaking_queue (
    player_id   UUID PRIMARY KEY REFERENCES players(player_id),
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Design notes:**
- `games.pgn` accumulates the full game in standard PGN format (built by `python-chess`).
- `games.fen` is the live position — updated on every move.
- `games.termination` records *how* the game ended (checkmate/stalemate/resignation).
- `moves.move_number` is the ply (1 = White's first, 2 = Black's first, etc.).
- `matchmaking_queue` uses `player_id` as PK — a player can only be in the queue once.

---

## 5. Module layout

```
src/chess_mvp/
├── __init__.py
├── main.py                  # create_app() factory, lifespan, /healthz, WS mount
├── config.py                # pydantic-settings: DATABASE_URL, APP_PORT, etc.
├── database.py              # async engine, sessionmaker, get_session dependency
├── auth.py                  # get_current_player dependency (Bearer token)
│
├── models/                  # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── player.py            # Player model
│   ├── game.py              # Game model (with moves relationship)
│   ├── move.py              # Move model
│   └── matchmaking_queue.py # MatchmakingQueue model
│
├── schemas/                 # Pydantic request/response DTOs
│   ├── __init__.py
│   ├── player.py            # PlayerCreate, PlayerResponse
│   ├── game.py              # GameResponse, GameSummary
│   └── matchmaking.py       # MatchmakingResponse
│
├── routers/                 # HTTP layer — thin, parse → call service → serialize
│   ├── __init__.py
│   ├── players.py           # POST /players
│   ├── games.py             # GET /games/{id}, GET /players/{id}/games
│   ├── matchmaking.py       # POST /matchmaking
│   └── health.py            # GET /healthz
│
├── services/                # Business logic + data access
│   ├── __init__.py
│   ├── player_service.py    # register, lookup by token
│   ├── game_service.py      # create game, get state, persist moves
│   ├── matchmaking_service.py  # queue, dequeue, match (FOR UPDATE SKIP LOCKED)
│   └── chess_service.py     # python-chess wrapper: validate, apply, FEN/PGN, game-end
│
└── ws/                      # WebSocket handling
    ├── __init__.py
    ├── game_handler.py      # per-connection handler: recv loop, dispatch to GameManager
    └── game_manager.py      # singleton: active games dict, broadcast, connect/disconnect

alembic/                     # Schema migrations
├── env.py
└── versions/
    └── 001_initial_schema.py  # Creates all 4 tables

tests/                       # White-box unit/integration tests
├── conftest.py
├── test_skeleton.py         # App factory import + route registration

verify/acceptance/           # Black-box acceptance (FIXED CONTRACT)
├── test_fr1_register.py     # FR-1: Register player
├── test_fr2_matchmaking.py  # FR-2: Matchmaking
├── test_fr3_connect.py      # FR-3: WebSocket connect
├── test_fr4_move.py         # FR-4: Legal/illegal/turn moves
├── test_fr4_checkmate.py    # FR-4: Scholar's Mate checkmate
├── test_fr4_stalemate.py    # FR-4: Stalemate detection
├── test_fr5_resign.py       # FR-5: Resignation
├── test_fr6_get_game.py     # FR-6: Get game state
├── test_fr7_list_games.py   # FR-7: List player games
└── test_fr8_healthz.py      # FR-8: Health check

pyproject.toml               # Dependencies + tool config
Dockerfile                   # Multi-stage: python:3.12-slim
docker-compose.yml           # db (postgres:16-alpine) + app
alembic.ini                  # Alembic config
.env.example                 # Environment template
.gitignore
.dockerignore
```

---

## 6. Data flows

### 6.1 Matchmaking flow

```
Player A                Server                  Player B
   |                      |                        |
   |-- POST /matchmaking ->|                        |
   |   (Bearer token_A)   |                        |
   |                       |-- SELECT matchmaking   |
   |                       |   queue → empty        |
   |                       |-- INSERT player_A      |
   |<-- 200 {waiting} -----|   into queue           |
   |                       |                        |
   |                       |<-- POST /matchmaking --|
   |                       |   (Bearer token_B)     |
   |                       |-- SELECT queue →       |
   |                       |   player_A waiting     |
   |                       |-- DELETE from queue    |
   |                       |-- INSERT game row      |
   |                       |-- CREATE GameManager   |
   |                       |   entry                |
   |                       |                        |
   |                       |-- 202 {game_id} ------>|
   |                       |                        |
   |-- POST /matchmaking ->|  (player_A re-checks)  |
   |                       |-- finds game exists   |
   |<-- 202 {game_id} -----|                       |
```

**Idempotency:** If a player already in a matched game POSTs matchmaking again, the service detects the existing active game and returns `202` with the same `game_id`. This is tested explicitly in `test_fr2_matchmaking_matched`.

### 6.2 Game move flow

```
Player A (white, ws1)       GameManager          Player B (black, ws2)      PostgreSQL
      |                         |                       |                       |
      |-- {"move", e2,e4} ---->|                       |                       |
      |                         |-- validate (python-   |                       |
      |                         |   chess Board)        |                       |
      |                         |-- illegal? → error    |                       |
      |                         |-- legal: push move    |                       |
      |                         |   to board            |                       |
      |                         |-- check game-end      |                       |
      |                         |   (checkmate/stale-   |                       |
      |                         |    mate)              |                       |
      |                         |                       |                       |
      |                         |------ INSERT move --->|                       |
      |                         |------ UPDATE game --->|                       |
      |                         |   (fen, pgn, status)  |                       |
      |                         |                       |                       |
      |<-- {"move_made", fen} --|                       |                       |
      |                         |-- {"move_made", fen} ->|                      |
      |                         |                       |                       |
      |                         |  (if game over:)      |                       |
      |<-- {"game_over", ...} --|                       |                       |
      |                         |-- {"game_over", ...} ->|                      |
```

### 6.3 WebSocket connection lifecycle

```
Player A (white)         GameManager            Player B (black)
      |                      |                       |
      |--- WS connect ------>|                       |
      |   ?token=tk_A       |                       |
      |                      |-- auth: lookup token  |
      |                      |-- register connection |
      |                      |   in game's conn map  |
      |                      |-- load/replay Board   |
      |<-- game_state -------|                       |
      |<-- opponent_disc. ---|  (B not connected)    |
      |                      |                       |
      |                      |<--- WS connect -------|
      |                      |    ?token=tk_B        |
      |                      |-- auth + register     |
      |                      |-- B: send game_state  |
      |                      |-- A: send opp.conn.   |
      |<-- opponent_conn. ---|                       |
      |                      |------- game_state --->|
      |                      |                       |
      |--- disconnect ------>|                       |
      |                      |-- unregister conn     |
      |                      |-- B: send opp.disc.   |
      |                      |------- opp.disc. ---->|
```

On disconnect, the game remains active — the opponent can reconnect and resume from the last persisted FEN.

---

## 7. Key design decisions

### 7.1 In-memory GameManager (not Redis)

**Decision:** Active games and WebSocket connections live in a process-local `GameManager` singleton (a dict of `game_id → GameState` with `asyncio.Lock` per game).

**Pro:**
- Zero network hops for move validation/broadcast — every move is a local dict lookup + `asyncio.Event` broadcast.
- No Redis dependency — simpler stack, fewer failure modes for MVP.
- `python-chess` `Board` objects are cheap to keep in memory (~KB each).

**Con:**
- Single process only — horizontal scaling requires sticky sessions or a message bus. Acceptable for MVP (one app instance).
- Process restart loses active connections (but game state reloads from DB).

**Rationale:** Lichess uses in-process game state with Redis pub/sub for cross-node fanout. For MVP with a single app instance, the Redis layer adds complexity without benefit. The 8 FRs don't require multi-node scaling.

**Recovery on restart:** On `lifespan` startup, previously active games load from DB into the `GameManager`. Reconnected players resume from the last persisted FEN.

### 7.2 Synchronous matchmaking via DB queue

**Decision:** Use the `matchmaking_queue` table as a simple FIFO. On `POST /matchmaking`: `SELECT ... FOR UPDATE SKIP LOCKED` to dequeue another waiting player atomically. If none found, insert the caller.

**Pro:**
- No distributed locking needed — Postgres handles concurrency.
- Survives app restart (queue is durable).
- `SKIP LOCKED` prevents head-of-line blocking when two matches arrive simultaneously.

**Con:**
- Latency of one DB round-trip per matchmaking request (~1ms, acceptable).
- No fairness/rating — pure FIFO, matches any two players.

**Rationale:** For MVP scope (no rating), a DB-backed queue is the simplest correct solution. Redis sorted sets would be overengineered for a 2-player FIFO queue.

### 7.3 python-chess for all game logic

**Decision:** All move validation, game-end detection, FEN/PGN generation delegated to the `python-chess` library. `chess_service.py` wraps `chess.Board` and exposes async-safe methods.

**Pro:**
- Battle-tested: `python-chess` is used by Lichess's analysis backend.
- Covers all legal moves: castling, en passant, pawn promotion, under-promotion.
- Built-in checkmate/stalemate/insufficient-material detection.
- No native engine dependency.

**Con:**
- Pure Python — ~100μs per move validation. For two-player games this is negligible.

### 7.4 Token auth (not JWT/OAuth)

**Decision:** Player registration generates a UUID4 token stored as plain text in the `players` table. Auth middleware looks up `players WHERE token = $1`.

**Pro:**
- Zero crypto — fast DB lookup, no token expiry or refresh logic.
- Simple for MVP; clients store one opaque string.

**Con:**
- Token is bearer — if leaked, attacker can impersonate the player.
- No scoping/expiry.

**Rationale:** For MVP scope (no rating/leaderboard), the threat model is low. A full auth system (JWT + refresh) would add complexity disproportionate to the 8 FRs. The token can be upgraded to a hashed credential in a future iteration.

### 7.5 No `create_all()` — Alembic owns the schema

**Decision:** The application code does **not** call `Base.metadata.create_all()` on startup. Alembic migrations are the sole schema owner.

**Why this matters:** When CI runs `alembic upgrade head` (the standard), an app that ALSO calls `create_all()` in its FastAPI `lifespan` creates the tables first, so the migration step then fails with `DuplicateTableError: relation "t" already exists`.

**Verification:** Both the Docker HEALTHCHECK and the functional CI workflow run migrations explicitly. The scaffold commit verified `alembic upgrade head` passes against a fresh PostgreSQL.

---

## 8. Functional requirements → acceptance test map

| FR | Requirement | Test file | Test functions | Acceptance criteria | Evidence |
|----|-------------|-----------|----------------|-------------------|----------|
| FR-1 | Register player | `test_fr1_register.py` | `test_fr1_register_player`<br>`test_fr1_register_duplicate_name` | `POST /players` → 201 with `{player_id, token}`<br>Duplicate username → 409 | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) runs all 16 acceptance tests |
| FR-2 | Matchmaking | `test_fr2_matchmaking.py` | `test_fr2_matchmaking_waiting`<br>`test_fr2_matchmaking_matched` | First player → 200 `{status:"waiting"}`<br>Second → 202 `{game_id, ws_url}` both get same game_id | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-3 | WebSocket connect | `test_fr3_connect.py` | `test_fr3_connect_authenticated`<br>`test_fr3_connect_invalid_token` | Valid token → `game_state` event<br>Invalid token → HTTP 403 | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-4 | Legal move | `test_fr4_move.py` | `test_fr4_legal_move`<br>`test_fr4_illegal_move`<br>`test_fr4_not_your_turn` | e2-e4 accepted, FEN advances<br>e2-e5 → ILLEGAL_MOVE<br>Black first move → NOT_YOUR_TURN | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-4 | Checkmate | `test_fr4_checkmate.py` | `test_fr4_checkmate_scholars_mate` | Scholar's Mate → game_over "1-0" | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-4 | Stalemate | `test_fr4_stalemate.py` | `test_fr4_stalemate` | 10-move forced stalemate → game_over "½-½" | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-5 | Resign | `test_fr5_resign.py` | `test_fr5_resign` | Black resigns → "White wins by resignation" | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-6 | Get game state | `test_fr6_get_game.py` | `test_fr6_get_game_state`<br>`test_fr6_get_game_not_found` | 200 with game data + moves[]<br>Nonexistent → 404 | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-7 | List games | `test_fr7_list_games.py` | `test_fr7_list_player_games` | 200 with games array | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |
| FR-8 | Health check | `test_fr8_healthz.py` | `test_fr8_healthz` | `GET /healthz` → `{"status":"ok"}` | [CI functional workflow](https://github.com/iliazlobin/sd-online-chess-backend-mvp/actions/workflows/functional.yml) |

**Total:** 10 test files, 16 test functions, covering all 8 functional requirements. All tests are black-box — HTTP/WebSocket only, no `import chess_mvp`.

## 9. CI pipeline

Three GitHub Actions workflows run on every push to `main` and every PR:

| Workflow | File | What it does |
|----------|------|-------------|
| **lint** | `.github/workflows/lint.yml` | `ruff check` + `ruff format --check` |
| **ci** | `.github/workflows/ci.yml` | `pip install -e ".[dev]"` → unit tests → Docker build → image smoke test |
| **functional** | `.github/workflows/functional.yml` | Compose up (Postgres + app) → `alembic upgrade head` → install test deps → run acceptance suite → teardown |

## 10. Environment & configuration

All settings loaded via `pydantic-settings` (`.env` or environment variables).

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://chess:chess@localhost:5432/chess_mvp` | PostgreSQL connection string |
| `APP_PORT` | `8000` | Port uvicorn listens on inside container |
| `DB_POOL_SIZE` | `10` | Async DB pool connections |
| `DB_MAX_IDLE_SECONDS` | `300` | Max idle before connection recycle |
| `APP_PORT` (compose override) | `8010` | Host-mapped port for `app` service |

## 11. Deployment

See [`DEPLOY.md`](DEPLOY.md) for:
- Docker Compose quick start (clone → `cp .env.example .env` → `docker compose up --build -d`)
- Port layout (only `app` publishes a host port; Postgres/Redis are compose-internal)
- Healthchecks (`pg_isready` for `db`, `curl /healthz` for `app`, container `HEALTHCHECK`)
- Manual migration commands
- Local dev without Docker

The host e2e acceptance loop (via `~/Hermes/bin/e2e-verify`) runs the full `verify/acceptance/` suite against the live system every 30 minutes and self-files fix cards on regression.
