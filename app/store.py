import asyncio
import json
from collections import OrderedDict, deque
from typing import Optional

_MAX = 200


class InMemoryStore:
    """In-process article store used when Redis is unavailable."""

    def __init__(self) -> None:
        self._articles: OrderedDict[str, dict] = OrderedDict()
        self._recent: deque[str] = deque(maxlen=_MAX)
        self._subscribers: list[asyncio.Queue] = []

    def put(self, article: dict) -> None:
        aid = article["id"]
        self._articles[aid] = article
        if aid in self._recent:
            # Move to front without duplicating
            tmp = [x for x in self._recent if x != aid]
            self._recent.clear()
            self._recent.extend(tmp)
        self._recent.appendleft(aid)
        # Evict articles that fell off the deque
        live = set(self._recent)
        for key in list(self._articles):
            if key not in live:
                del self._articles[key]
        payload = json.dumps(article)
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def get(self, article_id: str) -> Optional[dict]:
        return self._articles.get(article_id)

    def get_recent(self, limit: int = 20) -> list[dict]:
        ids = list(self._recent)[:limit]
        return [self._articles[i] for i in ids if i in self._articles]

    def subscribe(self) -> "asyncio.Queue[str]":
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[str]") -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass


# Module-level singleton shared by agent and routes
store = InMemoryStore()
