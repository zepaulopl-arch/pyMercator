from pathlib import Path

from pymercator.sentiment_store import load_ticker_news_score


def test_load_ticker_news_score_maps_positive_sentiment(tmp_path: Path):
    (tmp_path / "PETR4_SA_sentiment_daily.csv").write_text(
        "date,score,count\n"
        "2025-01-02,0.20,2\n"
        "2025-01-03,0.40,3\n",
        encoding="utf-8",
    )

    payload = load_ticker_news_score(
        sentiment_dir=tmp_path,
        ticker="PETR4.SA",
    )

    assert payload["status"] == "OK"
    assert payload["sentiment_score"] == 0.3
    assert payload["news_score"] == 65.0


def test_load_ticker_news_score_maps_missing_to_default(tmp_path: Path):
    payload = load_ticker_news_score(
        sentiment_dir=tmp_path,
        ticker="VALE3.SA",
    )

    assert payload["status"] == "MISSING"
    assert payload["news_score"] == 50.0
