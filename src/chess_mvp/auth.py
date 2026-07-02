from __future__ import annotations

from fastapi import Depends, HTTPException, status  # noqa: B008
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.database import get_session
from chess_mvp.models.player import Player
from chess_mvp.services.player_service import get_player_by_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_player(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> Player:
    """FastAPI dependency. Extracts Bearer token and returns the Player."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing authorization header",
        )
    player = await get_player_by_token(session, credentials.credentials)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token",
        )
    return player
