from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "i-will-change-you-in-production"
MIN_PRODUCTION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://audit:audit@localhost:5432/audit"
    secret_key: str = DEFAULT_SECRET_KEY
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    ack_overdue_days: int = 3
    cors_origins: str = "http://localhost:8000"
    env: Literal["development", "test", "production"] = "development"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cookie_secure(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == DEFAULT_SECRET_KEY:
                raise ValueError("SECRET_KEY must be changed when ENV=production")
            if len(self.secret_key) < MIN_PRODUCTION_SECRET_LENGTH:
                raise ValueError(
                    f"SECRET_KEY must be at least {MIN_PRODUCTION_SECRET_LENGTH} characters "
                    "when ENV=production"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
