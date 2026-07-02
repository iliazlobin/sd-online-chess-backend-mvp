"""FR-1 — Register player.

POST /players (empty body) → 201 with {player_id, token}.
Duplicate name → 409.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)


def test_fr1_register_player(client):
    """Register a new player → 201 with player_id and token."""
    resp = client.post("/players")
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "player_id" in data
    assert "token" in data


def test_fr1_register_duplicate_name(client):
    """Register with duplicate username → 409."""
    import uuid
    unique_name = f"player_{uuid.uuid4().hex[:8]}"

    # First, register a player with a name
    resp1 = client.post("/players", json={"username": unique_name})
    assert resp1.status_code == 201

    # Attempt duplicate
    resp2 = client.post("/players", json={"username": unique_name})
    assert resp2.status_code == 409, (
        f"Expected 409 for duplicate, got {resp2.status_code}: {resp2.text}"
    )
