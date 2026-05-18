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
_POLITICS_NOTE_VI = (
    "Thông tin chính trị được tổng hợp từ nguồn báo chí, không nhằm định hướng quan điểm."
)
_POLITICS_NOTE_EN = (
    "Political content is aggregated from news sources and does not represent editorial opinion."
)

# ── Category labels ───────────────────────────────────────────────────────────

_CAT_HEADER_VI = {
    "finance":       "💰 Tài chính",
    "politics":      "🏛️ Chính trị",
    "world":         "🌍 Thế giới",
    "vietnam":       "🇻🇳 Việt Nam",
    "technology":    "💻 Công nghệ",
    "entertainment": "🎬 Giải trí",
    "daily_life":    "🏠 Đời sống",
    "other":         "📰 Tin khác",
}
_CAT_HEADER_EN = {
    "finance":       "💰 Finance",
    "politics":      "🏛️ Politics",
    "world":         "🌍 World",
    "vietnam":       "🇻🇳 Vietnam",
    "technology":    "💻 Technology",
    "entertainment": "🎬 Entertainment",
    "daily_life":    "🏠 Daily Life",
    "other":         "📰 Other",
}
_CAT_LABEL_VI = {
    "finance": "tài chính", "politics": "chính trị", "world": "thế giới",
    "vietnam": "Việt Nam", "technology": "công nghệ",
    "entertainment": "giải trí", "daily_life": "đời sống", "other": "khác",
}

# ── Topic detection: question → target categories ────────────────────────────

# Keyword hints used only for detecting what the *question is asking about*.
# Separate from the article classifier's keyword map.
_TOPIC_HINTS: dict[str, list[str]] = {
    "finance": [
        "tài chính", "chứng khoán", "kinh tế", "lãi suất", "tiền tệ", "đầu tư",
        "giá dầu", "lạm phát", "ngân hàng", "cổ phiếu", "vàng", "crypto",
        "finance", "stock", "economy", "interest rate", "inflation", "oil price",
        "gold price", "central bank", "earnings", "gdp", "recession", "bitcoin",
        "market", "investment",
    ],
    "politics": [
        "chính trị", "chính phủ", "bầu cử", "quốc hội", "tổng thống", "thủ tướng",
        "ngoại giao", "chính sách", "luật pháp", "đảng phái", "nghị viện", "xung đột",
        "politics", "government", "election", "parliament", "president",
        "prime minister", "policy", "law", "diplomacy", "conflict", "sanctions",
        "treaty", "coup", "war",
    ],
    "world": [
        "thế giới", "quốc tế", "chiến tranh", "khủng hoảng toàn cầu",
        "world news", "international news", "global", "foreign affairs",
    ],
    "vietnam": [
        "việt nam", "hà nội", "hồ chí minh", "hcm", "đà nẵng",
        "vietnam", "hanoi",
    ],
    "technology": [
        "công nghệ", "trí tuệ nhân tạo", "phần mềm", "chip bán dẫn", "an ninh mạng",
        "technology", "artificial intelligence", " ai ", "cybersecurity",
        "semiconductor", "software", "startup", "tech",
    ],
    "entertainment": [
        "giải trí", "thể thao", "bóng đá", "âm nhạc", "phim ảnh", "ca sĩ", "diễn viên",
        "entertainment", "celebrity", "music", "movie", "sport", "football", "film",
    ],
    "daily_life": [
        "đời sống", "sức khỏe", "giáo dục", "du lịch", "tiêu dùng", "thời tiết",
        "daily life", "lifestyle", "health", "education", "travel", "consumer",
    ],
}

# When the user asks about politics, world/vietnam articles are also relevant
# because much political news is classified there.
_POLITICS_EXPANDS_TO = frozenset({"politics", "world", "vietnam"})


def _detect_topics(question: str) -> frozenset[str]:
    """Return the set of categories the question is asking about (empty = unspecified)."""
    q = question.lower()
    detected: set[str] = set()
    for cat, hints in _TOPIC_HINTS.items():
        if any(h in q for h in hints):
            detected.add(cat)
    if "politics" in detected:
        detected.update(_POLITICS_EXPANDS_TO)
    return frozenset(detected)


# ── Article helpers ───────────────────────────────────────────────────────────

def _parse_pub_date(s: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _pub_ts(s: str) -> float:
    dt = _parse_pub_date(s)
    return dt.timestamp() if dt else 0.0


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


# ── Relevance filtering ───────────────────────────────────────────────────────

def _find_relevant(
    articles: list[dict],
    question: str,
    max_results: int = 5,
) -> tuple[list[dict], frozenset[str]]:
    """
    Return (relevant_articles, target_categories).

    - If the question maps to specific categories, only those articles are returned.
    - If nothing detected, return top-N by importance (no category filtering).
    - Result is sorted by importance desc, then published_at desc.
    """
    target_cats = _detect_topics(question)

    if target_cats:
        relevant = [a for a in articles if (a.get("category") or "other") in target_cats]
    else:
        relevant = list(articles)

    relevant.sort(key=lambda x: (-x.get("importance", 1), -_pub_ts(x.get("published_at", ""))))
    return relevant[:max_results], target_cats


# ── Fallback answer formatting ────────────────────────────────────────────────

def _no_match_message(target_cats: frozenset[str], language: str) -> str:
    if language == "vi":
        cat_labels = ", ".join(_CAT_LABEL_VI.get(c, c) for c in sorted(target_cats))
        return (
            f"Hiện chưa có tin tức phù hợp"
            + (f" về chủ đề: {cat_labels}" if cat_labels else "")
            + ".\n\nVui lòng thử:\n"
            "• Chạy **POST /api/v1/ingest/run** để tải tin mới.\n"
            "• Bổ sung nguồn RSS trong **config/config.yaml**."
        )
    cat_labels = ", ".join(sorted(target_cats))
    return (
        f"No matching news found"
        + (f" for topics: {cat_labels}" if cat_labels else "")
        + ".\n\nTry:\n"
        "• Run **POST /api/v1/ingest/run** to fetch new articles.\n"
        "• Add more RSS feeds in **config/config.yaml**."
    )


def _format_fallback(
    articles: list[dict],
    target_cats: frozenset[str],
    language: str,
) -> str:
    if not articles:
        body = _no_match_message(target_cats, language)
    else:
        # Group by category, preserving importance-sorted order within groups
        grouped: dict[str, list[dict]] = {}
        for a in articles:
            cat = a.get("category") or "other"
            grouped.setdefault(cat, []).append(a)

        headers = _CAT_HEADER_VI if language == "vi" else _CAT_HEADER_EN
        source_label = "Nguồn" if language == "vi" else "Source"
        intro = "**Dưới đây là các tin đáng chú ý:**" if language == "vi" else "**Here are the most relevant articles:**"

        lines = [intro]
        for cat, items in grouped.items():
            lines.append(f"\n### {headers.get(cat, cat.title())}")
            for a in items:
                summary = a.get("summary") or a.get("content", "")[:200] or a["title"]
                imp = a.get("importance", 1)
                lines.append(
                    f"\n• **{a['title']}** _(Độ quan trọng: {imp}/10)_\n"
                    f"  {summary}\n"
                    f"  📌 {source_label}: [{a['source']}]({a['url']})"
                )
        note = "_(Tóm tắt tự động — không có phân tích AI.)_" if language == "vi" \
               else "_(Automatic summary — no AI analysis.)_"
        lines.append(f"\n{note}")
        body = "\n".join(lines)

    # Disclaimers
    cats_hit = {a.get("category") for a in articles}
    if "finance" in cats_hit or "finance" in target_cats:
        body += f"\n\n⚠️ {_FINANCE_DISCLAIMER}"
    if cats_hit & {"politics", "world", "vietnam"} or target_cats & {"politics", "world", "vietnam"}:
        note = _POLITICS_NOTE_VI if language == "vi" else _POLITICS_NOTE_EN
        body += f"\n\n_{note}_"
    return body


# ── Claude answer ─────────────────────────────────────────────────────────────

async def _claude_answer(
    question: str,
    articles: list[dict],
    language: str,
    target_cats: frozenset[str],
) -> str:
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
    has_finance = "finance" in target_cats or any(a.get("category") == "finance" for a in articles)
    has_politics = bool(target_cats & {"politics", "world", "vietnam"})

    rules = [f"- {lang_instr}"]
    if has_politics:
        rules.append("- Với chủ đề chính trị: trung lập, khách quan, không thuyết phục hay tuyên truyền.")
    if has_finance:
        rules.append(f'- Với chủ đề tài chính: luôn thêm câu: "{_FINANCE_DISCLAIMER}"')
    rules.append("- Nếu bài báo không đủ để trả lời, hãy nói rõ.")

    prompt = (
        "Bạn là trợ lý phân tích tin tức. Hãy trả lời câu hỏi của người dùng "
        "DỰA TRÊN các bài báo được cung cấp dưới đây.\n\n"
        f"Nguyên tắc:\n{chr(10).join(rules)}\n\n"
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


@router.post("/ask", summary="Ask a question about recent news")
async def ask(body: AskRequest):
    articles = store.get_recent(100)
    relevant, target_cats = _find_relevant(articles, body.question)

    if settings.anthropic_api_key:
        try:
            answer = await _claude_answer(body.question, relevant, body.language, target_cats)
            mode = "llm"
        except Exception as exc:
            logger.warning("Claude call failed (%s), using fallback", exc)
            answer = _format_fallback(relevant, target_cats, body.language)
            mode = "fallback"
    else:
        answer = _format_fallback(relevant, target_cats, body.language)
        mode = "fallback"

    sources = [
        {
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "source": a.get("source", ""),
            "category": a.get("category") or "other",
            "importance_score": a.get("importance", 1),
        }
        for a in relevant
    ]
    return {
        "answer": answer,
        "sources": sources,
        "article_count": len(relevant),
        "topics_detected": sorted(target_cats),
        "mode": mode,
    }
