import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent import NewsAgent
from app.news_fetcher import Article
from app.store import InMemoryStore


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
    s = MagicMock()
    s.enrich = lambda a: a
    return s


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
async def test_new_articles_are_published_to_redis(agent):
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


@pytest.mark.asyncio
async def test_redis_unavailable_does_not_crash(agent, monkeypatch):
    private_store = InMemoryStore()
    monkeypatch.setattr("app.agent.store", private_store)

    agent._redis = None
    articles = [_make_article(i) for i in range(2)]
    await agent._process_batch(articles)

    assert len(agent._seen_ids) == 2
    assert len(private_store.get_recent(10)) == 2


@pytest.mark.asyncio
async def test_redis_failure_mid_cycle_falls_back(agent, monkeypatch):
    private_store = InMemoryStore()
    monkeypatch.setattr("app.agent.store", private_store)

    failing_redis = AsyncMock()
    failing_redis.publish = AsyncMock(side_effect=ConnectionError("refused"))
    agent._redis = failing_redis

    await agent._process_batch([_make_article(0)])

    assert private_store.get("id0") is not None
    assert agent._redis is None


@pytest.mark.asyncio
async def test_run_once_returns_stats(agent, monkeypatch):
    private_store = InMemoryStore()
    monkeypatch.setattr("app.agent.store", private_store)
    agent._redis = None

    from app.news_fetcher import Article as _Article
    from datetime import datetime

    async def mock_fetch_tracked(session, url, name):
        return [_make_article(0), _make_article(1)], None

    monkeypatch.setattr("app.agent.fetch_rss_tracked", mock_fetch_tracked)
    # Give the agent one feed so run_once has something to iterate
    agent._feeds = [{"name": "TestFeed", "url": "https://fake.example/rss"}]

    result = await agent.run_once()

    assert result["sources_attempted"] == 1
    assert result["sources_failed"] == 0
    assert result["fetched_count"] == 2
    assert result["stored_count"] == 2
    assert result["skipped_duplicates"] == 0


@pytest.mark.asyncio
async def test_run_once_tracks_feed_failure(agent, monkeypatch):
    private_store = InMemoryStore()
    monkeypatch.setattr("app.agent.store", private_store)
    agent._redis = None

    async def mock_fetch_tracked_fail(session, url, name):
        return [], "Connection refused"

    monkeypatch.setattr("app.agent.fetch_rss_tracked", mock_fetch_tracked_fail)
    agent._feeds = [{"name": "BrokenFeed", "url": "https://broken.example/rss"}]

    result = await agent.run_once()

    assert result["sources_failed"] == 1
    assert len(result["errors"]) == 1
    assert "BrokenFeed" in result["errors"][0]
