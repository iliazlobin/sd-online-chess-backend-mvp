"""FR-3 — Connect to game via WebSocket.

ws://host/games/{game_id}?token=<token> → authenticated stream of game events.
Invalid/missing token → 403 HTTP rejection.
"""

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
async def test_fr3_connect_authenticated():
    """Connect with valid token → accepted, receive game state event."""
    import json

    import websockets

    t1, _t2, game_id = await _setup_matched_game()

    ws_url = f"{WS_BASE_URL}/games/{game_id}?token={t1}"
    async with websockets.connect(ws_url) as ws:
        # Should receive initial game state
        msg = await ws.recv()
        data = json.loads(msg)
        assert data["type"] == "game_state"
        assert "fen" in data
        assert "your_color" in data
        assert "players" in data


@pytest.mark.asyncio
async def test_fr3_connect_invalid_token():
    """Connect with invalid token → connection rejected with HTTP error."""
    import websockets

    game_id = "00000000-0000-0000-0000-000000000000"  # nonexistent
    ws_url = f"{WS_BASE_URL}/games/{game_id}?token=invalid-token"

    with pytest.raises(websockets.InvalidStatusCode) as exc_info:
        async with websockets.connect(ws_url):
            pass
    # Should be rejected — server returns 403 for invalid token
    assert exc_info.value.status_code == 403
