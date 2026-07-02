from __future__ import annotations

import chess
from chess import Board


class ChessService:
    """Wrapper around python-chess for move validation, application, and game-end detection."""

    @staticmethod
    def validate_move(
        board: Board, from_sq: str, to_sq: str, promotion: str | None = None
    ) -> chess.Move | None:
        """Return the Move object if legal on the given board, else None."""
        try:
            move = chess.Move.from_uci(from_sq + to_sq + (promotion or ""))
        except ValueError:
            return None
        if move in board.legal_moves:
            return move
        # Try with promotion inferred from the board (UCI promotion handling)
        if promotion is None:
            for piece in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
                try:
                    candidate = chess.Move.from_uci(from_sq + to_sq + chess.piece_name(piece)[0])
                except ValueError:
                    continue
                if candidate in board.legal_moves:
                    return candidate
        return None

    @staticmethod
    def apply_move(board: Board, move: chess.Move) -> str:
        """Push move onto board and return the new FEN."""
        board.push(move)
        return board.fen()

    @staticmethod
    def is_checkmate(board: Board) -> bool:
        return board.is_checkmate()

    @staticmethod
    def is_stalemate(board: Board) -> bool:
        return board.is_stalemate()

    @staticmethod
    def is_game_over(board: Board) -> tuple[bool, str | None]:
        """Return (is_over, result_string) like ('1-0', '0-1', '½-½')."""
        if board.is_checkmate():
            # Checkmate: side to move loses
            if board.turn == chess.WHITE:
                return True, "0-1"
            return True, "1-0"
        if board.is_stalemate():
            return True, "½-½"
        if board.is_insufficient_material():
            return True, "½-½"
        return False, None

    @staticmethod
    def get_legal_moves_count(board: Board) -> int:
        return board.legal_moves.count()

    @staticmethod
    def initial_board() -> Board:
        return chess.Board()
