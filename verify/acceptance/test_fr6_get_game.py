"""FR-6 — Get game state.

GET /games/{game_id} (Authorization: Bearer <token>) →
200 {game_id, fen, status, players, moves[]}.
Not found → 404.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)


def test_fr6_get_game_state(client):
    """Get a game by id → 200 with game state and moves."""
    # Register and match two players
    r1 = client.post("/players")
    r2 = client.post("/players")
    _p1_id, t1 = r1.json()["player_id"], r1.json()["token"]
    t2 = r2.json()["token"]

    client.post("/matchmaking", headers={"Authorization": f"Bearer {t1}"})
    mr = client.post("/matchmaking", headers={"Authorization": f"Bearer {t2}"})
    assert mr.status_code == 202
    game_id = mr.json()["game_id"]

    resp = client.get(
        f"/games/{game_id}",
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["game_id"] == game_id
    assert "fen" in data
    assert "status" in data
    assert "players" in data
    assert "moves" in data
    assert isinstance(data["moves"], list)


def test_fr6_get_game_not_found(client):
    """Get a nonexistent game → 404."""
    # Register a player first to get a valid token
    r = client.post("/players")
    assert r.status_code == 201
    token = r.json()["token"]

    resp = client.get(
        "/games/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
