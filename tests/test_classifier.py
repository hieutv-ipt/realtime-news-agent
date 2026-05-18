import pytest
from app.processors.classifier import classify_by_keywords, score_importance, VALID_CATEGORIES


# ── classify_by_keywords ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    # politics
    ("The election results are in and the president won by a landslide vote", "politics"),
    ("Parliament passes new legislation amid government protest", "politics"),
    # finance
    ("Stock market crashes as federal reserve hikes interest rate by 50 basis points", "finance"),
    ("Bitcoin and crypto market rallied after the rate cut announcement", "finance"),
    ("GDP contracts as inflation surges to record high", "finance"),
    # technology
    ("OpenAI unveils new artificial intelligence model with improved capabilities", "technology"),
    ("Major cyberattack hits critical infrastructure of cloud provider", "technology"),
    ("Nvidia semiconductor chip shortage drives up prices", "technology"),
    # vietnam
    ("Hanoi announces new economic policy for Mekong delta region", "vietnam"),
    ("VnExpress reports flood damage across Ho Chi Minh city", "vietnam"),
    # world
    ("Military conflict escalates as troops advance with missile strikes", "world"),
    ("Humanitarian crisis grows as refugee count reaches record levels", "world"),
    # entertainment
    ("Actor wins Oscar for best film at streaming ceremony", "entertainment"),
    ("FIFA World Cup championship tournament kicks off in stadium", "entertainment"),
    # daily_life
    ("FDA approves new cancer treatment after successful vaccine trial", "daily_life"),
    ("School announces education reform to reduce student loan burden", "daily_life"),
])
def test_classify_by_keywords(text, expected):
    assert classify_by_keywords(text) == expected


def test_classify_unknown_returns_other():
    assert classify_by_keywords("nothing meaningful here xyz qwerty") == "other"


def test_classify_never_returns_none():
    for text in ["", "   ", "a", "random words without any signal"]:
        result = classify_by_keywords(text)
        assert result is not None
        assert result in VALID_CATEGORIES


def test_vietnam_priority_over_generic():
    # Should be vietnam, not world, because Vietnam is a specific location signal
    text = "Vietnam conflict in Hanoi sparks international concern"
    assert classify_by_keywords(text) == "vietnam"


# ── score_importance ──────────────────────────────────────────────────────────

def test_importance_high_for_breaking_news():
    score = score_importance("BREAKING NEWS: Market crash wipes out trillions")
    assert score >= 9


def test_importance_high_for_rate_hike():
    score = score_importance("Federal reserve announces emergency rate hike of 75 basis points")
    assert score >= 7


def test_importance_low_for_soft_news():
    score = score_importance("Local chef opens new restaurant downtown")
    assert score <= 3


def test_importance_in_range():
    texts = [
        "President resigns amid coup",
        "Stock market crash rate cut",
        "New policy announced",
        "Celebrity wins award show",
        "",
    ]
    for text in texts:
        s = score_importance(text)
        assert 1 <= s <= 10, f"Score {s} out of range for: {text!r}"


def test_importance_finance_category_baseline():
    # Finance category should get at least 4 as a baseline even for boring text
    score = score_importance("quarterly earnings released", "finance")
    assert score >= 4


def test_importance_market_crash_nine():
    assert score_importance("stock market crash emergency session called") >= 9
