from __future__ import annotations

from fastapi import APIRouter, Depends  # noqa: B008
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.auth import get_current_player
from chess_mvp.database import get_session
from chess_mvp.models.player import Player
from chess_mvp.schemas.matchmaking import MatchmakingResponse

router = APIRouter(tags=["matchmaking"])


@router.post("/matchmaking", response_model=MatchmakingResponse)
async def post_matchmaking(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    player: Player = Depends(get_current_player),  # noqa: B008
):
    """Enter matchmaking queue or match with a waiting opponent."""
    # For the scaffold, always return "waiting" — full matchmaking
    # logic is implemented in a subsequent staff-engineer task.
    return MatchmakingResponse(status="waiting")
