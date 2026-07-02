from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, status
from sqlalchemy import select

from chess_mvp.database import dispose_engine, get_session_factory
from chess_mvp.models.game import Game
from chess_mvp.models.player import Player
from chess_mvp.routers import games, health, matchmaking, players
from chess_mvp.ws.game_handler import handle_game_ws


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

    # --- WebSocket route ---
    @app.websocket("/games/{game_id}")
    async def ws_game_endpoint(websocket: WebSocket, game_id: str):
        # Extract token from query params
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return

        # Validate token
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Player).where(Player.token == token))
            player = result.scalar_one_or_none()

        if player is None:
            # Reject the upgrade with HTTP 403
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token",
            )

        # Validate game exists
        try:
            gid = uuid.UUID(game_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            ) from e

        async with factory() as session:
            result = await session.execute(select(Game).where(Game.game_id == gid))
            db_game = result.scalar_one_or_none()

        if db_game is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found",
            )

        # Validate player is participant
        player_id = player.player_id
        if player_id not in (db_game.white_player, db_game.black_player):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a participant",
            )

        # All validations passed — hand off to handler
        await handle_game_ws(websocket, gid, token)

    return app


app = create_app()
