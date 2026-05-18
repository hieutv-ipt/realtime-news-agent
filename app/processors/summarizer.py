import json
import logging
from typing import Optional

from app.news_fetcher import Article
from app.processors.classifier import classify_by_keywords

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional news analyst. For each article provided, produce:
1. A concise 2-3 sentence summary
2. The primary category (politics, technology, business, science, health, sports, entertainment, world)
3. A sentiment score: positive, neutral, or negative
4. Three key entities (people, organizations, or locations) mentioned
5. An importance score from 1 (minor) to 5 (breaking/major)

Respond ONLY with valid JSON matching this schema:
{"summary": "...", "category": "...", "sentiment": "positive|neutral|negative", "entities": ["...", "...", "..."], "importance": 1}"""


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

    def analyze(self, article: Article) -> Optional[dict]:
        if self._client is None:
            return None
        import anthropic
        user_message = f"Title: {article.title}\n\nContent: {article.content or article.title}"
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
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
        if result:
            article.summary = result.get("summary")
            article.category = result.get("category")
            article.sentiment = result.get("sentiment")
            article.entities = result.get("entities", [])
            article.importance = int(result.get("importance", 1))
        else:
            # Fallback: keyword-based category, no LLM summary
            article.category = classify_by_keywords(f"{article.title} {article.content}")
        return article
