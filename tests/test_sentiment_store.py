from pathlib import Path

from pymercator.sentiment_store import (
    check_sentiment_dir,
    check_sentiment_file,
    migrate_legacy_sentiment,
)


def test_check_sentiment_file_accepts_score_column(tmp_path: Path):
    file_path = tmp_path / "PETR4_SA_sentiment_daily.csv"

    file_path.write_text(
        "date,sentiment_score,count\n"
        "2025-01-02,0.15,3\n"
        "2025-01-03,-0.05,2\n",
        encoding="utf-8",
    )

    payload = check_sentiment_file(file_path)

    assert payload["valid"] is True
    assert payload["rows"] == 2
    assert payload["ticker"] == "PETR4.SA"
    assert payload["sentiment_column"] == "sentiment_score"


def test_check_sentiment_dir_summarizes_files(tmp_path: Path):
    (tmp_path / "VALE3_SA_sentiment_daily.csv").write_text(
        "date,score\n2025-01-02,0.2\n",
        encoding="utf-8",
    )

    payload = check_sentiment_dir(tmp_path)

    assert payload["exists"] is True
    assert payload["files"] == 1
    assert payload["valid_files"] == 1
    assert payload["tickers"] == 1


def test_migrate_legacy_sentiment_copies_files(tmp_path: Path):
    legacy = tmp_path / "legacy"
    source = legacy / "data" / "sentiment"
    output = tmp_path / "sentiment"

    source.mkdir(parents=True)
    (source / "PRIO3_SA_sentiment_daily.csv").write_text(
        "date,sentiment\n2025-01-02,0.1\n",
        encoding="utf-8",
    )

    payload = migrate_legacy_sentiment(
        legacy_path=legacy,
        output=output,
    )

    assert payload["copied"] == 1
    assert payload["valid_files"] == 1
    assert (output / "PRIO3_SA_sentiment_daily.csv").exists()
