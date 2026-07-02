from __future__ import annotations

from pydantic import BaseModel


class MatchmakingResponse(BaseModel):
    status: str  # "waiting"
    game_id: str | None = None
    ws_url: str | None = None
