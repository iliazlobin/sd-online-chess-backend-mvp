# Online Chess MVP — Architectural Design

> **Contract:** This document is the source of truth for the implementation phase.
> The acceptance suite in `verify/acceptance/` is the FIXED contract — the system
> must pass every case. When this document and an acceptance test conflict, the
> acceptance test wins.

## 1. Architecture Overview

A single FastAPI service handles both REST (HTTP) and WebSocket connections. The
server is authoritative for all game logic — clients send move intents; the server
validates, applies, persists, and broadcasts results.

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

**Key principle:** The FastAPI process owns all active-game state in memory.
python-chess `Board` objects live inside the `GameManager`. PostgreSQL is the
durable store — every move is persisted, and on restart games reload from DB.

## 2. API Contracts

### 2.1 REST Endpoints

| Method | Path | Auth | Request Body | Success | Errors |
|--------|------|------|-------------|---------|--------|
| `POST` | `/players` | none | `{}` or `{"username": "alice"}` | `201 {"player_id": "<uuid>", "token": "<uuid4>"}` | `409` duplicate username |
| `POST` | `/matchmaking` | `Bearer <token>` | `{}` | `200 {"status": "waiting"}` or `202 {"game_id": "<uuid>", "ws_url": "ws://host/games/<uuid>"}` | `403` invalid token |
| `GET` | `/games/{game_id}` | `Bearer <token>` | — | `200 {"game_id": "<uuid>", "fen": "...", "status": "active", "players": {"white": "<id>", "black": "<id>"}, "moves": [...]}` | `404` not found, `403` invalid token |
| `GET` | `/players/{player_id}/games` | `Bearer <token>` | — | `200 {"games": [{"game_id": "<uuid>", "opponent": "<id>", "result": "1-0", "date": "..."}]}` | `200` (empty list if none) |
| `GET` | `/healthz` | none | — | `200 {"status": "ok"}` | `503` if DB down |

**Matchmaking idempotency:** If a player already in the queue POSTs again and a
match has been found, return `202` with the matched `game_id` (don't create a
duplicate entry). This is tested explicitly in `test_fr2_matchmaking_matched`.

**Auth middleware:** Extract `Authorization: Bearer <token>` header. Look up
player by token in the `players` table. If missing/invalid, return `403`.
WebSocket connections also authenticate via `?token=<uuid>` query parameter —
invalid/missing token returns HTTP `403` at the upgrade handshake (not a
WebSocket close code; the acceptance tests assert HTTP 403).

### 2.2 WebSocket Protocol (`ws://host/games/{game_id}?token=<token>`)

All messages are JSON-encoded, one object per frame.

**Client → Server:**

```json
{"type": "move", "from": "e2", "to": "e4"}
{"type": "move", "from": "e7", "to": "e8", "promotion": "q"}
{"type": "resign"}
```

**Server → Client:**

```json
// Sent on connect — the current board + player identity
{"type": "game_state", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
 "your_color": "white", "players": {"white": "<uuid>", "black": "<uuid>"}}

// Sent to BOTH players after a legal move
{"type": "move_made", "fen": "...", "legal_next_moves": 20}

// Sent to the player who attempted an invalid move (board unchanged)
{"type": "error", "code": "ILLEGAL_MOVE"}
{"type": "error", "code": "NOT_YOUR_TURN"}

// Sent to the connecting player; also sent to the already-connected
// player when the opponent joins
{"type": "opponent_connected"}
{"type": "opponent_disconnected"}

// Sent to BOTH players when the game ends (checkmate, stalemate, resignation)
{"type": "game_over", "result": "White wins by resignation"}
{"type": "game_over", "result": "White wins by checkmate"}
{"type": "game_over", "result": "Black wins by checkmate"}
{"type": "game_over", "result": "Draw by stalemate"}
```

**Connection lifecycle events (derived from acceptance tests):**

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
| `NOT_YOUR_TURN` | Player tried to move out of turn | Black moves on move 1 |

**WebSocket close behavior:** On disconnect, the server sends `opponent_disconnected`
to the remaining player. The game remains active — the opponent can reconnect
and resume.

## 3. Data Model

All tables live in PostgreSQL. Migrations managed by Alembic (sole schema owner).

```sql
-- One row per registered player. Token doubles as bearer credential.
CREATE TABLE players (
    player_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token       TEXT NOT NULL UNIQUE DEFAULT gen_random_uuid()::text,
    username    TEXT UNIQUE,              -- optional, NULL if anonymous
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per game. FEN is the authoritative board state.
-- Result codes: "1-0" (white wins), "0-1" (black wins), "½-½" (draw).
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

## 4. Module Layout

Follows the `src/<pkg>/` layout per System-Design MVP Standards. Package name:
`chess_mvp`. Three-layer separation: routers (HTTP) → services (business logic) →
models (ORM).

```
sd-online-chess-backend-mvp-v2026.07.02.1/
├── src/chess_mvp/
│   ├── __init__.py
│   ├── main.py                  # create_app() factory, lifespan, /healthz, WS mount
│   ├── config.py                # pydantic-settings: DATABASE_URL, APP_PORT, etc.
│   ├── database.py              # async engine, sessionmaker, get_session dependency
│   ├── auth.py                  # get_current_player dependency (Bearer token)
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── player.py            # Player model
│   │   ├── game.py              # Game model
│   │   └── move.py              # Move model
│   │
│   ├── schemas/                 # Pydantic request/response DTOs
│   │   ├── __init__.py
│   │   ├── player.py            # PlayerCreate, PlayerResponse
│   │   ├── game.py              # GameResponse, GameSummary
│   │   └── matchmaking.py       # MatchmakingResponse
│   │
│   ├── routers/                 # HTTP layer — thin, parse → call service → serialize
│   │   ├── __init__.py
│   │   ├── players.py           # POST /players
│   │   ├── games.py             # GET /games/{id}
│   │   ├── matchmaking.py       # POST /matchmaking
│   │   └── health.py            # GET /healthz
│   │
│   ├── services/                # Business logic + data access
│   │   ├── __init__.py
│   │   ├── player_service.py    # register, lookup by token
│   │   ├── game_service.py      # create game, get state, persist moves
│   │   ├── matchmaking_service.py  # queue, dequeue, match
│   │   └── chess_service.py     # python-chess wrapper: validate, apply, FEN/PGN, state detection
│   │
│   └── ws/                      # WebSocket handling
│       ├── __init__.py
│       ├── game_handler.py      # per-connection handler: recv loop, dispatch to GameManager
│       └── game_manager.py      # singleton: active games dict, broadcast, connect/disconnect
│
├── alembic/                     # Alembic migrations
│   ├── env.py
│   └── versions/
│
├── tests/                       # White-box unit/integration tests
│   ├── conftest.py
│   ├── test_chess_service.py
│   ├── test_matchmaking.py
│   ├── test_game_ws.py
│   └── test_api.py
│
├── verify/                      # Black-box acceptance (FIXED CONTRACT)
│   └── acceptance/
│       ├── test_fr1_register.py
│       ├── test_fr2_matchmaking.py
│       ├── test_fr3_connect.py
│       ├── test_fr4_move.py
│       ├── test_fr4_checkmate.py
│       ├── test_fr4_stalemate.py
│       ├── test_fr5_resign.py
│       ├── test_fr6_get_game.py
│       ├── test_fr7_list_games.py
│       └── test_fr8_healthz.py
│
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── .env.example
└── .gitignore
```

## 5. Data Flow

### 5.1 Matchmaking Flow

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
   |                                              |
   |-- POST /matchmaking ->|  (player_A re-checks) |
   |                       |-- finds game exists   |
   |<-- 202 {game_id} -----|                       |
```

### 5.2 Game Move Flow

```
Player A (white, ws1)       GameManager          Player B (black, ws2)      PostgreSQL
      |                         |                       |                       |
      |-- {"move":"e2e4"} ---->|                       |                       |
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

### 5.3 WebSocket Connection Lifecycle

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

## 6. Key Design Decisions

### 6.1 In-Memory GameManager (not Redis)

**Decision:** Active games and WebSocket connections live in a process-local
`GameManager` singleton (a dict of `game_id → GameState` with `asyncio.Lock`
per game).

**Pro:**
- Zero network hops for move validation/broadcast — every move is a local dict
  lookup + `asyncio.Event` broadcast.
- No Redis dependency — simpler stack, fewer failure modes for MVP.
- python-chess `Board` objects are cheap to keep in memory.

**Con:**
- Single process only — horizontal scaling requires sticky sessions or a
  message bus. Acceptable for MVP (one app instance).
- Process restart loses active connections (but game state reloads from DB).

**Rationale:** Lichess uses in-process game state with Redis pub/sub for
cross-node fanout. For MVP with a single app instance, the Redis layer adds
complexity without benefit. The 8 FRs don't require multi-node scaling.

**Recovery on restart:** On `lifespan` startup, load all `status='active'`
games from DB into the GameManager. Reconnected players resume from the last
persisted FEN.

### 6.2 Synchronous Matchmaking via DB Queue

**Decision:** Use the `matchmaking_queue` table as a simple FIFO. On
`POST /matchmaking`: `SELECT ... FOR UPDATE SKIP LOCKED` to dequeue another
waiting player atomically. If none found, insert the caller.

**Pro:**
- No distributed locking needed — Postgres handles concurrency.
- Survives app restart (queue is durable).

**Con:**
- Latency of one DB round-trip per matchmaking request (~1ms, acceptable).
- No fairness/rating — pure FIFO, matches any two players.

**Rationale:** For MVP scope (no rating), a DB-backed queue is the simplest
correct solution. Redis sorted sets would be overengineered for a 2-player
FIFO queue.

### 6.3 python-chess for All Game Logic

**Decision:** All move validation, game-end detection, FEN/PGN generation
delegated to the `python-chess` library. The `chess_service.py` module wraps
`chess.Board` and exposes async-safe methods.

**Pro:**
- Battle-tested: python-chess is used by Lichess's analysis backend.
- Covers all legal moves: castling, en passant, pawn promotion, under-promotion.
- Built-in checkmate/stalemate/insufficient-material detection.
- No native engine dependency.

**Con:**
- Pure Python — ~100μs per move validation. For two-player games this is
  negligible.

### 6.4 Token Auth (not JWT/OAuth)

**Decision:** Player registration generates a UUID4 token stored as plain text
in the `players` table. Auth middleware looks up `players WHERE token = $1`.

**Pro:**
- Zero crypto — fast DB lookup, no token expiry or refresh logic.
- Simple for MVP; clients store one opaque string.

**Con:**
- Token is bearer — if leaked, attacker can impersonate the player.
- No scoping/expiry.

**Rationale:** For MVP scope (no rating/leaderboard), the threat model is low.
A full auth system (JWT + refresh) would add complexity disproportionate to
the 8 FRs. The token can be upgraded to a hashed credential in a future
iteration.

## 7. Acceptance Criteria: FR-to-Test Mapping

| FR | Requirement | Test File | Tests |
|----|------------|-----------|-------|
| FR-1 | Register player | `test_fr1_register.py` | `test_fr1_register_player` — 201 + player_id/token<br>`test_fr1_register_duplicate_name` — 409 on dup username |
| FR-2 | Matchmaking | `test_fr2_matchmaking.py` | `test_fr2_matchmaking_waiting` — first player gets 200 waiting<br>`test_fr2_matchmaking_matched` — second triggers 202, first re-checks → same game_id |
| FR-3 | WebSocket connect | `test_fr3_connect.py` | `test_fr3_connect_authenticated` — valid token → game_state event<br>`test_fr3_connect_invalid_token` — bad token → HTTP 403 |
| FR-4 | Make a move | `test_fr4_move.py` | `test_fr4_legal_move` — e2-e4 accepted, FEN advances<br>`test_fr4_illegal_move` — e2-e5 → ILLEGAL_MOVE<br>`test_fr4_not_your_turn` — black tries first → NOT_YOUR_TURN |
| FR-4 | Checkmate | `test_fr4_checkmate.py` | `test_fr4_checkmate_scholars_mate` — Scholar's Mate → game_over 1-0 |
| FR-4 | Stalemate | `test_fr4_stalemate.py` | `test_fr4_stalemate` — fast stalemate → game_over ½-½ |
| FR-5 | Resign | `test_fr5_resign.py` | `test_fr5_resign` — black resigns → game_over White wins |
| FR-6 | Get game state | `test_fr6_get_game.py` | `test_fr6_get_game_state` — 200 with full game data<br>`test_fr6_get_game_not_found` — nonexistent → 404 |
| FR-7 | List player games | `test_fr7_list_games.py` | `test_fr7_list_player_games` — 200 with games array |
| FR-8 | Health check | `test_fr8_healthz.py` | `test_fr8_healthz` — 200, `{"status": "ok"}` |

**Total: 10 test files, 15 test functions, covering 8 functional requirements.
All tests are black-box — HTTP/WebSocket only, no `import chess_mvp`.**

## 8. Implementation Notes for Engineers

### Tier: staff-engineer tasks
- `src/chess_mvp/services/chess_service.py` — python-chess wrapper: validate moves, detect checkmate/stalemate, generate FEN/PGN. Must handle all legal moves (castling, en passant, pawn promotion including under-promotion).
- `src/chess_mvp/ws/game_manager.py` — In-memory registry with `asyncio.Lock` per game, connection map, broadcast logic. Must be importable as a singleton.
- `src/chess_mvp/services/game_service.py` — Transactional move persistence: INSERT into `moves` + UPDATE `games` (fen, pgn, status, result, finished_at) in one DB transaction.
- `src/chess_mvp/models/` — SQLAlchemy ORM models matching §3 exactly.
- `alembic/versions/` — Initial migration creating all 4 tables.
- `src/chess_mvp/auth.py` — `get_current_player` FastAPI dependency: extract Bearer token, query DB, raise `HTTPException(403)` on miss.

### Tier: senior-engineer tasks
- `src/chess_mvp/main.py` — App factory `create_app()`, lifespan (init DB pool + GameManager reload), `/healthz`, mount routers + WS route.
- `src/chess_mvp/config.py` — `pydantic-settings` with `DATABASE_URL`, `APP_PORT`.
- `src/chess_mvp/database.py` — async SQLAlchemy engine, `get_session` dependency.
- `src/chess_mvp/routers/*` — Thin HTTP handlers: parse, validate, call service, return response.
- `src/chess_mvp/schemas/*` — Pydantic request/response models.
- `src/chess_mvp/ws/game_handler.py` — WebSocket endpoint: auth token from query param, connect to GameManager, recv/send loop.
- `pyproject.toml` — Dependencies: fastapi, uvicorn[standard], asyncpg, sqlalchemy[asyncio], python-chess, alembic, pydantic-settings. Dev: pytest, pytest-asyncio, httpx, websockets.
- `Dockerfile` — Multi-stage: builder installs into venv, runtime copies venv.
- `docker-compose.yml` — Services: `db` (postgres:16-alpine), `app` (build: .). `APP_PORT` override. Healthchecks on both.
- `tests/` — White-box unit/integration tests importing `chess_mvp`.
