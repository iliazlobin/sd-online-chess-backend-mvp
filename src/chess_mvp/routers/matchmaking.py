from __future__ import annotations

from fastapi import APIRouter, Depends  # noqa: B008
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.auth import get_current_player
from chess_mvp.database import get_session
from chess_mvp.models.player import Player
from chess_mvp.services.matchmaking_service import enter_matchmaking

router = APIRouter(tags=["matchmaking"])


@router.post("/matchmaking")
async def post_matchmaking(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    player: Player = Depends(get_current_player),  # noqa: B008
):
    """Enter matchmaking queue or match with a waiting opponent.

    - If the player is already in an active game → 202 with the game_id.
    - If a waiting opponent is found → 202 with game_id.
    - Otherwise → 200 with status "waiting".
    """
    result = await enter_matchmaking(session, player.player_id)

    await session.commit()

    if result.status == "matched":
        return JSONResponse(
            status_code=202,
            content={
                "status": "matched",
                "game_id": result.game_id,
                "ws_url": result.ws_url,
            },
        )

    return JSONResponse(
        status_code=200,
        content={"status": "waiting"},
    )
