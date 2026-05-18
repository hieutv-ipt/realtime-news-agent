import json
import logging
from typing import Optional

from app.news_fetcher import Article
from app.processors.classifier import VALID_CATEGORIES, classify_by_keywords, score_importance

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional news analyst. For each article, produce a JSON object with:
1. "summary"  — 2-3 sentence factual summary in English
2. "category" — exactly one of: politics, finance, daily_life, technology, world, vietnam, entertainment, other
3. "sentiment" — exactly one of: positive, neutral, negative
4. "entities" — list of up to 3 key entities (people, orgs, places)
5. "importance" — integer 1-10:
   9-10: war escalation, election result, central-bank rate decision, market crash, major disaster, head-of-state resignation
   7-8:  major policy/geopolitical event, significant earnings/economic data
   4-6:  normal newsworthy public-interest story
   1-3:  soft news, minor update

Rules:
- Political content must be neutral, factual, and source-grounded — no persuasive framing.
- Never invent facts not in the provided text.
- Respond ONLY with valid JSON, no extra text.

Schema:
{"summary": "...", "category": "politics", "sentiment": "neutral", "entities": ["A", "B", "C"], "importance": 5}"""


class ArticleSummarizer:
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6"):
        self._model = model
        self._client = None
        if api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            except Exception as exc:
                logger.warning("Could not initialise Anthropic client: %s", exc)

    @property
    def has_llm(self) -> bool:
        return self._client is not None

    def analyze(self, article: Article) -> Optional[dict]:
        if self._client is None:
            return None
        import anthropic
        user_msg = f"Title: {article.title}\n\nContent: {article.content or article.title}"
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            )
            text = response.content[0].text.strip()
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Non-JSON response for article %s", article.id)
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
        return None

    def enrich(self, article: Article) -> Article:
        result = self.analyze(article)
        combined = f"{article.title} {article.content}"
        if result:
            cat = result.get("category", "other")
            if cat not in VALID_CATEGORIES:
                cat = classify_by_keywords(combined)
            article.summary = result.get("summary")
            article.category = cat
            article.sentiment = result.get("sentiment", "neutral")
            article.entities = result.get("entities", [])
            raw_imp = result.get("importance", 1)
            # Keep deterministic score as floor so LLM can't return 1 for major news
            floor = score_importance(combined, cat)
            article.importance = max(int(raw_imp), floor)
        else:
            # Keyword-only fallback
            article.category = classify_by_keywords(combined)
            article.importance = score_importance(combined, article.category)
        return article
