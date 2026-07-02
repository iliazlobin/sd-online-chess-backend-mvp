from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # --- Required ---
    # PostgreSQL connection string. Example: postgresql+asyncpg://user:pass@db:5432/chess_mvp
    DATABASE_URL: str = "postgresql+asyncpg://chess:chess@localhost:5433/chess_mvp"

    # --- Optional ---
    # Port the app listens on inside the container.
    APP_PORT: int = 8000

    # Number of async database pool connections.
    DB_POOL_SIZE: int = 10

    # Max idle seconds before a DB connection is recycled.
    DB_MAX_IDLE_SECONDS: int = 300


settings = Settings()
