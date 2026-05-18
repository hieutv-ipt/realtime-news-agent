import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.store import store
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_REDIS_CONNECT_TIMEOUT = 3


async def _get_redis() -> Optional[aioredis.Redis]:
    """Return a connected Redis client, or None if Redis is unavailable."""
    try:
        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
        )
        await client.ping()
        return client
    except Exception as exc:
        logger.debug("Redis not reachable for request (%s)", exc)
        return None


@router.get("/health")
async def health():
    redis = await _get_redis()
    redis_ok = redis is not None
    if redis:
        await redis.aclose()
    return {"status": "ok", "redis": redis_ok, "in_memory_articles": len(store.get_recent(200))}


@router.get("/articles/recent")
async def recent_articles(limit: int = 20):
    redis = await _get_redis()
    if redis:
        try:
            ids = await redis.lrange("articles:recent", 0, limit - 1)
            if ids:
                pipe = redis.pipeline()
                for aid in ids:
                    pipe.get(f"article:{aid}")
                raw_list = await pipe.execute()
                await redis.aclose()
                articles = [json.loads(r) for r in raw_list if r]
                return {"articles": articles, "count": len(articles), "source": "redis"}
        except Exception as exc:
            logger.warning("Redis read failed (%s), falling back to in-memory store", exc)
        finally:
            try:
                await redis.aclose()
            except Exception:
                pass

    articles = store.get_recent(limit)
    return {"articles": articles, "count": len(articles), "source": "memory"}


@router.get("/articles/{article_id}")
async def get_article(article_id: str):
    redis = await _get_redis()
    if redis:
        try:
            raw = await redis.get(f"article:{article_id}")
            await redis.aclose()
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Redis read failed (%s), falling back to in-memory store", exc)
        finally:
            try:
                await redis.aclose()
            except Exception:
                pass

    article = store.get(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


async def _redis_sse(redis: aioredis.Redis) -> AsyncGenerator[str, None]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.redis_channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    except (asyncio.CancelledError, Exception):
        pass
    finally:
        try:
            await pubsub.unsubscribe(settings.redis_channel)
            await pubsub.aclose()
        except Exception:
            pass


async def _memory_sse() -> AsyncGenerator[str, None]:
    q = store.subscribe()
    try:
        while True:
            payload = await q.get()
            yield f"data: {payload}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        store.unsubscribe(q)


@router.get("/stream")
async def stream_articles():
    redis = await _get_redis()
    if redis:
        return StreamingResponse(
            _redis_sse(redis),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return StreamingResponse(
        _memory_sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    redis = await _get_redis()

    if redis:
        pubsub = redis.pubsub()
        await pubsub.subscribe(settings.redis_channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except WebSocketDisconnect:
            pass
        finally:
            try:
                await pubsub.unsubscribe(settings.redis_channel)
                await pubsub.aclose()
                await redis.aclose()
            except Exception:
                pass
    else:
        q = store.subscribe()
        try:
            while True:
                payload = await q.get()
                await websocket.send_text(payload)
        except WebSocketDisconnect:
            pass
        finally:
            store.unsubscribe(q)
