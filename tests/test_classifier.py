import pytest
from app.processors.classifier import classify_by_keywords


@pytest.mark.parametrize("text,expected", [
    ("The election results are in and the president won by a landslide vote", "politics"),
    ("New AI chip from startup disrupts the semiconductor market", "technology"),
    ("Stock market crashes as company revenue misses expectations", "business"),
    ("NASA discovers new exoplanet in groundbreaking research study", "science"),
    ("Vaccine approved by FDA after cancer drug trial", "health"),
    ("Team wins Olympic championship tournament", "sports"),
    ("Actor wins award for best film at streaming ceremony", "entertainment"),
    ("NATO imposes new sanction amid diplomatic crisis", "world"),
])
def test_classify_by_keywords(text, expected):
    result = classify_by_keywords(text)
    assert result == expected


def test_classify_unknown_returns_none():
    result = classify_by_keywords("nothing meaningful here xyz")
    assert result is None
