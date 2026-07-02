from __future__ import annotations

from pydantic import BaseModel


class GameResponse(BaseModel):
    game_id: str
    fen: str
    status: str
    players: dict[str, str]  # {"white": "<id>", "black": "<id>"}
    result: str | None = None
    termination: str | None = None
    moves: list[dict] = []


class GameSummary(BaseModel):
    game_id: str
    opponent: str
    result: str | None = None
    date: str | None = None
