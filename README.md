# Realtime News Agent

A realtime **news aggregation and intelligence agent** powered by [Claude (Anthropic)](https://www.anthropic.com/), FastAPI, and Redis. The agent continuously fetches RSS feeds, classifies every article by category, scores its importance, and streams the results to connected clients. A conversational `/ask` endpoint lets you query the news in Vietnamese or English.

Both **Redis** and **ANTHROPIC_API_KEY** are fully optional — the app runs in graceful fallback mode without either.

---

## Architecture

```
RSS Feeds (8 sources)
  ├── BBC World / Technology / Business
  ├── NYT Home
  ├── VnExpress Thời sự / Kinh doanh / Thế giới / Đời sống
  └── (more in config/config.yaml)
        │
        ▼
  NewsFetcher (aiohttp + feedparser)
        │
        ▼
  ArticleSummarizer
  ├── With ANTHROPIC_API_KEY → Claude enrichment (summary, category, sentiment, entities, importance)
  └── Without key           → Keyword classifier + importance scorer (fully offline)
        │
        ▼
  InMemoryStore ──(if Redis available)──► Redis pub/sub + cache
        │
  ┌─────┴──────────────────────────┐
  ▼                                ▼
REST API                     WebSocket / SSE
GET /articles/recent         ws://host/api/v1/ws
GET /digest/today
POST /ask
```

---

## Quick Start

### Option A — Docker Compose (Redis included)

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env (optional but recommended)
docker compose up --build
```

### Option B — Local (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env and optionally set ANTHROPIC_API_KEY

python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Option C — Local (Linux / macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the interactive docs at **http://127.0.0.1:8000/docs**

---

## Running Tests

```powershell
# Windows
.\.venv\Scripts\Activate.ps1
pytest
```

```bash
# Linux / macOS
source .venv/bin/activate
pytest
```

Expected output: **62 passed** (no Redis, no API key required).

---

## API Reference

All endpoints live under `/api/v1`.

### `GET /health`

```bash
curl http://localhost:8000/api/v1/health
```

```json
{"status": "ok", "redis": false, "in_memory_articles": 20}
```

---

### `GET /articles/recent?limit=20`

Returns the most recently ingested articles.

```bash
curl "http://localhost:8000/api/v1/articles/recent?limit=5"
```

---

### `GET /articles/{article_id}`

Fetch a single article by its 16-character SHA-256 ID.

```bash
curl http://localhost:8000/api/v1/articles/a1b2c3d4e5f6g7h8
```

---

### `POST /ingest/run`

Manually trigger one fetch-enrich-store cycle across all configured feeds.

```bash
curl -X POST http://localhost:8000/api/v1/ingest/run
```

```json
{
  "fetched_count": 18,
  "stored_count": 6,
  "skipped_duplicates": 12,
  "sources_attempted": 8,
  "sources_failed": 0,
  "errors": []
}
```

---

### `GET /digest/today`

Today's articles grouped by category, sorted by importance.

```bash
curl http://localhost:8000/api/v1/digest/today
```

```json
{
  "date": "2026-05-18",
  "total_articles": 14,
  "categories": {
    "vietnam": [...],
    "finance":  [...],
    "politics": [...]
  }
}
```

---

### `GET /digest/category/{category}?limit=20`

Top articles for one category. Valid categories:

| Category | Description |
|----------|-------------|
| `politics` | Government, elections, diplomacy, legislation |
| `finance` | Markets, crypto, central banks, earnings |
| `technology` | AI, cybersecurity, hardware, software |
| `world` | International conflicts, disasters, global crises |
| `vietnam` | Vietnam-specific news |
| `entertainment` | Sports, celebrity, film, music |
| `daily_life` | Health, education, travel, lifestyle |
| `other` | Everything else |

```bash
curl http://localhost:8000/api/v1/digest/category/finance
curl http://localhost:8000/api/v1/digest/category/vietnam
```

Returns HTTP 400 for unsupported categories.

---

### `POST /ask`

Ask a question about recent news in Vietnamese or English.

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hôm nay có tin gì quan trọng về tài chính và chính trị?", "language": "vi"}'
```

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the most important tech news today?", "language": "en"}'
```

**With ANTHROPIC_API_KEY**: Claude produces a natural-language answer with source citations.  
**Without key**: Returns a formatted list of the top matching articles.

> ⚠️ Finance answers always include the disclaimer:  
> *"Thông tin này chỉ nhằm mục đích tham khảo, không phải lời khuyên đầu tư."*

> Political content is always neutral and source-grounded — no persuasive framing.

---

### `GET /stream` (Server-Sent Events)

```javascript
const evtSource = new EventSource("http://localhost:8000/api/v1/stream");
evtSource.onmessage = (e) => console.log(JSON.parse(e.data));
```

### `WS /ws` (WebSocket)

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/ws");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## Article Schema

```json
{
  "id": "a1b2c3d4e5f6g7h8",
  "title": "Fed Raises Rates by 50 Basis Points",
  "url": "https://...",
  "source": "BBC Business",
  "published_at": "2026-05-18T10:00:00",
  "content": "...",
  "summary": "The Federal Reserve raised interest rates...",
  "category": "finance",
  "sentiment": "negative",
  "entities": ["Federal Reserve", "Jerome Powell", "Wall Street"],
  "importance": 8
}
```

### Importance Scale

| Score | Meaning |
|-------|---------|
| 9–10 | Breaking: election result, rate decision, market crash, major disaster, head-of-state resignation |
| 7–8  | Major policy, key geopolitical event, significant earnings |
| 4–6  | Normal newsworthy public-interest story |
| 1–3  | Soft news, minor update |

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(empty)* | If set, enables Claude enrichment |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection (optional) |
| `FETCH_INTERVAL_SECONDS` | `300` | How often to auto-fetch feeds |
| `MAX_ARTICLES_PER_FETCH` | `20` | Articles processed per cycle |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

### Adding / Removing Feeds

Edit [`config/config.yaml`](config/config.yaml):

```yaml
sources:
  rss:
    - name: My Custom Feed
      url: https://example.com/feed.rss
```

The feeds are loaded at startup. Remove the Reuters line entirely — it is commented out by default.

---

## Fallback Modes

| Component | Missing | Behaviour |
|-----------|---------|-----------|
| Redis | Not running | `InMemoryStore` used for all storage and pub/sub |
| `ANTHROPIC_API_KEY` | Not set | Keyword-based classifier + importance scorer (offline) |
| Both missing | — | App fully functional, no external services needed |

---

## Project Structure

```
realtime-news-agent/
├── app/
│   ├── main.py                  # FastAPI app + agent lifecycle
│   ├── agent.py                 # NewsAgent orchestrator
│   ├── news_fetcher.py          # Async RSS fetcher, Article dataclass
│   ├── store.py                 # InMemoryStore (Redis fallback)
│   ├── api/
│   │   ├── routes.py            # /health, /articles/*, /stream, /ws
│   │   ├── ingest.py            # POST /ingest/run
│   │   └── digest.py            # GET /digest/today, /digest/category, POST /ask
│   └── processors/
│       ├── classifier.py        # Keyword classifier + importance scorer
│       └── summarizer.py        # Claude-based enrichment
├── config/
│   ├── settings.py              # Pydantic settings (env-driven)
│   └── config.yaml              # Feed list + static config
├── tests/
│   ├── test_api.py              # API endpoint tests (62 tests)
│   ├── test_agent.py
│   ├── test_classifier.py
│   ├── test_news_fetcher.py
│   └── test_store.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Disclaimers

- **No financial advice**: All finance-category answers include the disclaimer *"Thông tin này chỉ nhằm mục đích tham khảo, không phải lời khuyên đầu tư."*
- **Political neutrality**: Political summaries are factual and source-grounded. No persuasive or propaganda framing.
- **No API key hardcoded**: All credentials must be supplied via environment variables.
