"""FR-4 — Stalemate detection.

Reach a stalemate position → game ends in draw "½-½".
Uses a known fast stalemate sequence (10 moves): the black king
is not in check but has no legal moves, so the game is drawn.
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
async def test_fr4_stalemate():
    """Fast stalemate sequence → game_over with result "½-½".

    Sequence (one of the fastest known stalemates, 10 moves / 19 ply):
      1.e3 a5  2.Qh5 Ra6  3.Qxa5 h5  4.Qxc7 Rah6
      5.h4 f6  6.Qxd7+ Kf7  7.Qxb7 Qd3  8.Qxb8 Qh7
      9.Qxc8 Kg6  10.Qe6 (stalemate — Black to move, not in check, no legal moves)
    """
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

        # Stalemate sequence — alternating white (ws1) then black (ws2)
        moves = [
            (ws1, "e2", "e3"),  # 1. e3
            (ws2, "a7", "a5"),  # 1... a5
            (ws1, "d1", "h5"),  # 2. Qh5
            (ws2, "a8", "a6"),  # 2... Ra6
            (ws1, "h5", "a5"),  # 3. Qxa5
            (ws2, "h7", "h5"),  # 3... h5
            (ws1, "a5", "c7"),  # 4. Qxc7
            (ws2, "a6", "h6"),  # 4... Rah6
            (ws1, "h2", "h4"),  # 5. h4
            (ws2, "f7", "f6"),  # 5... f6
            (ws1, "c7", "d7"),  # 6. Qxd7+
            (ws2, "e8", "f7"),  # 6... Kf7
            (ws1, "d7", "b7"),  # 7. Qxb7
            (ws2, "d8", "d3"),  # 7... Qd3
            (ws1, "b7", "b8"),  # 8. Qxb8
            (ws2, "d3", "h7"),  # 8... Qh7
            (ws1, "b8", "c8"),  # 9. Qxc8
            (ws2, "f7", "g6"),  # 9... Kg6
            (ws1, "c8", "e6"),  # 10. Qe6 — stalemate!
        ]

        for i, (ws, from_sq, to_sq) in enumerate(moves):
            await ws.send(json.dumps({"type": "move", "from": from_sq, "to": to_sq}))
            resp = json.loads(await ws.recv())

            is_last = i == len(moves) - 1
            if not is_last:
                assert resp["type"] == "move_made", (
                    f"Move {i + 1} ({from_sq}-{to_sq}): expected move_made, got {resp}"
                )
            else:
                # Last move triggers stalemate → game_over with draw
                assert resp["type"] == "game_over", (
                    f"Final move: expected game_over (stalemate), got {resp}"
                )
                result = resp.get("result", "")
                assert "½-½" in result or "1/2-1/2" in result or "draw" in result.lower(), (
                    f"Expected draw result, got {result}"
                )
