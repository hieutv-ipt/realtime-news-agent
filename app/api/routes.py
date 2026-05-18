import asyncio
import json
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_redis() -> aioredis.Redis:
    client = await aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/articles/recent")
async def recent_articles(limit: int = 20, redis: aioredis.Redis = Depends(get_redis)):
    ids = await redis.lrange("articles:recent", 0, limit - 1)
    if not ids:
        return {"articles": []}
    pipe = redis.pipeline()
    for article_id in ids:
        pipe.get(f"article:{article_id}")
    raw_list = await pipe.execute()
    articles = [json.loads(r) for r in raw_list if r]
    return {"articles": articles, "count": len(articles)}


@router.get("/articles/{article_id}")
async def get_article(article_id: str, redis: aioredis.Redis = Depends(get_redis)):
    raw = await redis.get(f"article:{article_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Article not found")
    return json.loads(raw)


async def _sse_generator(redis: aioredis.Redis) -> AsyncGenerator[str, None]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.redis_channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield f"data: {message['data']}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(settings.redis_channel)
        await pubsub.aclose()


@router.get("/stream")
async def stream_articles(redis: aioredis.Redis = Depends(get_redis)):
    return StreamingResponse(
        _sse_generator(redis),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    await websocket.accept()
    redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(settings.redis_channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(settings.redis_channel)
        await pubsub.aclose()
        await redis.aclose()
