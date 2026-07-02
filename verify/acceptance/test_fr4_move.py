"""FR-4 — Make a move.

Send {"type": "move", "from": "e2", "to": "e4"} over WebSocket →
{"type": "move_made", "fen": "...", "legal_next_moves": N}.
Illegal move → {"type": "error", "code": "ILLEGAL_MOVE"}.
"""

import json
import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")
WS_BASE_URL = API_BASE_URL.replace("http://", "ws://")


async def _setup_matched_game():
    """Register two players, match them, return (t1, t2, game_id)."""
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
        r1 = await client.post("/players")
        r2 = await client.post("/players")
        t1, t2 = r1.json()["token"], r2.json()["token"]

        await client.post("/matchmaking", headers={"Authorization": f"Bearer {t1}"})
        mr = await client.post("/matchmaking", headers={"Authorization": f"Bearer {t2}"})
        assert mr.status_code == 202
        game_id = mr.json()["game_id"]

    return t1, t2, game_id


@pytest.mark.asyncio
async def test_fr4_legal_move():
    """Make a legal move (e2-e4 as White) → move accepted, FEN advances."""
    import websockets

    t1, t2, game_id = await _setup_matched_game()

    # Connect both players
    ws_url1 = f"{WS_BASE_URL}/games/{game_id}?token={t1}"
    ws_url2 = f"{WS_BASE_URL}/games/{game_id}?token={t2}"

    async with (
        websockets.connect(ws_url1) as ws1,
        websockets.connect(ws_url2) as ws2,
    ):
        # Both receive game_state
        await ws1.recv()
        state = json.loads(await ws2.recv())
        assert state["type"] == "game_state"

        # Player 1 gets: opponent_disconnected (sent when P1 connected)
        # then opponent_connected (sent when P2's handler runs)
        await ws1.recv()  # opponent_disconnected
        await ws1.recv()  # opponent_connected

        # Player 2: no extra messages beyond game_state

        # Send a legal move as white (ws1)
        move_payload = {"type": "move", "from": "e2", "to": "e4"}
        await ws1.send(json.dumps(move_payload))

        response_data = json.loads(await ws1.recv())
        assert response_data["type"] == "move_made", f"Expected move_made, got {response_data}"
        assert "fen" in response_data
        # FEN should have advanced (should not be the starting position)
        assert response_data["fen"] != "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.mark.asyncio
async def test_fr4_illegal_move():
    """Make an illegal move (e2-e5) → error: ILLEGAL_MOVE."""
    import websockets

    t1, t2, game_id = await _setup_matched_game()

    ws_url1 = f"{WS_BASE_URL}/games/{game_id}?token={t1}"
    ws_url2 = f"{WS_BASE_URL}/games/{game_id}?token={t2}"

    async with (
        websockets.connect(ws_url1) as ws1,
        websockets.connect(ws_url2) as ws2,
    ):
        await ws1.recv()  # game_state
        await ws2.recv()  # game_state
        await ws1.recv()  # opponent_disconnected
        await ws1.recv()  # opponent_connected

        move_payload = {"type": "move", "from": "e2", "to": "e5"}
        await ws1.send(json.dumps(move_payload))

        response_data = json.loads(await ws1.recv())
        assert response_data["type"] == "error", f"Expected error, got {response_data}"
        assert response_data["code"] == "ILLEGAL_MOVE"


@pytest.mark.asyncio
async def test_fr4_not_your_turn():
    """Black player attempts to move on White's turn → NOT_YOUR_TURN error."""
    import websockets

    t1, t2, game_id = await _setup_matched_game()

    # Connect as black player (ws2)
    ws_url2 = f"{WS_BASE_URL}/games/{game_id}?token={t2}"
    ws_url1 = f"{WS_BASE_URL}/games/{game_id}?token={t1}"

    async with (
        websockets.connect(ws_url2) as ws2,
        websockets.connect(ws_url1) as ws1,
    ):
        await ws2.recv()  # game_state (black connects first)
        await ws1.recv()  # game_state (white connects second)
        await ws2.recv()  # opponent_disconnected (sent when black connected)
        await ws2.recv()  # opponent_connected (sent when white's handler runs)

        # Black tries to move first
        move_payload = {"type": "move", "from": "e7", "to": "e5"}
        await ws2.send(json.dumps(move_payload))

        response_data = json.loads(await ws2.recv())
        assert response_data["type"] == "error"
        assert response_data["code"] == "NOT_YOUR_TURN"
