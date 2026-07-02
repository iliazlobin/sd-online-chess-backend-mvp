from __future__ import annotations

import json
import logging
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from chess_mvp.database import get_session_factory
from chess_mvp.models.game import Game
from chess_mvp.models.player import Player
from chess_mvp.services.game_service import end_game, persist_move
from chess_mvp.ws.game_manager import GameState, game_manager

logger = logging.getLogger(__name__)


async def _lookup_player(token: str) -> Player | None:
    """Look up a player by bearer token."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Player).where(Player.token == token))
        return result.scalar_one_or_none()


async def handle_game_ws(websocket: WebSocket, game_id: uuid.UUID, token: str) -> None:
    """Main WebSocket handler for game connections.

    Called from the FastAPI WebSocket route after the initial HTTP upgrade.
    Auth and game validation are already done by the route handler.
    """
    player = await _lookup_player(token)
    if player is None:
        await websocket.close(code=4001, reason="Invalid token")
        return
    player_id = player.player_id

    # --- Verify game exists ---
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Game)
            .options(selectinload(Game.moves))
            .where(Game.game_id == game_id)
        )
        db_game = result.scalar_one_or_none()

    if db_game is None:
        await websocket.close(code=4001, reason="Game not found")
        return

    if player_id not in (db_game.white_player, db_game.black_player):
        await websocket.close(code=4001, reason="Not a participant")
        return

    # --- Ensure GameManager entry exists ---
    state = game_manager.get_game(game_id)
    if state is None:
        state = game_manager.create_game(
            game_id=game_id,
            white_id=db_game.white_player,
            black_id=db_game.black_player,
            fen=db_game.fen,
        )
        if db_game.status == "finished":
            state.status = "finished"
            state.result = db_game.result
            state.termination = db_game.termination

    # --- Persist callbacks ---
    async def persist_move_callback(
        s: GameState, from_sq: str, to_sq: str, prom: str | None,
        fen_before: str, fen_after: str,
    ) -> None:
        sf = get_session_factory()
        async with sf() as sess, sess.begin():
            r = await sess.execute(
                select(Game)
                .options(selectinload(Game.moves))
                .where(Game.game_id == s.game_id)
            )
            g = r.scalar_one()
            move_number = len(g.moves) + 1 if g.moves else 1
            await persist_move(
                sess, g, player_id, move_number,
                from_sq, to_sq, prom, fen_before, fen_after,
                s.pgn,
            )

    async def persist_resign_callback(
        s: GameState, is_resignation: bool = True,
    ) -> None:
        sf = get_session_factory()
        async with sf() as sess, sess.begin():
            r = await sess.execute(
                select(Game).where(Game.game_id == s.game_id)
            )
            g = r.scalar_one()
            await end_game(sess, g, s.result, s.termination)

    # --- Accept and register ---
    await websocket.accept()
    logger.info("WebSocket accepted for player %s in game %s", player_id, game_id)

    try:
        await game_manager.connect(game_id, player_id, websocket)
    except Exception as e:
        logger.exception("Failed to connect to game %s: %s", game_id, e)
        await websocket.close(code=4001, reason="Connection failed")
        return

    # --- Receive loop ---
    try:
        while state.status == "active":
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "code": "INVALID_JSON"})
                )
                continue

            msg_type = msg.get("type")

            if msg_type == "move":
                from_sq = msg.get("from", "")
                to_sq = msg.get("to", "")
                promotion = msg.get("promotion")

                response = await game_manager.handle_move(
                    game_id, player_id, from_sq, to_sq, promotion,
                    persist_callback=persist_move_callback,
                )

                resp_type = response.get("type")

                if resp_type == "move_made":
                    # Send move_made to sender only (no opponent broadcast)
                    await websocket.send_text(json.dumps(response))

                elif resp_type == "game_over":
                    # Broadcast game_over to BOTH players
                    game_over_json = json.dumps(response)
                    await game_manager.broadcast_to_both(game_id, game_over_json)

                else:
                    # Error — send to sender only
                    await websocket.send_text(json.dumps(response))

            elif msg_type == "resign":
                response = await game_manager.handle_resign(
                    game_id, player_id,
                    persist_callback=persist_resign_callback,
                )

                resp_type = response.get("type")

                if resp_type == "game_over":
                    # Broadcast to both
                    game_over_json = json.dumps(response)
                    await game_manager.broadcast_to_both(game_id, game_over_json)

                else:
                    # Error — send to sender
                    await websocket.send_text(json.dumps(response))

            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "code": "UNKNOWN_MESSAGE_TYPE"})
                )

    except WebSocketDisconnect:
        logger.info("Player %s disconnected from game %s", player_id, game_id)
    except Exception:
        logger.exception("Error in game handler for player %s, game %s", player_id, game_id)
    finally:
        await game_manager.disconnect(game_id, player_id)
