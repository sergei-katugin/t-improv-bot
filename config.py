from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ADMIN_BOT_TOKEN: str
    PUBLIC_BOT_TOKEN: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/impro.db"
    ANNOUNCEMENT_CHANNEL_ID: str = ""
    ADMIN_IDS: str = ""
    PUBLIC_BOT_USERNAME: str = "ImprovCypEventBot"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
ADMIN_ID_LIST: list[int] = (
    [int(x.strip()) for x in settings.ADMIN_IDS.split(",") if x.strip()]
    if settings.ADMIN_IDS
    else []
)
