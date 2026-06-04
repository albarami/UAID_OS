from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Runtime connections use the non-superuser, RLS-enforced role `uaid_app`.
    # No password in source: the real value is supplied via env (the Makefile
    # injects RLS_DB_PASSWORD into these URLs). The password-less default fails
    # closed locally unless DATABASE_URL/TEST_DATABASE_URL are provided.
    database_url: str = "postgresql+asyncpg://uaid_app@localhost:5432/app"
    test_database_url: str = "postgresql+asyncpg://uaid_app@localhost:5432/app_test"
    # Admin (owner/superuser) connections are used ONLY for migrations + schema/role
    # bootstrap + test seeding. Migrations must never run as `uaid_app`.
    admin_database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    test_admin_database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app_test"
    redis_url: str = "redis://localhost:6379/0"
    chroma_url: str = "http://localhost:8001"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Slice 14a — LLM extraction. No default model: empty ⇒ fail closed (no provider
    # call). The exact model id must be set AND present in the price card.
    llm_extraction_model: str = ""
    llm_max_output_tokens: int = 2048


settings = Settings()
