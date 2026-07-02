from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chess_mvp.models.game import Game
from chess_mvp.models.move import Move


async def create_game(
    session: AsyncSession,
    white_id: uuid.UUID,
    black_id: uuid.UUID,
    fen: str,
) -> Game:
    """Create and persist a new game."""
    game = Game(
        white_player=white_id,
        black_player=black_id,
        status="active",
        fen=fen,
        pgn="",
    )
    session.add(game)
    await session.flush()
    return game


async def get_game_by_id(
    session: AsyncSession, game_id: uuid.UUID | str
) -> Game | None:
    """Load a game with its moves eagerly loaded."""
    result = await session.execute(
        select(Game)
        .options(selectinload(Game.moves))
        .where(Game.game_id == game_id)
    )
    return result.scalar_one_or_none()


async def persist_move(
    session: AsyncSession,
    game: Game,
    player_id: uuid.UUID,
    move_number: int,
    from_sq: str,
    to_sq: str,
    promotion: str | None,
    fen_before: str,
    fen_after: str,
    pgn: str,
) -> Move:
    """Persist a move and update the game state in one transaction context."""
    move = Move(
        game_id=game.game_id,
        player_id=player_id,
        move_number=move_number,
        from_square=from_sq,
        to_square=to_sq,
        promotion=promotion,
        fen_before=fen_before,
        fen_after=fen_after,
    )
    session.add(move)
    game.fen = fen_after
    game.pgn = pgn
    return move


async def end_game(
    session: AsyncSession,
    game: Game,
    result: str,
    termination: str,
) -> None:
    """Mark a game as finished."""
    game.status = "finished"
    game.result = result
    game.termination = termination
    game.finished_at = datetime.now(UTC)
