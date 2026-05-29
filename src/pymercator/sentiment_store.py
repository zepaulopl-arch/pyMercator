from __future__ import annotations

import csv
import shutil
from pathlib import Path
from typing import Any

SENTIMENT_COLUMNS = {
    "sentiment",
    "sentiment_score",
    "score",
    "news_score",
    "compound",
    "polarity",
}


def _detect_sentiment_column(columns: list[str]) -> str:
    lowered = {column.lower(): column for column in columns}

    for candidate in SENTIMENT_COLUMNS:
        if candidate in lowered:
            return lowered[candidate]

    for column in columns:
        name = column.lower()
        if "sentiment" in name or "score" in name or "polarity" in name:
            return column

    return ""


def _ticker_from_sentiment_file(path: Path) -> str:
    name = path.stem

    for suffix in (
        "_sentiment_daily",
        "_sentiment",
        "_news_daily",
        "_news",
    ):
        if name.endswith(suffix):
            name = name[: -len(suffix)]

    return name.replace("_SA", ".SA").replace("_", ".")


def check_sentiment_file(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)

    if not file_path.exists():
        return {
            "path": str(file_path),
            "file": file_path.name,
            "ticker": _ticker_from_sentiment_file(file_path),
            "valid": False,
            "rows": 0,
            "columns": [],
            "date_column": "",
            "sentiment_column": "",
            "start_date": "",
            "end_date": "",
            "errors": ["file not found"],
        }

    errors: list[str] = []
    rows = 0
    start_date = ""
    end_date = ""

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            columns = list(reader.fieldnames or [])

            date_column = "date" if "date" in [c.lower() for c in columns] else ""
            if not date_column:
                for column in columns:
                    if column.lower() in {"dt", "day", "timestamp"}:
                        date_column = column
                        break

            sentiment_column = _detect_sentiment_column(columns)

            if not date_column:
                errors.append("missing date column")

            if not sentiment_column:
                errors.append("missing sentiment/score column")

            for line_no, row in enumerate(reader, start=2):
                rows += 1

                date_value = str(row.get(date_column, "")).strip()
                score_value = str(row.get(sentiment_column, "")).strip()

                if rows == 1:
                    start_date = date_value

                end_date = date_value

                if not date_value:
                    errors.append(f"line {line_no}: missing date")

                if sentiment_column and score_value:
                    try:
                        float(score_value)
                    except ValueError:
                        errors.append(
                            f"line {line_no}: invalid sentiment value"
                        )

    except Exception as exc:
        return {
            "path": str(file_path),
            "file": file_path.name,
            "ticker": _ticker_from_sentiment_file(file_path),
            "valid": False,
            "rows": 0,
            "columns": [],
            "date_column": "",
            "sentiment_column": "",
            "start_date": "",
            "end_date": "",
            "errors": [str(exc)],
        }

    return {
        "path": str(file_path),
        "file": file_path.name,
        "ticker": _ticker_from_sentiment_file(file_path),
        "valid": not errors and rows > 0,
        "rows": rows,
        "columns": columns,
        "date_column": date_column,
        "sentiment_column": sentiment_column,
        "start_date": start_date,
        "end_date": end_date,
        "errors": errors[:20],
    }


def check_sentiment_dir(sentiment_dir: str | Path) -> dict[str, Any]:
    root = Path(sentiment_dir)

    if not root.exists():
        return {
            "sentiment_dir": str(root),
            "exists": False,
            "files": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "tickers": 0,
            "results": [],
        }

    results = [
        check_sentiment_file(path)
        for path in sorted(root.glob("*.csv"))
    ]

    valid_files = sum(1 for item in results if item["valid"])
    invalid_files = sum(1 for item in results if not item["valid"])
    tickers = len({item["ticker"] for item in results if item["ticker"]})

    return {
        "sentiment_dir": str(root),
        "exists": True,
        "files": len(results),
        "valid_files": valid_files,
        "invalid_files": invalid_files,
        "tickers": tickers,
        "results": results,
    }


def migrate_legacy_sentiment(
    *,
    legacy_path: str | Path,
    output: str | Path,
    source_dir: str = "data/sentiment",
) -> dict[str, Any]:
    root = Path(legacy_path)
    source = root / source_dir
    target = Path(output)

    if not source.exists():
        raise FileNotFoundError(f"Legacy sentiment directory not found: {source}")

    target.mkdir(parents=True, exist_ok=True)

    copied: list[dict[str, str]] = []

    for source_file in sorted(source.glob("*.csv")):
        target_file = target / source_file.name
        shutil.copy2(source_file, target_file)

        copied.append(
            {
                "source": str(source_file),
                "target": str(target_file),
                "ticker": _ticker_from_sentiment_file(target_file),
            }
        )

    check = check_sentiment_dir(target)

    return {
        "legacy_path": str(root),
        "source_dir": str(source),
        "output": str(target),
        "copied": len(copied),
        "valid_files": check["valid_files"],
        "invalid_files": check["invalid_files"],
        "tickers": check["tickers"],
        "files": copied,
        "check": check,
    }


def render_sentiment_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR SENTIMENT CHECK",
        line,
        f"{'SENTIMENT DIR':<20} {payload['sentiment_dir']}",
        f"{'EXISTS':<20} {payload['exists']}",
        f"{'FILES':<20} {payload['files']}",
        f"{'VALID FILES':<20} {payload['valid_files']}",
        f"{'INVALID FILES':<20} {payload['invalid_files']}",
        f"{'TICKERS':<20} {payload['tickers']}",
        "",
        "FILES",
        line,
    ]

    for item in payload["results"][:120]:
        status = "OK" if item["valid"] else "INVALID"
        errors = "; ".join(item["errors"][:2]) if item["errors"] else "-"
        lines.append(
            f"{item['file']:<36} "
            f"{status:<8} "
            f"rows={item['rows']:<6} "
            f"ticker={item['ticker']:<12} "
            f"score={item['sentiment_column'] or '-':<18} "
            f"{errors}"
        )

    return "\n".join(lines)

def _normalize_score_to_news_score(score: float) -> float:
    # Legacy sentiment usually lives around -1.0..1.0.
    # Convert it into an operational 0..100 news score centered at 50.
    value = 50.0 + (score * 50.0)
    return round(max(0.0, min(100.0, value)), 2)


def _sentiment_file_for_ticker(sentiment_dir: Path, ticker: str) -> Path:
    normalized = ticker.upper().replace(".SA", "_SA").replace(".", "_")
    return sentiment_dir / f"{normalized}_sentiment_daily.csv"


def load_ticker_news_score(
    *,
    sentiment_dir: str | Path,
    ticker: str,
    lookback_rows: int = 5,
    default: float = 50.0,
) -> dict[str, Any]:
    root = Path(sentiment_dir)
    file_path = _sentiment_file_for_ticker(root, ticker)

    if not file_path.exists():
        return {
            "ticker": ticker,
            "news_score": default,
            "sentiment_score": 0.0,
            "rows_used": 0,
            "path": str(file_path),
            "status": "MISSING",
        }

    check = check_sentiment_file(file_path)
    if not check["valid"]:
        return {
            "ticker": ticker,
            "news_score": default,
            "sentiment_score": 0.0,
            "rows_used": 0,
            "path": str(file_path),
            "status": "INVALID",
        }

    rows: list[float] = []

    with file_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        sentiment_column = check["sentiment_column"]

        for row in reader:
            value = str(row.get(sentiment_column, "")).strip()
            if not value:
                continue

            try:
                rows.append(float(value))
            except ValueError:
                continue

    if not rows:
        return {
            "ticker": ticker,
            "news_score": default,
            "sentiment_score": 0.0,
            "rows_used": 0,
            "path": str(file_path),
            "status": "EMPTY",
        }

    recent = rows[-lookback_rows:]
    sentiment_score = sum(recent) / len(recent)

    return {
        "ticker": ticker,
        "news_score": _normalize_score_to_news_score(sentiment_score),
        "sentiment_score": round(sentiment_score, 4),
        "rows_used": len(recent),
        "path": str(file_path),
        "status": "OK",
    }


def load_news_scores(
    *,
    sentiment_dir: str | Path,
    tickers: list[str],
    lookback_rows: int = 5,
    default: float = 50.0,
) -> dict[str, dict[str, Any]]:
    return {
        ticker: load_ticker_news_score(
            sentiment_dir=sentiment_dir,
            ticker=ticker,
            lookback_rows=lookback_rows,
            default=default,
        )
        for ticker in tickers
    }

