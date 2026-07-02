"""FR-8 — Health check.

GET /healthz → 200 OK.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8001")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)


def test_fr8_healthz(client):
    """Health check endpoint returns 200 OK."""
    resp = client.get("/healthz")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] == "ok"
