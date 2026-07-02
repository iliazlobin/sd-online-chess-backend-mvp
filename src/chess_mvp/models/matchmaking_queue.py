from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from chess_mvp.database import Base


class MatchmakingQueue(Base):
    __tablename__ = "matchmaking_queue"

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("players.player_id"), primary_key=True
    )
    joined_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
