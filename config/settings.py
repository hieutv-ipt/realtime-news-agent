from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Anthropic (optional — app runs in no-LLM mode when absent)
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    claude_model: str = Field("claude-sonnet-4-6", validation_alias="CLAUDE_MODEL")

    # NewsAPI
    news_api_key: str = Field("", validation_alias="NEWS_API_KEY")

    # Redis
    redis_url: str = Field("redis://localhost:6379", validation_alias="REDIS_URL")
    redis_channel: str = Field("news_stream", validation_alias="REDIS_CHANNEL")

    # App
    host: str = Field("0.0.0.0", validation_alias="HOST")
    port: int = Field(8000, validation_alias="PORT")
    fetch_interval_seconds: int = Field(300, validation_alias="FETCH_INTERVAL_SECONDS")
    max_articles_per_fetch: int = Field(20, validation_alias="MAX_ARTICLES_PER_FETCH")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")


settings = Settings()
