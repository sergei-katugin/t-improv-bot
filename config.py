from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    ADMIN_BOT_TOKEN: str
    PUBLIC_BOT_TOKEN: str
    DATABASE_URL: str
    ANNOUNCEMENT_CHANNEL_ID: str = ""
    ADMIN_IDS: str = ""
    PUBLIC_BOT_USERNAME: str = "ImprovCypEventBot"
    ADMIN_BOT_USERNAME: str = "ImprovCypBot"
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_SECRET: str = ""
    INVITE_TTL_HOURS: int = 24
    APP_TIMEZONE: str = "Europe/Nicosia"
    REMINDER_HOUR_LOCAL: int = 9
    MAX_CONCURRENT_UPDATES: int = 20
    FSM_TTL_DAYS: int = 30
    ERROR_ALERT_CHAT_ID: Optional[int] = None
    ALLOW_SQLITE_FOR_TESTS: bool = False

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def require_postgres_runtime(self):
        is_sqlite = self.DATABASE_URL.startswith("sqlite") or "sqlite+" in self.DATABASE_URL
        if is_sqlite and not self.ALLOW_SQLITE_FOR_TESTS:
            raise ValueError(
                "SQLite is test-only. Configure an external Postgres DATABASE_URL."
            )
        if not 0 <= self.REMINDER_HOUR_LOCAL <= 23:
            raise ValueError("REMINDER_HOUR_LOCAL must be between 0 and 23")
        if self.MAX_CONCURRENT_UPDATES < 1:
            raise ValueError("MAX_CONCURRENT_UPDATES must be positive")
        return self


settings = Settings()
ADMIN_ID_LIST: list[int] = (
    [int(x.strip()) for x in settings.ADMIN_IDS.split(",") if x.strip()]
    if settings.ADMIN_IDS
    else []
)
