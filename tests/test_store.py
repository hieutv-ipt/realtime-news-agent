import asyncio
import pytest
from app.store import InMemoryStore


def _article(n: int) -> dict:
    return {"id": f"id{n}", "title": f"Article {n}", "url": f"https://example.com/{n}",
            "source": "test", "published_at": "2026-01-01T00:00:00",
            "content": "", "summary": None, "category": None,
            "sentiment": None, "entities": [], "importance": 1}


def test_put_and_get():
    s = InMemoryStore()
    a = _article(1)
    s.put(a)
    assert s.get("id1") == a


def test_get_missing_returns_none():
    s = InMemoryStore()
    assert s.get("nope") is None


def test_get_recent_order():
    s = InMemoryStore()
    for i in range(5):
        s.put(_article(i))
    recent = s.get_recent(3)
    assert len(recent) == 3
    # Most recently inserted should be first
    assert recent[0]["id"] == "id4"


def test_max_capacity():
    from app.store import _MAX
    s = InMemoryStore()
    for i in range(_MAX + 10):
        s.put(_article(i))
    assert len(s.get_recent(_MAX + 10)) == _MAX


def test_subscriber_receives_article():
    s = InMemoryStore()
    q = s.subscribe()
    s.put(_article(1))
    assert not q.empty()
    import json
    payload = json.loads(q.get_nowait())
    assert payload["id"] == "id1"


def test_unsubscribe_stops_delivery():
    s = InMemoryStore()
    q = s.subscribe()
    s.unsubscribe(q)
    s.put(_article(1))
    assert q.empty()


def test_duplicate_put_no_duplicate_in_recent():
    s = InMemoryStore()
    a = _article(1)
    s.put(a)
    s.put(a)
    recent = s.get_recent(10)
    ids = [r["id"] for r in recent]
    assert ids.count("id1") == 1
