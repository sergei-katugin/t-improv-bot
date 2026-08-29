from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ADMIN_BOT_TOKEN: str
    PUBLIC_BOT_TOKEN: str
    DATABASE_URL: str
    ANNOUNCEMENT_CHANNEL_ID: str = ""
    ADMIN_IDS: str = ""
    PUBLIC_BOT_USERNAME: str = "ImprovCypEventBot"
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_SECRET: str = ""
    INVITE_TTL_HOURS: int = 24
    APP_TIMEZONE: str = "Europe/Nicosia"
    REMINDER_HOUR_LOCAL: int = 9
    MAX_CONCURRENT_UPDATES: int = 20
    ALLOW_SQLITE_FOR_TESTS: bool = False

    model_config = SettingsConfigDict(env_file=".env")

    @model_validator(mode="after")
    def require_postgres_runtime(self):
        is_sqlite = self.DATABASE_URL.startswith("sqlite") or "sqlite+" in self.DATABASE_URL
        if is_sqlite and not self.ALLOW_SQLITE_FOR_TESTS:
            raise ValueError(
                "SQLite is test-only. Configure an external Postgres DATABASE_URL."
            )
        return self


settings = Settings()
ADMIN_ID_LIST: list[int] = (
    [int(x.strip()) for x in settings.ADMIN_IDS.split(",") if x.strip()]
    if settings.ADMIN_IDS
    else []
)
