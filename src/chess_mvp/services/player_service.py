from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.models.player import Player


async def register_player(session: AsyncSession, username: str | None = None) -> Player:
    """Create a new player. Returns 409-like error if username taken."""
    if username is not None:
        existing = await session.execute(select(Player).where(Player.username == username))
        if existing.scalar_one_or_none():
            raise ValueError(f"Username '{username}' already taken")
    player = Player(username=username)
    session.add(player)
    await session.flush()
    return player


async def get_player_by_token(session: AsyncSession, token: str) -> Player | None:
    result = await session.execute(select(Player).where(Player.token == token))
    return result.scalar_one_or_none()
