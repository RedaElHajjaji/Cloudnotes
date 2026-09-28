"""Application settings loaded from environment variables (and a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings.

    Every field is overridable via a ``CLOUDNOTES_`` prefixed environment
    variable (e.g. ``CLOUDNOTES_LOG_LEVEL``) or via a ``.env`` file that is
    never committed to version control.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLOUDNOTES_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CloudNotes"
    app_env: str = "local"
    debug: bool = False
    log_level: str = "INFO"

    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:password@host:5432/dbname
    database_url: str = "postgresql+asyncpg://cloudnotes:cloudnotes@localhost:5432/cloudnotes"

    @property
    def database_url_offline(self) -> str:
        """Driver-agnostic URL used by Alembic's offline SQL-rendering mode."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
