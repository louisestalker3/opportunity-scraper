from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/opportunity_scraper"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI
    openai_api_key: str = ""

    # Reddit
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "OpportunityScraper/1.0"

    # Twitter/X
    twitter_bearer_token: str = ""

    # App
    secret_key: str = "change-me-in-production"
    environment: str = "development"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def sync_database_url(self) -> str:
        """Return a sync database URL for Alembic."""
        return self.database_url.replace("+asyncpg", "+psycopg2").replace(
            "asyncpg", "psycopg2"
        )


settings = Settings()
