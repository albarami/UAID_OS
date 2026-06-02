from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    chroma_url: str = "http://localhost:8001"
    anthropic_api_key: str = ""
    openai_api_key: str = ""


settings = Settings()
