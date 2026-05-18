import re
from typing import Optional

KEYWORD_MAP = {
    "politics": ["election", "government", "senate", "congress", "president", "minister", "vote", "policy"],
    "technology": ["ai", "software", "startup", "tech", "robot", "cloud", "cyber", "chip", "semiconductor"],
    "business": ["market", "stock", "economy", "trade", "company", "ceo", "revenue", "profit", "merger"],
    "science": ["research", "study", "discovery", "nasa", "space", "climate", "fossil", "genome"],
    "health": ["hospital", "vaccine", "disease", "drug", "fda", "cancer", "mental health", "pandemic"],
    "sports": ["championship", "tournament", "nba", "nfl", "fifa", "olympic", "athlete", "match"],
    "entertainment": ["movie", "music", "actor", "award", "celebrity", "film", "album", "streaming"],
    "world": ["war", "crisis", "un", "nato", "refugee", "diplomatic", "sanction"],
}


def classify_by_keywords(text: str) -> Optional[str]:
    lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in KEYWORD_MAP.items():
        scores[category] = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", lower))
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else None
