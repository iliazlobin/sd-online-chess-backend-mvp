"""FR-5 — Resign.

Send {"type": "resign"} → {"type": "game_over", "result": "White wins by resignation"}.
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
async def test_fr5_resign():
    """A player resigns → game_over event with correct result."""
    import websockets

    t1, t2, game_id = await _setup_matched_game()

    # Connect both players, then black (ws2) resigns
    ws_url1 = f"{WS_BASE_URL}/games/{game_id}?token={t1}"
    ws_url2 = f"{WS_BASE_URL}/games/{game_id}?token={t2}"

    async with (
        websockets.connect(ws_url1) as ws1,
        websockets.connect(ws_url2) as ws2,
    ):
        await ws1.recv()  # game_state (white)
        await ws2.recv()  # game_state (black)
        await ws1.recv()  # opponent_disconnected (sent when white connected alone)
        await ws1.recv()  # opponent_connected (sent when black's handler runs)

        # Black resigns
        await ws2.send(json.dumps({"type": "resign"}))
        response_data = json.loads(await ws2.recv())

        assert response_data["type"] == "game_over", (
            f"Expected game_over, got {response_data}"
        )
        # Black resigns → White wins
        assert "White wins" in response_data.get("result", "")
