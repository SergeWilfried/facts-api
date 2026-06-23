from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/kaseto"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    apify_api_token: str = ""
    tavily_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
