"""
API endpoint tests using a minimal FastAPI app (no startup event / no network / no Redis).
The test app shares the real route handlers but injects its own store and mock agent.
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router as core_router
from app.api.ingest import router as ingest_router
from app.api.digest import router as digest_router
from app.store import InMemoryStore

# ── Test application setup ────────────────────────────────────────────────────

_test_store = InMemoryStore()

# Patch module-level `store` references before any routes import them
import app.api.routes as _routes_mod
import app.api.digest as _digest_mod
_routes_mod.store = _test_store
_digest_mod.store = _test_store

_app = FastAPI()
_app.include_router(core_router, prefix="/api/v1")
_app.include_router(ingest_router, prefix="/api/v1")
_app.include_router(digest_router, prefix="/api/v1")

_mock_agent = MagicMock()
_mock_agent.run_once = AsyncMock(return_value={
    "fetched_count": 5,
    "stored_count": 3,
    "skipped_duplicates": 2,
    "sources_attempted": 4,
    "sources_failed": 0,
    "errors": [],
})
_app.state.agent = _mock_agent


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _article(n: int, category: str = "technology", importance: int = 5) -> dict:
    today = datetime.now(timezone.utc).isoformat()
    return {
        "id": f"t{n:04d}",
        "title": f"Test Article {n}: AI chip launch announced",
        "url": f"https://example.com/article/{n}",
        "source": "Test Source",
        "published_at": today,
        "content": f"Content of test article {n} about technology.",
        "summary": f"Summary of article {n}.",
        "category": category,
        "sentiment": "neutral",
        "entities": ["Entity A"],
        "importance": importance,
    }


@pytest.fixture(autouse=True)
def clear_store():
    _test_store.clear()
    yield
    _test_store.clear()


@pytest.fixture
def client():
    return TestClient(_app)


@pytest.fixture
def seeded_client():
    for i in range(5):
        _test_store.put(_article(i, "technology", importance=5))
    _test_store.put(_article(10, "finance", importance=8))
    _test_store.put(_article(11, "politics", importance=7))
    _test_store.put(_article(12, "vietnam", importance=4))
    return TestClient(_app)


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "redis" in body
    assert "in_memory_articles" in body


# ── /articles/recent ─────────────────────────────────────────────────────────

def test_recent_articles_empty(client):
    r = client.get("/api/v1/articles/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["articles"] == []
    assert body["count"] == 0


def test_recent_articles_returns_stored(seeded_client):
    r = seeded_client.get("/api/v1/articles/recent?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 5
    assert len(body["articles"]) == 5


def test_get_article_by_id(seeded_client):
    r = seeded_client.get("/api/v1/articles/t0000")
    assert r.status_code == 200
    assert r.json()["id"] == "t0000"


def test_get_article_not_found(client):
    r = client.get("/api/v1/articles/doesnotexist")
    assert r.status_code == 404


# ── /ingest/run ───────────────────────────────────────────────────────────────

def test_ingest_run_returns_stats(client):
    r = client.post("/api/v1/ingest/run")
    assert r.status_code == 200
    body = r.json()
    assert "fetched_count" in body
    assert "stored_count" in body
    assert "skipped_duplicates" in body
    assert "sources_attempted" in body
    assert "sources_failed" in body
    assert "errors" in body


def test_ingest_run_no_agent():
    _bare = FastAPI()
    _bare.include_router(ingest_router, prefix="/api/v1")
    # No agent on state
    with TestClient(_bare) as c:
        r = c.post("/api/v1/ingest/run")
    assert r.status_code == 503


# ── /digest/today ─────────────────────────────────────────────────────────────

def test_digest_today_empty(client):
    r = client.get("/api/v1/digest/today")
    assert r.status_code == 200
    body = r.json()
    assert "date" in body
    assert "categories" in body
    assert body["total_articles"] == 0


def test_digest_today_grouped_by_category(seeded_client):
    r = seeded_client.get("/api/v1/digest/today")
    assert r.status_code == 200
    body = r.json()
    cats = body["categories"]
    assert "technology" in cats
    assert "finance" in cats
    assert "politics" in cats


def test_digest_today_sorted_by_importance(seeded_client):
    r = seeded_client.get("/api/v1/digest/today")
    tech_articles = r.json()["categories"].get("technology", [])
    if len(tech_articles) > 1:
        scores = [a["importance_score"] for a in tech_articles]
        assert scores == sorted(scores, reverse=True)


def test_digest_today_fields(seeded_client):
    r = seeded_client.get("/api/v1/digest/today")
    cats = r.json()["categories"]
    for items in cats.values():
        for item in items:
            assert "title" in item
            assert "category" in item
            assert "importance_score" in item
            assert "source" in item
            assert "url" in item
            assert "published_at" in item


# ── /digest/category/{category} ───────────────────────────────────────────────

def test_digest_category_valid(seeded_client):
    r = seeded_client.get("/api/v1/digest/category/technology")
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "technology"
    assert body["count"] >= 1
    for item in body["articles"]:
        assert item["category"] == "technology"


def test_digest_category_invalid(client):
    r = client.get("/api/v1/digest/category/sports")
    assert r.status_code == 400
    assert "Invalid category" in r.json()["detail"]


def test_digest_category_other_is_valid(client):
    r = client.get("/api/v1/digest/category/other")
    assert r.status_code == 200


def test_digest_all_valid_categories(client):
    from app.processors.classifier import VALID_CATEGORIES
    for cat in VALID_CATEGORIES:
        r = client.get(f"/api/v1/digest/category/{cat}")
        assert r.status_code == 200, f"Expected 200 for /{cat}, got {r.status_code}"


# ── /ask ──────────────────────────────────────────────────────────────────────

def test_ask_fallback_no_articles(client):
    r = client.post("/api/v1/ask", json={"question": "Tin tức hôm nay là gì?", "language": "vi"})
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body
    assert body["mode"] == "fallback"


def test_ask_fallback_with_articles(seeded_client):
    r = seeded_client.post("/api/v1/ask", json={"question": "AI news today?", "language": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "fallback"
    assert body["article_count"] > 0
    assert len(body["sources"]) > 0


def test_ask_finance_disclaimer_added(seeded_client):
    r = seeded_client.post(
        "/api/v1/ask",
        json={"question": "tài chính kinh tế hôm nay thế nào?", "language": "vi"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "lời khuyên đầu tư" in body["answer"]


def test_ask_sources_contain_url(seeded_client):
    r = seeded_client.post("/api/v1/ask", json={"question": "technology news", "language": "en"})
    body = r.json()
    for src in body["sources"]:
        assert "url" in src
        assert "title" in src


# ── Redis unavailable does not crash core endpoints ───────────────────────────

def test_health_when_redis_down(client):
    # Redis is not running; health should still return 200 with redis=False
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["redis"] is False


def test_recent_articles_when_redis_down(seeded_client):
    r = seeded_client.get("/api/v1/articles/recent")
    assert r.status_code == 200
    assert r.json()["source"] == "memory"
