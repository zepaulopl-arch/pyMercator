from pathlib import Path

from pymercator.cli import main


def test_sentiment_check_command(tmp_path: Path, capsys):
    (tmp_path / "PETR4_SA_sentiment_daily.csv").write_text(
        "date,sentiment_score\n2025-01-02,0.1\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "sentiment",
            "check",
            "--sentiment-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    captured = capsys.readouterr()
    assert "PYMERCATOR SENTIMENT CHECK" in captured.out
    assert "VALID FILES" in captured.out
    assert "PETR4.SA" in captured.out


def test_legacy_migrate_sentiment_command(tmp_path: Path, capsys):
    legacy = tmp_path / "legacy"
    source = legacy / "data" / "sentiment"
    output = tmp_path / "sentiment"

    source.mkdir(parents=True)
    (source / "VALE3_SA_sentiment_daily.csv").write_text(
        "date,score\n2025-01-02,0.25\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "legacy",
            "migrate-sentiment",
            "--legacy-path",
            str(legacy),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert (output / "VALE3_SA_sentiment_daily.csv").exists()

    captured = capsys.readouterr()
    assert "PYMERCATOR LEGACY SENTIMENT MIGRATION" in captured.out
    assert "COPIED" in captured.out
