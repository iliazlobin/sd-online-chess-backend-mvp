# Online Chess — MVP Spec

## 1. Goal & scope

Build a real-time two-player chess game server where players can register, find an opponent, and play a full game with legal move validation via WebSocket.

**In scope**
- Player registration (POST /players)
- Simple matchmaking — request a game via API, get matched to an available opponent
- Real-time chess game play over WebSocket (ws://host/games/{game_id})
- Server-authoritative move validation (all legal moves: piece movement, capture, castling, en passant, pawn promotion)
- Check, checkmate, and stalemate detection
- Game result (White wins / Black wins / Draw) with resignation support
- Game state persistence in PostgreSQL
- Player game history (GET /players/{id}/games)

**Out of scope**
- Rating / Glicko-2 / leaderboard
- Tournaments
- Game replay
- Anti-cheat engine
- Correspondence chess
- Spectator mode
- AI opponent

## 2. Functional requirements

- **FR-1 — Register player.** `POST /players` (empty body) → `201` with `{player_id, token}`. Error (duplicate name if provided) → `409`.
- **FR-2 — Create matchmaking request.** `POST /matchmaking` (header `Authorization: Bearer <token>`) → `202 {game_id, ws_url}` when a match is found; `200 {status: "waiting"}` if no opponent yet.
- **FR-3 — Connect to game.** WebSocket `ws://host/games/{game_id}?token=<token>` → authenticated stream of game events. Invalid/missing token → `4001` close.
- **FR-4 — Make a move.** Send `{"type": "move", "from": "e2", "to": "e4"}` over WebSocket → `{"type": "move_made", "fen": "...", "legal_next_moves": N}`. Illegal move → `{"type": "error", "code": "ILLEGAL_MOVE"}`.
- **FR-5 — Resign.** Send `{"type": "resign"}` → `{"type": "game_over", "result": "White wins by resignation"}`.
- **FR-6 — Get game state.** `GET /games/{game_id}` (header `Authorization: Bearer <token>`) → `200 {game_id, fen, status, players, moves[]}`. Not found → `404`.
- **FR-7 — List player games.** `GET /players/{id}/games` → `200 {games: [{game_id, opponent, result, date}]}`.
- **FR-8 — Heartbeat.** `GET /healthz` → `200 OK`.

## 3. Stack & deployment

- **Runtime:** Python 3.12, FastAPI, WebSocket (via Starlette)
- **Datastore:** PostgreSQL (via asyncpg + Alembic migrations)
- **Chess logic:** python-chess library (pure Python, no engine needed)
- **Auth:** simple bearer tokens (UUID-based, no OAuth for MVP)
- **Tests:** pytest, pytest-asyncio, websockets test client
- **Container:** multi-stage Docker build, Caddy reverse proxy
- **Port:** 8001 (mapped to hermes-stg1.iliazlobin.com)
- **Design →** [System Design: Online Chess](https://www.notion.so/38fd865005a881e6b638d328a41171cb)
- **Board →** projects

## 4. Data model

```sql
Player {
  player_id:      uuid  PK          ← generated on registration
  token:          text              ← bearer token (UUID4), unique
  created_at:     timestamptz       ← auto
  username:       text              ← optional, unique
}

Game {
  game_id:        uuid  PK
  white_player:   uuid  FK → Player
  black_player:   uuid  FK → Player
  status:         text              ← waiting / active / finished
  result:         text              ← empty / "1-0" / "0-1" / "½-½"
  fen:            text              ← current board as FEN string
  pgn:            text              ← full game in PGN format
  created_at:     timestamptz       ← auto
  finished_at:    timestamptz       ← nullable

  finished:       bool              ← denormalized: status = finished
  winner:         text              ← "white" / "black" / null
  termination:    text              ← "checkmate" / "stalemate" / "resignation" / null
}

Move {
  move_id:        bigint  PK
  game_id:        uuid  FK → Game
  player_id:      uuid  FK → Player
  move_number:    int               ← half-move counter (ply)
  from_square:    text              ← e.g. "e2"
  to_square:      text              ← e.g. "e4"
  promotion:      text              ← nullable: piece type if promotion
  fen_before:     text              ← board state before this move
  fen_after:      text              ← board state after this move
  created_at:     timestamptz       ← auto
}

MatchmakingQueue {
  player_id:      uuid  PK
  joined_at:      timestamptz
}
```

## 5. API

- `POST /players` — register a new player, returns player_id + bearer token
- `POST /matchmaking` — enter (or find) matchmaking queue
- `ws://host/games/{game_id}` — WebSocket game connection
- `GET /games/{game_id}` — get game state and move history
- `GET /players/{id}/games` — list player's completed games
- `GET /healthz` — health check

## 6. Test scenarios

- Register two players → both get unique tokens and player_ids
- Matchmaking: first player waits, second player triggers match → both get the same game_id
- Legal move: make `e2-e4` as white → move accepted, FEN advances, black's turn
- Illegal move: try `e2-e5` → error: `ILLEGAL_MOVE`, board unchanged
- Checkmate: play a Scholar's Mate sequence → game ends, result set
- Resignation: player resigns mid-game → game over, opponent wins
- Invalid token on WebSocket → connection rejected with 4001
- Get game state after 3 moves → FEN matches, 3 moves in history
- Player attempts opponent's move → error: `NOT_YOUR_TURN`
- Stalemate: reach a stalemate position → game ends in draw `½-½`

## 7. Module layout

```
sd-online-chess-mvp/
├── app/
│   ├── __init__.py
│   ├── main.py              ← FastAPI app, WebSocket routes, /healthz
│   ├── models.py            ← Pydantic/SQLAlchemy models (Player, Game, Move)
│   ├── chess_engine.py      ← python-chess wrapper: validate, apply moves, detect game-end
│   ├── game_manager.py      ← in-memory active-games registry + WebSocket connection map
│   ├── matchmaking.py       ← simple queue: find or wait for opponent
│   ├── db.py                ← asyncpg pool + queries
│   └── auth.py              ← bearer token lookup middleware
├── alembic/                 ← migrations
│   └── versions/
├── tests/
│   ├── test_matchmaking.py
│   ├── test_game_ws.py      ← WebSocket integration tests with real chess moves
│   ├── test_chess_engine.py ← unit tests for move validation, checkmate, stalemate
│   └── test_api.py          ← REST endpoint tests
├── verify/
│   └── acceptance/          ← black-box acceptance (one per FR)
│       ├── test_fr1_register.py
│       ├── test_fr2_matchmaking.py
│       ├── test_fr3_connect.py
│       ├── test_fr4_move.py
│       ├── test_fr5_resign.py
│       ├── test_fr6_get_game.py
│       ├── test_fr7_list_games.py
│       └── test_fr8_healthz.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── alembic.ini
└── SPEC.md
```

## 8. Run

```bash
# Start with Docker Compose (PostgreSQL + app)
docker compose up --build

# Health check
curl http://localhost:8001/healthz

# Run tests
pytest tests/ verify/acceptance/ -v

# Run lint
ruff check .
```
