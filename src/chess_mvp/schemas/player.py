from __future__ import annotations

from pydantic import BaseModel


class PlayerCreate(BaseModel):
    username: str | None = None


class PlayerResponse(BaseModel):
    player_id: str
    token: str
