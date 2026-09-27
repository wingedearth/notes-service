"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the notes service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongodb_uri: str = Field(..., alias="MONGODB_URI")
    db_name: str = Field(default="notes-service", alias="DB_NAME")
    port: int = Field(default=8000, alias="PORT")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
