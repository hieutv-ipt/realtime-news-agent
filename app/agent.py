import asyncio
import json
import logging
import time
from typing import Set

import aiohttp
import redis.asyncio as aioredis

from app.news_fetcher import Article, fetch_all_feeds, fetch_rss_tracked
from app.processors.summarizer import ArticleSummarizer
from app.store import store

logger = logging.getLogger(__name__)

_REDIS_CONNECT_TIMEOUT = 3


class NewsAgent:
    def __init__(
        self,
        feeds: list,
        summarizer: ArticleSummarizer,
        redis_url: str,
        channel: str,
        fetch_interval: int = 300,
        max_articles: int = 20,
    ):
        self._feeds = feeds
        self._summarizer = summarizer
        self._redis_url = redis_url
        self._channel = channel
        self._fetch_interval = fetch_interval
        self._max_articles = max_articles
        self._seen_ids: Set[str] = set()
        self._redis: aioredis.Redis | None = None
        self._running = False

    async def _try_connect_redis(self) -> None:
        try:
            client = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
            )
            await client.ping()
            self._redis = client
            logger.info("Connected to Redis at %s", self._redis_url)
        except Exception as exc:
            logger.warning("Redis unavailable (%s), using in-memory fallback", exc)
            self._redis = None

    async def _publish(self, article: Article) -> None:
        data = article.to_dict()
        store.put(data)
        if self._redis is None:
            return
        payload = json.dumps(data)
        try:
            await self._redis.publish(self._channel, payload)
            await self._redis.setex(f"article:{article.id}", 86400, payload)
            await self._redis.lpush("articles:recent", article.id)
            await self._redis.ltrim("articles:recent", 0, 199)
        except Exception as exc:
            logger.warning("Redis write failed (%s) — in-memory store still updated", exc)
            self._redis = None

    async def _enrich_and_publish(self, article: Article) -> None:
        loop = asyncio.get_running_loop()
        enriched = await loop.run_in_executor(None, self._summarizer.enrich, article)
        self._seen_ids.add(enriched.id)
        await self._publish(enriched)
        logger.info("[%s] %s (importance=%d)", enriched.category, enriched.title[:80], enriched.importance)

    async def _process_batch(self, articles: list[Article]) -> None:
        new_articles = [a for a in articles if a.id not in self._seen_ids]
        if not new_articles:
            logger.debug("No new articles in this batch")
            return
        logger.info("Processing %d new articles", len(new_articles))
        for article in new_articles:
            await self._enrich_and_publish(article)

    async def run_once(self) -> dict:
        """Run one ingest cycle and return stats. Used by POST /ingest/run."""
        sources_attempted = len(self._feeds)
        sources_failed = 0
        errors: list[str] = []
        all_articles: list[Article] = []

        async with aiohttp.ClientSession() as session:
            for feed in self._feeds:
                articles, err = await fetch_rss_tracked(session, feed["url"], feed["name"])
                all_articles.extend(articles)
                if err:
                    sources_failed += 1
                    errors.append(f"{feed['name']}: {err}")

        all_articles.sort(key=lambda a: a.published_at, reverse=True)
        all_articles = all_articles[: self._max_articles]

        new_articles = [a for a in all_articles if a.id not in self._seen_ids]
        skipped = len(all_articles) - len(new_articles)

        for article in new_articles:
            await self._enrich_and_publish(article)

        return {
            "fetched_count": len(all_articles),
            "stored_count": len(new_articles),
            "skipped_duplicates": skipped,
            "sources_attempted": sources_attempted,
            "sources_failed": sources_failed,
            "errors": errors,
        }

    async def run(self) -> None:
        await self._try_connect_redis()
        self._running = True
        logger.info("News agent started. Fetching every %ds", self._fetch_interval)
        while self._running:
            start = time.monotonic()
            try:
                articles = await fetch_all_feeds(self._feeds, self._max_articles)
                await self._process_batch(articles)
            except Exception as exc:
                logger.error("Agent cycle error: %s", exc)
            elapsed = time.monotonic() - start
            sleep_for = max(0, self._fetch_interval - elapsed)
            await asyncio.sleep(sleep_for)

    def stop(self) -> None:
        self._running = False
