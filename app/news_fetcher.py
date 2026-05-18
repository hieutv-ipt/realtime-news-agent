import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class Article:
    id: str
    title: str
    url: str
    source: str
    published_at: datetime
    content: str = ""
    summary: Optional[str] = None
    category: Optional[str] = None
    sentiment: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    importance: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "content": self.content,
            "summary": self.summary,
            "category": self.category,
            "sentiment": self.sentiment,
            "entities": self.entities,
            "importance": self.importance,
        }


def _make_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _parse_entries(raw: str, source_name: str) -> List[Article]:
    """Parse feedparser-compatible RSS/Atom text into Article objects."""
    articles: List[Article] = []
    parsed = feedparser.parse(raw)
    for entry in parsed.entries:
        url = entry.get("link", "")
        if not url:
            continue
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        pub_dt = datetime(*published[:6]) if published else datetime.utcnow()
        content = ""
        if hasattr(entry, "summary"):
            soup = BeautifulSoup(entry.summary, "lxml")
            content = soup.get_text(separator=" ", strip=True)
        articles.append(
            Article(
                id=_make_id(url),
                title=entry.get("title", "Untitled"),
                url=url,
                source=source_name,
                published_at=pub_dt,
                content=content,
            )
        )
    return articles


async def fetch_rss_feed(
    session: aiohttp.ClientSession, feed_url: str, source_name: str
) -> List[Article]:
    """Fetch and parse a feed, returning [] on any error."""
    try:
        async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            raw = await resp.text()
        return _parse_entries(raw, source_name)
    except Exception as exc:
        logger.warning("Failed to fetch feed %s: %s", feed_url, exc)
        return []


async def fetch_rss_tracked(
    session: aiohttp.ClientSession, feed_url: str, source_name: str
) -> Tuple[List[Article], Optional[str]]:
    """Like fetch_rss_feed but returns (articles, error_msg) for caller stats."""
    try:
        async with session.get(feed_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            raw = await resp.text()
        return _parse_entries(raw, source_name), None
    except Exception as exc:
        logger.warning("Failed to fetch feed %s: %s", feed_url, exc)
        return [], str(exc)


async def fetch_all_feeds(feeds: List[dict], max_articles: int = 20) -> List[Article]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_rss_feed(session, f["url"], f["name"]) for f in feeds]
        results = await asyncio.gather(*tasks)
    all_articles: List[Article] = []
    for batch in results:
        all_articles.extend(batch)
    all_articles.sort(key=lambda a: a.published_at, reverse=True)
    return all_articles[:max_articles]
