# Realtime News Agent

A realtime news aggregation and analysis agent powered by **Claude (Anthropic)**, **FastAPI**, and **Redis**. The agent continuously fetches articles from RSS feeds, enriches each one using Claude (summary, category, sentiment, entities, importance), and streams the results to connected clients via WebSocket or Server-Sent Events.

## Architecture

```
RSS Feeds ──► NewsFetcher ──► ArticleSummarizer (Claude) ──► Redis pub/sub
                                                                    │
                                              ┌─────────────────────┤
                                              ▼                     ▼
                                         REST API            WebSocket / SSE
                                     GET /articles          ws://host/api/v1/ws
```

## Quick Start

### With Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
docker compose up --build
```

### Local development

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY

# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Run the app
python -m app.main
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/articles/recent?limit=20` | Latest analysed articles |
| GET | `/api/v1/articles/{id}` | Single article by ID |
| GET | `/api/v1/stream` | Server-Sent Events stream |
| WS  | `/api/v1/ws` | WebSocket stream |

### Example: Connect via WebSocket

```js
const ws = new WebSocket("ws://localhost:8000/api/v1/ws");
ws.onmessage = (event) => {
  const article = JSON.parse(event.data);
  console.log(article.title, article.category, article.importance);
};
```

### Example: Poll recent articles

```bash
curl http://localhost:8000/api/v1/articles/recent?limit=5 | jq .
```

## Article Schema

```json
{
  "id": "a1b2c3d4e5f6g7h8",
  "title": "...",
  "url": "https://...",
  "source": "BBC News",
  "published_at": "2026-05-18T10:00:00",
  "content": "...",
  "summary": "Two-sentence Claude-generated summary.",
  "category": "technology",
  "sentiment": "neutral",
  "entities": ["OpenAI", "Sam Altman", "San Francisco"],
  "importance": 4
}
```

## Configuration

All settings are controlled via environment variables (see [`.env.example`](.env.example)).

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | **required** | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `FETCH_INTERVAL_SECONDS` | `300` | How often to poll feeds |
| `MAX_ARTICLES_PER_FETCH` | `20` | Articles processed per cycle |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
realtime-news-agent/
├── app/
│   ├── main.py              # FastAPI app + agent lifecycle
│   ├── agent.py             # NewsAgent orchestrator
│   ├── news_fetcher.py      # RSS feed fetching & Article model
│   ├── api/
│   │   └── routes.py        # REST + WebSocket + SSE endpoints
│   └── processors/
│       ├── summarizer.py    # Claude-based article enrichment
│       └── classifier.py    # Keyword-based fallback classifier
├── config/
│   ├── settings.py          # Pydantic settings
│   └── config.yaml          # Static configuration
├── tests/
│   ├── test_agent.py
│   ├── test_news_fetcher.py
│   └── test_classifier.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
