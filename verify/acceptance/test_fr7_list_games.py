"""FR-7 — List player games.

GET /players/{id}/games → 200 {games: [{game_id, opponent, result, date}]}.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)


def test_fr7_list_player_games(client):
    """List a player's games → 200 with game list."""
    # Register and match two players to create at least one game
    r1 = client.post("/players")
    r2 = client.post("/players")
    p1_id, t1 = r1.json()["player_id"], r1.json()["token"]
    t2 = r2.json()["token"]

    client.post("/matchmaking", headers={"Authorization": f"Bearer {t1}"})
    mr = client.post("/matchmaking", headers={"Authorization": f"Bearer {t2}"})
    assert mr.status_code == 202

    resp = client.get(
        f"/players/{p1_id}/games",
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "games" in data
    assert isinstance(data["games"], list)
    # Game list fetched successfully (may be empty if no finished games)
