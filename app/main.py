import asyncio
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import NewsAgent
from app.api.routes import router
from app.processors.summarizer import ArticleSummarizer
from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Realtime News Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")

_agent: NewsAgent | None = None
_agent_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup():
    global _agent, _agent_task
    summarizer = ArticleSummarizer(
        api_key=settings.anthropic_api_key,  # None → no-LLM fallback mode
        model=settings.claude_model,
    )
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — running in no-LLM fallback mode")
    feeds = [
        {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/rss.xml"},
        {"name": "Reuters", "url": "https://feeds.reuters.com/reuters/topNews"},
        {"name": "NYT", "url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"},
    ]
    _agent = NewsAgent(
        feeds=feeds,
        summarizer=summarizer,
        redis_url=settings.redis_url,
        channel=settings.redis_channel,
        fetch_interval=settings.fetch_interval_seconds,
        max_articles=settings.max_articles_per_fetch,
    )
    _agent_task = asyncio.create_task(_agent.run())
    logger.info("News agent task started")


@app.on_event("shutdown")
async def shutdown():
    if _agent:
        _agent.stop()
    if _agent_task:
        _agent_task.cancel()
        try:
            await _agent_task
        except asyncio.CancelledError:
            pass
    logger.info("News agent stopped")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
