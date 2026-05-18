import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest/run", summary="Manually trigger one ingest cycle")
async def ingest_run(request: Request):
    """
    Fetch all configured RSS feeds, enrich new articles, store them.
    Returns per-cycle statistics.
    """
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="News agent not initialised")
    try:
        result = await agent.run_once()
    except Exception as exc:
        logger.error("Manual ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return result
