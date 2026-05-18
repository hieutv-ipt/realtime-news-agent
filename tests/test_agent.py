import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent import NewsAgent
from app.news_fetcher import Article


def _make_article(n: int) -> Article:
    return Article(
        id=f"id{n}",
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source="TestFeed",
        published_at=datetime(2026, 1, n + 1),
        content=f"Content of article {n}",
    )


@pytest.fixture
def mock_summarizer():
    summarizer = MagicMock()
    summarizer.enrich = lambda a: a
    return summarizer


@pytest.fixture
def agent(mock_summarizer):
    return NewsAgent(
        feeds=[],
        summarizer=mock_summarizer,
        redis_url="redis://localhost:6379",
        channel="test_channel",
        fetch_interval=60,
        max_articles=10,
    )


@pytest.mark.asyncio
async def test_new_articles_are_published(agent):
    articles = [_make_article(i) for i in range(3)]
    agent._redis = AsyncMock()
    agent._redis.publish = AsyncMock()
    agent._redis.setex = AsyncMock()
    agent._redis.lpush = AsyncMock()
    agent._redis.ltrim = AsyncMock()

    await agent._process_batch(articles)

    assert len(agent._seen_ids) == 3
    assert agent._redis.publish.call_count == 3


@pytest.mark.asyncio
async def test_seen_articles_not_republished(agent):
    article = _make_article(0)
    agent._seen_ids.add(article.id)
    agent._redis = AsyncMock()
    agent._redis.publish = AsyncMock()
    agent._redis.setex = AsyncMock()
    agent._redis.lpush = AsyncMock()
    agent._redis.ltrim = AsyncMock()

    await agent._process_batch([article])

    agent._redis.publish.assert_not_called()
