from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parents[3]
if (_ROOT_DIR / ".env").exists():
    load_dotenv(_ROOT_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(_ROOT_DIR / ".env")),
        env_prefix="REPROLAB_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://reprolab:reprolab@localhost:5432/reprolab"
    storage_root: Path = Path("storage")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1)
    cors_origins: str = "http://localhost:3000"
    auto_create_schema: bool = True
    gemini_api_key: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = "gemini-2.5-flash"
    auth_enabled: bool = False
    api_tokens: str = ""
    backup_dir: Path = Path("storage/backups")
    runner_backend: str = "subprocess"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
