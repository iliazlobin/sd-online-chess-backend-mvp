from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status  # noqa: B008
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.database import get_session
from chess_mvp.schemas.player import PlayerCreate, PlayerResponse
from chess_mvp.services.player_service import register_player

router = APIRouter(prefix="/players", tags=["players"])


@router.post("", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
async def post_register(
    body: PlayerCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    """Register a new player. Empty body or optional username."""
    try:
        player = await register_player(session, username=body.username)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return PlayerResponse(
        player_id=str(player.player_id),
        token=player.token,
    )
