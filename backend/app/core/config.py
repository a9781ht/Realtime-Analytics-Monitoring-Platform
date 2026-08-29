"""應用程式設定（Pydantic Settings）。

所有設定皆可由環境變數覆寫，容器與本機共用同一份程式碼。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- 一般 ----
    PROJECT_NAME: str = "Realtime Analytics Platform"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # ---- 資料庫 ----
    DB_HOST: str = "mariadb"
    DB_PORT: int = 3306
    DB_NAME: str = "analytics"
    DB_USER: str = "analytics"
    DB_PASSWORD: str = "analytics_pw_change_me"

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # 測試時可直接指定完整 DSN（例如 sqlite+aiosqlite:///:memory:）
    DATABASE_URL: str | None = None

    # ---- JWT ----
    SECRET_KEY: str = "please-generate-your-own-super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080

    # ---- CORS ----
    # NoDecode 保留 .env 的逗號分隔字串，交由下方 validator 拆分。
    # 未指定時 Pydantic Settings 會將 list 環境變數預設當作 JSON 處理。
    BACKEND_CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:8501"]

    # ---- 即時資料產生器 ----
    GENERATOR_ENABLED: bool = True
    GENERATOR_INTERVAL_SECONDS: float = 1.0
    GENERATOR_BATCH_SIZE: int = 5
    GENERATOR_FLUSH_INTERVAL: int = 5
    GENERATOR_FLUSH_SIZE: int = 50
    ALERT_THRESHOLD_HIGH: float = 90.0
    ALERT_THRESHOLD_LOW: float = 10.0

    # ---- 種子資料 ----
    SEED_DEMO_USERS: bool = True
    ADMIN_USERNAME: str = "admin"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "Admin@1234"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def sqlalchemy_database_uri(self) -> str:
        """非同步連線字串（asyncmy driver）。"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+asyncmy://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_database_uri.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
