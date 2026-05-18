import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.news_fetcher import Article, _make_id, fetch_rss_feed


def test_make_id_deterministic():
    url = "https://example.com/article/1"
    assert _make_id(url) == _make_id(url)
    assert len(_make_id(url)) == 16


def test_article_to_dict():
    article = Article(
        id="abc123",
        title="Test Article",
        url="https://example.com",
        source="Test Source",
        published_at=datetime(2026, 1, 1, 12, 0, 0),
        content="Some content",
        summary="A summary",
        category="technology",
        sentiment="positive",
        entities=["OpenAI", "Google"],
        importance=3,
    )
    d = article.to_dict()
    assert d["id"] == "abc123"
    assert d["title"] == "Test Article"
    assert d["category"] == "technology"
    assert d["importance"] == 3
    assert d["entities"] == ["OpenAI", "Google"]


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Breaking: Something happened</title>
      <link>https://example.com/news/1</link>
      <description>Short description of the news.</description>
      <pubDate>Mon, 01 Jan 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
async def test_fetch_rss_feed_parses_items():
    mock_response = MagicMock()
    mock_response.text = AsyncMock(return_value=SAMPLE_RSS)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    # session.get() must return the context manager object directly (not a coroutine)
    mock_session.get = MagicMock(return_value=mock_response)

    articles = await fetch_rss_feed(mock_session, "https://fake.feed/rss", "TestSource")
    assert len(articles) == 1
    assert articles[0].title == "Breaking: Something happened"
    assert articles[0].source == "TestSource"
    assert articles[0].url == "https://example.com/news/1"
