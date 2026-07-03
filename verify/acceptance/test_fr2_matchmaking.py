"""FR-2 — Matchmaking.

POST /matchmaking (Authorization: Bearer <token>) → 202 {game_id, ws_url} when matched.
200 {status: "waiting"} if no opponent yet.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)


@pytest.fixture
def registered_player(client):
    """Register a player and return (player_id, token)."""
    resp = client.post("/players")
    assert resp.status_code == 201
    data = resp.json()
    return data["player_id"], data["token"]


def test_fr2_matchmaking_waiting(client, registered_player):
    """First player enters matchmaking → 200 with status 'waiting'."""
    _player_id, token = registered_player
    resp = client.post(
        "/matchmaking",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] == "waiting"


def test_fr2_matchmaking_matched(client):
    """Two players enter matchmaking → both get 202 with same game_id."""
    import os

    import psycopg2

    # Clean the matchmaking queue first (test isolation)
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://chess:chess@localhost:5432/chess",
    )
    # Convert async URL to sync for psycopg2
    sync_url = db_url.replace("+asyncpg", "")
    conn = psycopg2.connect(sync_url)
    conn.autocommit = True
    conn.cursor().execute("DELETE FROM matchmaking_queue")
    conn.close()

    # Register two players
    r1 = client.post("/players")
    r2 = client.post("/players")
    assert r1.status_code == 201 and r2.status_code == 201
    token1 = r1.json()["token"]
    token2 = r2.json()["token"]

    # First player waits
    resp1 = client.post(
        "/matchmaking",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "waiting"

    # Second player triggers match
    resp2 = client.post(
        "/matchmaking",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp2.status_code == 202, (
        f"Expected 202 for match, got {resp2.status_code}: {resp2.text}"
    )
    data = resp2.json()
    assert "game_id" in data
    assert "ws_url" in data

    # Now re-check first player's matchmaking
    resp3 = client.post(
        "/matchmaking",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp3.status_code == 202
    assert resp3.json()["game_id"] == data["game_id"]
