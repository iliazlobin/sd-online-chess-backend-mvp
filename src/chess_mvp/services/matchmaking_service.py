from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chess_mvp.models.game import Game
from chess_mvp.models.matchmaking_queue import MatchmakingQueue


@dataclass
class MatchResult:
    status: str  # "waiting" or "matched"
    game_id: str | None = None
    ws_url: str | None = None


async def enter_matchmaking(
    session: AsyncSession, player_id: uuid.UUID
) -> MatchResult:
    """Handle a matchmaking request for a player.

    1. Check if player is already in an active game → return matched
    2. Try to dequeue a waiting opponent → create game, return matched
    3. Add player to queue → return waiting
    """
    # Check if player is already in an active (not yet finished) game
    existing_game = await session.execute(
        select(Game).where(
            (Game.white_player == player_id) | (Game.black_player == player_id),
            Game.status == "active",
        ).limit(1)
    )
    game = existing_game.scalar_one_or_none()
    if game is not None:
        return MatchResult(
            status="matched",
            game_id=str(game.game_id),
            ws_url=f"/games/{game.game_id}",
        )

    # Try to find a waiting opponent
    # SELECT ... FOR UPDATE SKIP LOCKED for atomic dequeue
    waiting = await session.execute(
        select(MatchmakingQueue)
        .where(MatchmakingQueue.player_id != player_id)
        .order_by(MatchmakingQueue.joined_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    opponent_entry = waiting.scalar_one_or_none()

    if opponent_entry is not None:
        opponent_id = opponent_entry.player_id

        # Remove opponent from queue
        await session.execute(
            delete(MatchmakingQueue).where(
                MatchmakingQueue.player_id == opponent_id
            )
        )

        # Create the game (white = opponent who was waiting first, black = current player)
        # First in queue is white
        initial_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        game = Game(
            white_player=opponent_id,
            black_player=player_id,
            status="active",
            fen=initial_fen,
            pgn="",
        )
        session.add(game)
        await session.flush()

        return MatchResult(
            status="matched",
            game_id=str(game.game_id),
            ws_url=f"/games/{game.game_id}",
        )

    # No opponent waiting — add player to queue
    # Upsert: remove any stale queue entry first, then insert
    await session.execute(
        delete(MatchmakingQueue).where(
            MatchmakingQueue.player_id == player_id
        )
    )
    session.add(MatchmakingQueue(player_id=player_id))
    await session.flush()

    return MatchResult(status="waiting")


async def cleanup_queue_entry(
    session: AsyncSession, player_id: uuid.UUID
) -> None:
    """Remove a player from the matchmaking queue."""
    await session.execute(
        delete(MatchmakingQueue).where(MatchmakingQueue.player_id == player_id)
    )
