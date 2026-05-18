import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.processors.classifier import VALID_CATEGORIES
from app.store import store
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_FINANCE_DISCLAIMER = (
    "Thông tin này chỉ nhằm mục đích tham khảo, không phải lời khuyên đầu tư."
)

# Vietnamese question → category hints for relevance filtering
_VI_CATEGORY_HINTS: dict[str, list[str]] = {
    "politics": ["chính trị", "chính phủ", "bầu cử", "quốc hội", "tổng thống", "thủ tướng",
                 "politics", "government", "election", "parliament"],
    "finance": ["tài chính", "chứng khoán", "kinh tế", "lãi suất", "tiền tệ", "đầu tư",
                "finance", "stock", "economy", "crypto", "interest rate", "market"],
    "vietnam": ["việt nam", "hà nội", "hcm", "hồ chí minh", "vietnam", "hanoi"],
    "technology": ["công nghệ", "ai", "trí tuệ", "phần mềm", "technology", "artificial intelligence"],
    "world": ["thế giới", "quốc tế", "chiến tranh", "world", "international", "war"],
    "entertainment": ["giải trí", "thể thao", "bóng đá", "âm nhạc", "entertainment", "sport", "football"],
    "daily_life": ["sức khỏe", "giáo dục", "đời sống", "health", "education", "lifestyle"],
}


def _parse_pub_date(s: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _to_digest_item(a: dict) -> dict:
    return {
        "title": a.get("title", ""),
        "summary": a.get("summary"),
        "category": a.get("category") or "other",
        "sentiment": a.get("sentiment"),
        "importance_score": a.get("importance", 1),
        "source": a.get("source", ""),
        "url": a.get("url", ""),
        "published_at": a.get("published_at", ""),
    }


def _sort_digest(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: (-x["importance_score"], x["published_at"]), reverse=False)


# ── Digest endpoints ──────────────────────────────────────────────────────────

@router.get("/digest/today", summary="Today's top articles grouped by category")
async def digest_today():
    articles = store.get_recent(200)
    today = datetime.now(timezone.utc).date()
    grouped: dict[str, list[dict]] = {}
    for a in articles:
        pub = _parse_pub_date(a.get("published_at", ""))
        if pub and pub.date() != today:
            continue
        cat = a.get("category") or "other"
        grouped.setdefault(cat, []).append(_to_digest_item(a))
    for cat in grouped:
        grouped[cat] = _sort_digest(grouped[cat])
    total = sum(len(v) for v in grouped.values())
    return {"date": today.isoformat(), "total_articles": total, "categories": grouped}


@router.get("/digest/category/{category}", summary="Top recent articles for one category")
async def digest_category(category: str, limit: int = 20):
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Valid: {', '.join(VALID_CATEGORIES)}",
        )
    articles = store.get_recent(200)
    filtered = [_to_digest_item(a) for a in articles if (a.get("category") or "other") == category]
    filtered = _sort_digest(filtered)[:limit]
    return {"category": category, "articles": filtered, "count": len(filtered)}


# ── Ask endpoint ──────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    language: str = "vi"


def _find_relevant(articles: list[dict], question: str) -> list[dict]:
    q = question.lower()
    target_cats: list[str] = []
    for cat, hints in _VI_CATEGORY_HINTS.items():
        if any(h in q for h in hints):
            target_cats.append(cat)
    if target_cats:
        relevant = [a for a in articles if (a.get("category") or "other") in target_cats]
    else:
        relevant = list(articles)
    relevant.sort(key=lambda x: -x.get("importance", 1))
    return relevant


def _fallback_answer(question: str, articles: list[dict], language: str) -> str:
    if not articles:
        if language == "vi":
            return "Không tìm thấy tin tức liên quan. Vui lòng chạy /api/v1/ingest/run để tải tin mới."
        return "No relevant news found. Try running /api/v1/ingest/run to fetch articles."

    top = articles[:5]
    if language == "vi":
        lines = [f"Dưới đây là {len(top)} tin tức liên quan đến câu hỏi của bạn:\n"]
        for i, a in enumerate(top, 1):
            body = a.get("summary") or a.get("content", "")[:200] or a["title"]
            lines.append(f"{i}. **{a['title']}** ({a['source']})\n   {body}\n   Nguồn: {a['url']}\n")
        lines.append("_(Chú thích: Tóm tắt tự động — không có phân tích AI.)_")
    else:
        lines = [f"Here are {len(top)} relevant articles:\n"]
        for i, a in enumerate(top, 1):
            body = a.get("summary") or a.get("content", "")[:200] or a["title"]
            lines.append(f"{i}. **{a['title']}** ({a['source']})\n   {body}\n   Source: {a['url']}\n")
        lines.append("_(Note: automatic summary — no AI analysis.)_")
    return "\n".join(lines)


async def _claude_answer(question: str, articles: list[dict], language: str) -> str:
    import anthropic

    lang_instr = (
        "Trả lời bằng tiếng Việt. Trích dẫn nguồn bằng tên bài báo và URL."
        if language == "vi"
        else "Answer in English. Cite sources by article title and URL."
    )
    context = "\n\n".join(
        f"[{i + 1}] {a['title']} (Nguồn: {a['source']}, URL: {a['url']})\n"
        f"{a.get('summary') or a.get('content', '')[:300]}"
        for i, a in enumerate(articles[:10])
    )
    prompt = (
        f"Bạn là trợ lý phân tích tin tức. Hãy trả lời câu hỏi của người dùng "
        f"DỰA TRÊN các bài báo được cung cấp dưới đây.\n\n"
        f"Nguyên tắc:\n"
        f"- {lang_instr}\n"
        f"- Với chủ đề chính trị: trung lập, khách quan, không thuyết phục hay tuyên truyền.\n"
        f"- Với chủ đề tài chính: luôn thêm tuyên bố miễn trách nhiệm đầu tư.\n"
        f"- Nếu bài báo không đủ để trả lời, hãy nói rõ.\n\n"
        f"Bài báo:\n{context}\n\n"
        f"Câu hỏi: {question}"
    )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ),
    )
    return response.content[0].text


@router.post("/ask", summary="Ask a question about recent news")
async def ask(body: AskRequest):
    articles = store.get_recent(100)
    relevant = _find_relevant(articles, body.question)

    categories_hit = {a.get("category") for a in relevant}
    needs_finance_disclaimer = "finance" in categories_hit
    needs_politics_note = "politics" in categories_hit

    if settings.anthropic_api_key:
        try:
            answer = await _claude_answer(body.question, relevant, body.language)
            mode = "llm"
        except Exception as exc:
            logger.warning("Claude call failed (%s), using fallback", exc)
            answer = _fallback_answer(body.question, relevant, body.language)
            mode = "fallback"
    else:
        answer = _fallback_answer(body.question, relevant, body.language)
        mode = "fallback"

    if needs_finance_disclaimer and _FINANCE_DISCLAIMER not in answer:
        answer += f"\n\n⚠️ {_FINANCE_DISCLAIMER}"
    if needs_politics_note and mode == "fallback":
        note = (
            "\n\n_(Lưu ý: Thông tin chính trị được tổng hợp từ nguồn báo chí, không mang tính tuyên truyền.)_"
            if body.language == "vi"
            else "\n\n_(Note: Political content is aggregated from news sources and is not persuasive.)_"
        )
        answer += note

    sources = [
        {"title": a.get("title", ""), "url": a.get("url", ""), "source": a.get("source", "")}
        for a in relevant[:10]
    ]
    return {
        "answer": answer,
        "sources": sources,
        "article_count": len(relevant),
        "mode": mode,
    }
