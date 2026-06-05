from __future__ import annotations

import json
from pathlib import Path

from pymercator.cli import main
from pymercator.observation_review import run_observation_review


def _write_price(path: Path, first_close: float, latest_close: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "date,open,high,low,close,volume",
                f"2026-06-05,{first_close},{first_close},{first_close},{first_close},1000",
                f"2026-06-06,{latest_close},{latest_close},{latest_close},{latest_close},1000",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _decision(ticker: str, close: float, status: str, reasons: list[str]) -> dict:
    return {
        "asset": {
            "ticker": ticker,
            "last_close": close,
        },
        "ranking": {
            "ticker": ticker,
            "raw_score": 73.5,
            "context_score": 73.5,
            "raw_signal": "BUY",
            "context_signal": "BUY",
        },
        "validation": {
            "status": status,
        },
        "permission": {
            "status": status,
        },
        "decision_label": status,
        "blocker_reasons": reasons,
    }


def _write_report(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": "CON",
        "decisions": [
            _decision("LONG1", 100.0, "BLOCKED", ["MODEL_WEAK", "VOL_HIGH"]),
            _decision("LONG2", 50.0, "READY", []),
            _decision("LONG3", 40.0, "WATCH", ["MANUAL_REVIEW"]),
        ],
        "observation_candidates": [
            {
                "ticker": "LONG1",
                "score": 75.0,
                "class": "OBS_FAVORABLE",
                "reason": "strong trend/mom",
                "bias": "LONG",
                "executable": False,
            }
        ],
        "short_observation_candidates": [
            {
                "ticker": "SHORT1",
                "score": 92.9,
                "class": "SHORT_SETUP",
                "reason": "weak trend/mom + risk-off",
                "borrow_status": "DATA_MISSING",
                "permission": "SHORT_BLOCKED",
                "short_permission": "SHORT_BLOCKED",
                "bias": "SHORT",
                "executable": False,
            }
        ],
        "short_candidates": [
            {
                "ticker": "SHORT1",
                "score": 92.9,
                "class": "SHORT_SETUP",
                "reason": "weak trend/mom + risk-off",
                "borrow_status": "DATA_MISSING",
                "permission": "SHORT_BLOCKED",
                "short_permission": "SHORT_BLOCKED",
                "executable": False,
            },
            {
                "ticker": "SHORT2",
                "score": 80.0,
                "class": "SHORT_SETUP",
                "reason": "weak trend",
                "borrow_status": "OK",
                "permission": "READY",
                "short_permission": "SHORT_READY",
                "executable": True,
            }
        ],
    }
    (run_dir / "report_CON.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_observation_review_writes_outputs_and_separates_real_from_hypothetical(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runtime" / "daily_signal_20260605_120000"
    prices_dir = tmp_path / "prices"
    _write_report(run_dir)
    _write_price(prices_dir / "LONG1.SA.csv", 100.0, 110.0)
    _write_price(prices_dir / "LONG2.SA.csv", 50.0, 55.0)
    _write_price(prices_dir / "LONG3.SA.csv", 40.0, 44.0)
    _write_price(prices_dir / "SHORT1.SA.csv", 20.0, 18.0)
    _write_price(prices_dir / "SHORT2.SA.csv", 30.0, 27.0)

    review = run_observation_review(
        run_dir=run_dir,
        capital=100000.0,
        prices_dir=prices_dir,
    )

    assert (run_dir / "observation_review.txt").exists()
    assert (run_dir / "observation_review.csv").exists()
    assert (run_dir / "observation_review.json").exists()
    assert review["summary"]["real_watch_or_better"]["items"] == 3
    assert review["summary"]["real_watch_or_better"]["ready_items"] == 2
    assert review["summary"]["real_watch_or_better"]["watch_items"] == 1
    assert review["summary"]["real_watch_or_better"]["real_pnl"] > 0
    assert review["summary"]["real_watch_or_better"]["sim_pnl"] > review["summary"]["real_watch_or_better"]["real_pnl"]
    assert review["summary"]["long_observation"]["pnl_total"] == 10000.0
    assert review["summary"]["short_observation"]["pnl_total"] == 10000.0
    assert review["summary"]["observation_top10"]["items"] == 2
    assert review["summary"]["hypothetical_observation"]["pnl_total"] == 20000.0
    assert review["summary"]["blocked_setups"]["real_pnl"] == 0.0
    assert review["summary"]["blocked_setups"]["classes"]["MISSED_OPPORTUNITY"] == 2


def test_mtm_cli_renders_required_sections(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "runtime" / "daily_signal_20260605_120000"
    prices_dir = tmp_path / "prices"
    _write_report(run_dir)
    _write_price(prices_dir / "LONG1.SA.csv", 100.0, 90.0)
    _write_price(prices_dir / "LONG2.SA.csv", 50.0, 55.0)
    _write_price(prices_dir / "LONG3.SA.csv", 40.0, 44.0)
    _write_price(prices_dir / "SHORT1.SA.csv", 20.0, 25.0)
    _write_price(prices_dir / "SHORT2.SA.csv", 30.0, 27.0)

    exit_code = main(
        [
            "mtm",
            "--run-dir",
            str(run_dir),
            "--capital",
            "100000",
            "--prices-dir",
            str(prices_dir),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "REAL SIGNALS - WATCH OR BETTER" in output
    assert "REAL SIGNAL RESULT (LONG + SHORT)" in output
    assert "OBSERVATION TOP 10" in output
    assert "OBSERVATION RESULT (TOP 10 LONG + TOP 10 SHORT)" in output
    assert "LONG SIGNAL RESULT" not in output
    assert "SHORT SIGNAL RESULT" not in output
    assert "FINAL REVIEW" in output
    assert "observation P&L is hypothetical" in output
    assert "REAL_PNL" in output


def test_review_marks_missing_price_data(tmp_path: Path) -> None:
    run_dir = tmp_path / "runtime" / "daily_signal_20260605_120000"
    _write_report(run_dir)

    review = run_observation_review(
        run_dir=run_dir,
        capital=100000.0,
        prices_dir=tmp_path / "missing_prices",
    )

    assert review["data_missing"] > 0
    assert review["summary"]["long_observation"]["data_missing"] == 1
    assert "DATA_MISSING" in (run_dir / "observation_review.txt").read_text(encoding="utf-8")
