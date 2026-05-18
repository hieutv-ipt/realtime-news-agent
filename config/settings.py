from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")
    claude_model: str = Field("claude-sonnet-4-6", env="CLAUDE_MODEL")

    # NewsAPI
    news_api_key: str = Field("", env="NEWS_API_KEY")

    # RSS feeds to monitor
    rss_feeds: List[str] = Field(
        default=[
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://feeds.reuters.com/reuters/topNews",
        ],
        env="RSS_FEEDS",
    )

    # Redis
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")
    redis_channel: str = Field("news_stream", env="REDIS_CHANNEL")

    # App
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    fetch_interval_seconds: int = Field(300, env="FETCH_INTERVAL_SECONDS")
    max_articles_per_fetch: int = Field(20, env="MAX_ARTICLES_PER_FETCH")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
