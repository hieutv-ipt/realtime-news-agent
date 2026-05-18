import re

VALID_CATEGORIES = (
    "politics", "finance", "daily_life", "technology",
    "world", "vietnam", "entertainment", "other",
)

# Order matters: more-specific categories listed first so ties break in their favour.
_KEYWORD_MAP: dict[str, list[str]] = {
    "vietnam": [
        "vietnam", "vietnamese", "viet nam", "hanoi", "ho chi minh", "hcmc", "saigon",
        "tuoi tre", "thanh nien", "vnexpress", "vnd", "dong currency",
        "mekong", "da nang", "nha trang", "hai phong", "hue city",
        "national assembly of vietnam", "communist party of vietnam",
        "ministry of finance vietnam", "ministry of health vietnam",
    ],
    "politics": [
        "election", "government", "senate", "congress", "parliament", "president",
        "prime minister", "minister", "ministry", "vote", "policy", "legislation",
        "sanctions", "diplomacy", "diplomatic", "treaty", "bilateral",
        "coup", "protest", "democracy", "authoritarian", "referendum", "constitution",
        "foreign minister", "secretary of state", "white house", "kremlin",
        "european commission", "united nations", "nato", "summit",
        "political party", "cabinet", "governor", "mayor", "senator",
    ],
    "finance": [
        "stock", "crypto", "bitcoin", "ethereum", "central bank", "interest rate",
        "inflation", "exchange rate", "earnings", "oil price", "gold price",
        "bond market", "commodity", "gdp", "recession", "federal reserve", "fed rate",
        "ecb", "imf ", "world bank", "ipo", "hedge fund", "wall street", "nasdaq",
        "dow jones", "s&p 500", "forex", "trade deficit", "fiscal",
        "monetary policy", "rate hike", "rate cut", "quantitative easing",
        "treasury yield", "debt ceiling", "economic growth", "unemployment rate",
        "cpi", "ppi", "earnings per share", "market cap", "venture capital",
    ],
    "technology": [
        "artificial intelligence", " ai ", "machine learning", "deep learning",
        "openai", "chatgpt", "gemini", "claude ai", "llm", "generative ai",
        "cyberattack", "cybersecurity", "hacking", "ransomware", "malware",
        "cloud computing", "semiconductor", "nvidia", "intel chip", "apple silicon",
        "google", "microsoft", "meta platforms", "amazon aws",
        "startup funding", "tech layoffs", "data center", "5g network",
        "quantum computing", "blockchain", "electric vehicle", "self-driving",
        "chip shortage", "software", "smartphone launch",
    ],
    "world": [
        "war", "conflict", "military", "troops", "missile strike", "bombing", "ceasefire",
        "humanitarian crisis", "refugee", "invasion", "occupation",
        "ukraine", "russia", "israel", "gaza", "taiwan strait", "iran nuclear",
        "north korea", "middle east", "climate change", "natural disaster",
        "earthquake", "hurricane", "tsunami", "famine", "global crisis",
        "international relations", "foreign affairs", "geopolitical",
    ],
    "entertainment": [
        "movie", "film release", "music album", "concert", "actor", "actress",
        "celebrity", "oscar", "grammy", "billboard chart", "netflix",
        "spotify", "youtube", "tiktok", "influencer", "pop star",
        "football", "soccer", "basketball", "tennis", "golf", "olympics",
        "world cup", "championship", "tournament", "fifa", "nba", "nfl",
        "premier league", "athlete", "stadium", "esport", "video game",
    ],
    "daily_life": [
        "public health", "hospital", "vaccine", "disease outbreak", "drug approval",
        "fda approval", "cancer treatment", "mental health", "pandemic",
        "education reform", "school", "university enrollment", "student loan",
        "travel ban", "airline", "flight", "hotel", "visa",
        "cost of living", "housing market", "rent prices", "consumer prices",
        "food safety", "weather forecast", "traffic", "public transport",
        "environment", "pollution", "recycling", "energy bill",
    ],
}

# ── Importance scoring ────────────────────────────────────────────────────────

_HIGH_IMPACT_KW = [
    "war escalat", "nuclear strike", "nuclear threat", "invasion",
    "election result", "election victory", "wins election",
    "rate cut", "rate hike", "emergency rate", "market crash", "stock market crash",
    "bank collapse", "bank run", "financial crisis",
    "president resign", "prime minister resign", "resign amid", "coup",
    "assassination", "major earthquake", "magnitude 7", "magnitude 8",
    "major hurricane", "category 5", "major cyberattack", "critical infrastructure attack",
    "breaking:", "breaking news", "urgent:", "flash:", "just in:",
]

_MED_HIGH_IMPACT_KW = [
    "central bank decision", "federal reserve", "rate decision", "basis points",
    "earnings beat", "earnings miss", "profit warning", "quarterly results",
    "major policy", "landmark legislation", "key legislation",
    "military escalat", "ceasefire deal", "peace deal", "trade deal",
    "oil price surge", "oil price crash", "inflation surges", "gdp contracts",
    "record high", "record low", "all-time high", "all-time low",
    "pandemic declared", "outbreak declared", "state of emergency",
    "sanctions imposed", "trade war", "tariff hike",
]

_MED_IMPACT_KW = [
    "announced", "launches", "unveil", "report shows", "study finds",
    "deal signed", "merger", "acquisition", "investigation opens",
    "arrested", "charged", "indicted", "protest", "reform proposed",
    "regulation update", "new law", "policy update", "summit held",
    "conference", "agreement reached", "joint statement",
]

_CATEGORY_BASE_SCORE = {
    "politics": 4, "finance": 4, "world": 4,
    "technology": 3, "vietnam": 3,
    "entertainment": 2, "daily_life": 2, "other": 1,
}


def classify_by_keywords(text: str) -> str:
    """Return the best-matching category. Never returns None; falls back to 'other'."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for category, keywords in _KEYWORD_MAP.items():
        raw = sum(1 for kw in keywords if kw in lower)
        # Vietnam gets a 2× multiplier — it's the most specific bucket
        scores[category] = raw * 2 if category == "vietnam" else raw
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "other"


def score_importance(text: str, category: str = "other") -> int:
    """Return importance 1-10 based on headline / content keywords."""
    lower = text.lower()
    for kw in _HIGH_IMPACT_KW:
        if kw in lower:
            return 9
    count_mh = sum(1 for kw in _MED_HIGH_IMPACT_KW if kw in lower)
    if count_mh >= 2:
        return 8
    if count_mh == 1:
        return 7
    count_m = sum(1 for kw in _MED_IMPACT_KW if kw in lower)
    if count_m >= 3:
        return 6
    if count_m >= 1:
        return 4
    return _CATEGORY_BASE_SCORE.get(category, 2)
