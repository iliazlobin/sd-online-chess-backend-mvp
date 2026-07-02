from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chess_mvp.database import Base


class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    white_player: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.player_id"), nullable=False
    )
    black_player: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.player_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active | finished
    result: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )  # "1-0" | "0-1" | "½-½" | NULL
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    pgn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    termination: Mapped[str | None] = mapped_column(
        String(24), nullable=True
    )  # checkmate | stalemate | resignation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    white_player_rel = relationship(
        "Player", foreign_keys=[white_player], back_populates="games_as_white"
    )
    black_player_rel = relationship(
        "Player", foreign_keys=[black_player], back_populates="games_as_black"
    )
    moves = relationship("Move", back_populates="game", order_by="Move.move_number")
