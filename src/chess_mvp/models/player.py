from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chess_mvp.database import Base


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Relationships
    games_as_white = relationship(
        "Game", foreign_keys="Game.white_player", back_populates="white_player_rel"
    )
    games_as_black = relationship(
        "Game", foreign_keys="Game.black_player", back_populates="black_player_rel"
    )
