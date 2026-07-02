"""Online Chess MVP — initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column(
            "player_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "token", sa.Text(), nullable=False, server_default=sa.text("gen_random_uuid()::text")
        ),
        sa.Column("username", sa.String(128), nullable=True, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("player_id"),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "games",
        sa.Column(
            "game_id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("white_player", sa.Uuid(), nullable=False),
        sa.Column("black_player", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("result", sa.String(8), nullable=True),
        sa.Column("fen", sa.Text(), nullable=False),
        sa.Column("pgn", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("termination", sa.String(24), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("game_id"),
        sa.ForeignKeyConstraint(["white_player"], ["players.player_id"]),
        sa.ForeignKeyConstraint(["black_player"], ["players.player_id"]),
    )

    op.create_table(
        "moves",
        sa.Column("move_id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("game_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("move_number", sa.Integer(), nullable=False),
        sa.Column("from_square", sa.String(4), nullable=False),
        sa.Column("to_square", sa.String(4), nullable=False),
        sa.Column("promotion", sa.String(2), nullable=True),
        sa.Column("fen_before", sa.Text(), nullable=False),
        sa.Column("fen_after", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("move_id"),
        sa.ForeignKeyConstraint(["game_id"], ["games.game_id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.player_id"]),
    )

    op.create_table(
        "matchmaking_queue",
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("player_id"),
        sa.ForeignKeyConstraint(["player_id"], ["players.player_id"]),
    )


def downgrade() -> None:
    op.drop_table("matchmaking_queue")
    op.drop_table("moves")
    op.drop_table("games")
    op.drop_table("players")
