"""Skeleton test: verify app can be imported and health endpoint exists."""

from __future__ import annotations

from chess_mvp.main import create_app


def test_app_imports():
    """App factory can be imported and invoked."""
    app = create_app()
    assert app.title == "Online Chess MVP"


def test_health_route_registered():
    """Health route is registered."""
    app = create_app()
    # Check openapi routes for /healthz
    paths = list(app.openapi().get("paths", {}).keys())
    assert "/healthz" in paths, f"/healthz not in paths: {paths}"
