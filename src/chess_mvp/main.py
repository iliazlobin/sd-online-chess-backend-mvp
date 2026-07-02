from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from chess_mvp.database import dispose_engine
from chess_mvp.routers import games, health, matchmaking, players


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: manage DB pool lifecycle.

    Alembic OWNS the schema — no create_all() here.
    """
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    """Build the FastAPI application instance."""
    app = FastAPI(
        title="Online Chess MVP",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- REST routers ---
    app.include_router(health.router)
    app.include_router(players.router)
    app.include_router(matchmaking.router)
    app.include_router(games.router)

    return app


app = create_app()
