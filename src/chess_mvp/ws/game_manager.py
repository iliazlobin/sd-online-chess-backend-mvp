from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field

import chess
import chess.pgn
from fastapi import WebSocket

from chess_mvp.services.chess_service import ChessService


@dataclass
class GameState:
    """In-memory state for a single active game."""

    game_id: uuid.UUID
    white_id: uuid.UUID
    black_id: uuid.UUID
    board: chess.Board = field(default_factory=ChessService.initial_board)
    white_ws: WebSocket | None = None
    black_ws: WebSocket | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    status: str = "active"
    result: str | None = None
    termination: str | None = None

    @property
    def pgn(self) -> str:
        """Generate PGN from the board's move stack."""
        game = chess.pgn.Game()
        node = game
        for move in self.board.move_stack:
            node = node.add_variation(move)
        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
        game.accept(exporter)
        return str(exporter)

    def player_color(self, player_id: uuid.UUID) -> str | None:
        if player_id == self.white_id:
            return "white"
        if player_id == self.black_id:
            return "black"
        return None

    def is_player_turn(self, player_id: uuid.UUID) -> bool:
        color = self.player_color(player_id)
        if color == "white":
            return self.board.turn == chess.WHITE
        if color == "black":
            return self.board.turn == chess.BLACK
        return False

    def get_ws(self, player_id: uuid.UUID) -> WebSocket | None:
        color = self.player_color(player_id)
        if color == "white":
            return self.white_ws
        if color == "black":
            return self.black_ws
        return None

    def set_ws(self, player_id: uuid.UUID, ws: WebSocket | None) -> None:
        color = self.player_color(player_id)
        if color == "white":
            self.white_ws = ws
        elif color == "black":
            self.black_ws = ws

    def opponent_id(self, player_id: uuid.UUID) -> uuid.UUID:
        return self.black_id if player_id == self.white_id else self.white_id


class GameManager:
    """Singleton registry of all active games and their WebSocket connections."""

    _instance: GameManager | None = None

    def __init__(self) -> None:
        self._games: dict[uuid.UUID, GameState] = {}

    @classmethod
    def get(cls) -> GameManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_game(
        self,
        game_id: uuid.UUID,
        white_id: uuid.UUID,
        black_id: uuid.UUID,
        fen: str | None = None,
    ) -> GameState:
        """Create an in-memory game state entry."""
        board = chess.Board(fen) if fen else ChessService.initial_board()
        state = GameState(
            game_id=game_id,
            white_id=white_id,
            black_id=black_id,
            board=board,
        )
        self._games[game_id] = state
        return state

    def get_game(self, game_id: uuid.UUID) -> GameState | None:
        return self._games.get(game_id)

    def remove_game(self, game_id: uuid.UUID) -> None:
        self._games.pop(game_id, None)

    async def connect(
        self,
        game_id: uuid.UUID,
        player_id: uuid.UUID,
        ws: WebSocket,
    ) -> GameState:
        """Register a WebSocket connection for a player in a game."""
        state = self._games.get(game_id)
        if state is None:
            raise ValueError(f"Game {game_id} not found")

        async with state.lock:
            # Close stale connection if reconnecting
            old_ws = state.get_ws(player_id)
            if old_ws is not None:
                with contextlib.suppress(Exception):
                    await old_ws.close()

            state.set_ws(player_id, ws)

            # Send game state to connecting player
            color = state.player_color(player_id)
            await ws.send_text(json.dumps({
                "type": "game_state",
                "fen": state.board.fen(),
                "your_color": color,
                "players": {
                    "white": str(state.white_id),
                    "black": str(state.black_id),
                },
            }))

            # Notify about opponent connection status
            opponent_ws = state.get_ws(state.opponent_id(player_id))
            if opponent_ws is None:
                await ws.send_text(json.dumps({"type": "opponent_disconnected"}))
            else:
                with contextlib.suppress(Exception):
                    await opponent_ws.send_text(json.dumps({"type": "opponent_connected"}))

        return state

    async def disconnect(self, game_id: uuid.UUID, player_id: uuid.UUID) -> None:
        """Handle a player disconnecting."""
        state = self._games.get(game_id)
        if state is None:
            return

        async with state.lock:
            state.set_ws(player_id, None)

            opponent_ws = state.get_ws(state.opponent_id(player_id))
            if opponent_ws is not None:
                with contextlib.suppress(Exception):
                    await opponent_ws.send_text(
                        json.dumps({"type": "opponent_disconnected"})
                    )

    async def handle_move(
        self,
        game_id: uuid.UUID,
        player_id: uuid.UUID,
        from_sq: str,
        to_sq: str,
        promotion: str | None = None,
        persist_callback=None,
    ) -> dict:
        """Validate and apply a move. Returns response dict.

        The caller is responsible for sending the response to the sender
        and broadcasting to the opponent.
        """
        state = self._games.get(game_id)
        if state is None:
            return {"type": "error", "code": "GAME_NOT_FOUND"}
        if state.status != "active":
            return {"type": "error", "code": "GAME_OVER"}

        async with state.lock:
            if not state.is_player_turn(player_id):
                return {"type": "error", "code": "NOT_YOUR_TURN"}

            move = ChessService.validate_move(state.board, from_sq, to_sq, promotion)
            if move is None:
                return {"type": "error", "code": "ILLEGAL_MOVE"}

            fen_before = state.board.fen()

            ChessService.apply_move(state.board, move)
            fen_after = state.board.fen()
            legal_count = ChessService.get_legal_moves_count(state.board)

            if persist_callback is not None:
                await persist_callback(state, from_sq, to_sq, promotion, fen_before, fen_after)

            is_over, result = ChessService.is_game_over(state.board)

            if is_over:
                state.status = "finished"
                state.result = result
                if ChessService.is_checkmate(state.board):
                    state.termination = "checkmate"
                elif ChessService.is_stalemate(state.board):
                    state.termination = "stalemate"
                else:
                    state.termination = "draw"

                winner_map = {"1-0": "White", "0-1": "Black", "½-½": "Draw"}
                winner = winner_map.get(result, "Draw")
                if result in ("1-0", "0-1"):
                    result_text = f"{result} — {winner} wins by checkmate"
                else:
                    result_text = f"{result} — Draw by stalemate"

                return {
                    "type": "game_over",
                    "result": result_text,
                }

            return {
                "type": "move_made",
                "fen": fen_after,
                "legal_next_moves": legal_count,
            }

    async def handle_resign(
        self,
        game_id: uuid.UUID,
        player_id: uuid.UUID,
        persist_callback=None,
    ) -> dict:
        """Handle a player resigning."""
        state = self._games.get(game_id)
        if state is None:
            return {"type": "error", "code": "GAME_NOT_FOUND"}
        if state.status != "active":
            return {"type": "error", "code": "GAME_OVER"}

        async with state.lock:
            color = state.player_color(player_id)
            if color is None:
                return {"type": "error", "code": "NOT_A_PLAYER"}

            state.status = "finished"
            state.termination = "resignation"

            if color == "white":
                state.result = "0-1"
                result_msg = "0-1 — Black wins by resignation"
            else:
                state.result = "1-0"
                result_msg = "1-0 — White wins by resignation"

            if persist_callback is not None:
                await persist_callback(state, is_resignation=True)

            return {"type": "game_over", "result": result_msg}

    async def broadcast_to_opponent(
        self, game_id: uuid.UUID, player_id: uuid.UUID, message: str
    ) -> None:
        """Send a message to the opponent only."""
        state = self._games.get(game_id)
        if state is None:
            return
        opponent_ws = state.get_ws(state.opponent_id(player_id))
        if opponent_ws is not None:
            with contextlib.suppress(Exception):
                await opponent_ws.send_text(message)

    async def broadcast_to_both(
        self, game_id: uuid.UUID, message: str
    ) -> None:
        """Send a message to both connected players."""
        state = self._games.get(game_id)
        if state is None:
            return
        for ws in (state.white_ws, state.black_ws):
            if ws is not None:
                with contextlib.suppress(Exception):
                    await ws.send_text(message)


# Module-level singleton getter
game_manager = GameManager.get()
