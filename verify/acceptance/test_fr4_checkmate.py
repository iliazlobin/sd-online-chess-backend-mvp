"""FR-4 — Checkmate detection.

Play a Scholar's Mate sequence → game ends by checkmate, result "1-0".
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
async def test_fr4_checkmate_scholars_mate():
    """Scholar's Mate (1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6 4.Qxf7#) → game_over with 1-0."""
    import websockets

    t1, t2, game_id = await _setup_matched_game()

    ws_url1 = f"{WS_BASE_URL}/games/{game_id}?token={t1}"
    ws_url2 = f"{WS_BASE_URL}/games/{game_id}?token={t2}"

    async with (
        websockets.connect(ws_url1) as ws1,
        websockets.connect(ws_url2) as ws2,
    ):
        # Both receive game_state
        await ws1.recv()  # game_state (white)
        await ws2.recv()  # game_state (black)
        await ws1.recv()  # opponent_disconnected
        await ws1.recv()  # opponent_connected

        # White moves first
        # Scholar's Mate sequence: alternating white/black
        moves = [
            (ws1, "e2", "e4"),  # 1. e4 (white)
            (ws2, "e7", "e5"),  # 1... e5 (black)
            (ws1, "f1", "c4"),  # 2. Bc4 (white)
            (ws2, "b8", "c6"),  # 2... Nc6 (black)
            (ws1, "d1", "h5"),  # 3. Qh5 (white)
            (ws2, "g8", "f6"),  # 3... Nf6 (black)
            (ws1, "h5", "f7"),  # 4. Qxf7# (white, checkmate)
        ]

        for ws, from_sq, to_sq in moves:
            await ws.send(json.dumps({"type": "move", "from": from_sq, "to": to_sq}))
            resp = json.loads(await ws.recv())
            # All moves except the last should be move_made
            if (ws, from_sq, to_sq) != moves[-1]:
                assert (
                    resp["type"] == "move_made"
                ), f"Expected move_made for {from_sq}-{to_sq}, got {resp}"
            else:
                # Last move delivers checkmate → game_over
                assert resp["type"] == "game_over", f"Expected game_over after Qxf7#, got {resp}"
                assert "1-0" in resp.get(
                    "result", ""
                ), f"Expected White wins (1-0), got result={resp.get('result')}"
