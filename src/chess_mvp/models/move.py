from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chess_mvp.database import Base
from chess_mvp.models.game import Game  # noqa: F401


class Move(Base):
    __tablename__ = "moves"

    move_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("games.game_id"), nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.player_id"), nullable=False
    )
    move_number: Mapped[int] = mapped_column(Integer, nullable=False)
    from_square: Mapped[str] = mapped_column(String(4), nullable=False)
    to_square: Mapped[str] = mapped_column(String(4), nullable=False)
    promotion: Mapped[str | None] = mapped_column(String(2), nullable=True)
    fen_before: Mapped[str] = mapped_column(Text, nullable=False)
    fen_after: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Relationships
    game: Mapped[Game] = relationship("Game", back_populates="moves")
