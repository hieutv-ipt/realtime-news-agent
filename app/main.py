import asyncio
import logging
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows so non-ASCII article titles log cleanly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent import NewsAgent
from app.api.digest import router as digest_router
from app.api.ingest import router as ingest_router
from app.api.routes import router as core_router
from app.processors.summarizer import ArticleSummarizer
from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Realtime News Agent",
    version="1.0.0",
    description=(
        "Realtime news aggregation and intelligence agent. "
        "Fetches RSS feeds, classifies articles by category, scores importance, "
        "and answers questions about the news via a REST/WebSocket API."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core_router, prefix="/api/v1", tags=["Articles & Stream"])
app.include_router(ingest_router, prefix="/api/v1", tags=["Ingest"])
app.include_router(digest_router, prefix="/api/v1", tags=["Digest & Ask"])

_agent_task: asyncio.Task | None = None


def _load_feeds() -> list[dict]:
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    try:
        with open(config_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        feeds = cfg.get("sources", {}).get("rss", [])
        if feeds:
            logger.info("Loaded %d feeds from config.yaml", len(feeds))
            return feeds
    except Exception as exc:
        logger.warning("Could not load feeds from config.yaml (%s), using defaults", exc)
    return [
        {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "BBC Technology", "url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
    ]


@app.on_event("startup")
async def startup() -> None:
    global _agent_task
    summarizer = ArticleSummarizer(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model,
    )
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — running in no-LLM fallback mode")
    else:
        logger.info("LLM enrichment enabled (model: %s)", settings.claude_model)

    feeds = _load_feeds()
    agent = NewsAgent(
        feeds=feeds,
        summarizer=summarizer,
        redis_url=settings.redis_url,
        channel=settings.redis_channel,
        fetch_interval=settings.fetch_interval_seconds,
        max_articles=settings.max_articles_per_fetch,
    )
    app.state.agent = agent
    _agent_task = asyncio.create_task(agent.run())
    logger.info("News agent task started with %d feeds", len(feeds))


@app.on_event("shutdown")
async def shutdown() -> None:
    agent: NewsAgent | None = getattr(app.state, "agent", None)
    if agent:
        agent.stop()
    if _agent_task:
        _agent_task.cancel()
        try:
            await _agent_task
        except asyncio.CancelledError:
            pass
    logger.info("News agent stopped")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
