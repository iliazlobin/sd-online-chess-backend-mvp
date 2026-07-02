from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status  # noqa: B008
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chess_mvp.auth import get_current_player
from chess_mvp.database import get_session
from chess_mvp.models.game import Game
from chess_mvp.models.player import Player
from chess_mvp.schemas.game import GameResponse, GameSummary

router = APIRouter(tags=["games"])


@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _player: Player = Depends(get_current_player),  # noqa: B008
):
    """Get game state and move history."""
    result = await session.execute(
        select(Game).options(selectinload(Game.moves)).where(Game.game_id == game_id)
    )
    game = result.scalar_one_or_none()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return GameResponse(
        game_id=str(game.game_id),
        fen=game.fen,
        status=game.status,
        players={
            "white": str(game.white_player),
            "black": str(game.black_player),
        },
        result=game.result,
        termination=game.termination,
        moves=[
            {
                "move_number": m.move_number,
                "from": m.from_square,
                "to": m.to_square,
                "promotion": m.promotion,
                "fen_before": m.fen_before,
                "fen_after": m.fen_after,
            }
            for m in (game.moves or [])
        ],
    )


@router.get("/players/{player_id}/games")
async def list_player_games(
    player_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    _player: Player = Depends(get_current_player),  # noqa: B008
):
    """List games for a player."""
    result = await session.execute(
        select(Game).where((Game.white_player == player_id) | (Game.black_player == player_id))
    )
    games = result.scalars().all()
    return {
        "games": [
            GameSummary(
                game_id=str(g.game_id),
                opponent=str(
                    g.black_player if str(g.white_player) == player_id else g.white_player
                ),
                result=g.result,
                date=g.created_at.isoformat() if g.created_at else None,
            )
            for g in games
        ]
    }
