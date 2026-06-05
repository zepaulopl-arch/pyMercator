from __future__ import annotations

from pathlib import Path

from pymercator.storage.repositories import (
    latest_daily_run,
    latest_rankings,
    latest_simulation,
    save_daily_run,
    save_simulation,
    signals_for_ticker,
    table_counts,
)


def _sample_payload() -> dict:
    return {
        "command": "run",
        "profile": "CON",
        "list": "IBOV",
        "status": "OK",
        "market": {
            "regime": "RISK_OFF",
            "context_summary": {"market_trend": "DOWN"},
        },
        "prediction": {
            "behavior": "AVOID",
            "model_quality": {"status": "WEAK"},
        },
        "decision": {"actionable": 0, "watch": 1, "blocked": 1},
        "files": {
            "json": "runtime/report_CON.json",
            "report": "runtime/report_CON.txt",
            "basket": "runtime/basket_CON.csv",
            "run_dir": "runtime/run",
        },
        "basket": {"status": "BLOCKED"},
        "report": {
            "decisions": [
                {
                    "asset": {"ticker": "ABCD3"},
                    "permission": {
                        "status": "BLOCKED",
                        "reasons": ["MODEL_WEAK"],
                    },
                    "ranking": {"context_score": 42.5},
                    "validation": {"reasons": ["risk blocked"]},
                    "decision_label": "MODEL_WEAK",
                    "blocker_reasons": ["MODEL_WEAK"],
                    "decision_codes": ["MW"],
                }
            ]
        },
        "observation_candidates": [
            {
                "ticker": "BRAV3",
                "bias": "LONG",
                "score": 75.0,
                "class": "OBS_FAVORABLE",
                "reason": "strong trend/mom",
                "executable": False,
            }
        ],
        "short_observation_candidates": [
            {
                "ticker": "MGLU3",
                "bias": "SHORT",
                "score": 92.9,
                "class": "SHORT_SETUP",
                "reason": "weak trend/mom + risk-off",
                "executable": False,
                "borrow_status": "BORROW_DATA_MISSING",
                "permission": "SHORT_BLOCKED",
            }
        ],
        "hedge_candidates": [
            {
                "target": "INDEX",
                "action": "HEDGE_WATCH",
                "reason": "risk-off + broad weakness",
            }
        ],
        "top": [
            {
                "ticker": "ABCD3",
                "decision": "BLOCKED",
                "score": 42.5,
                "guard": "MODEL_WEAK",
            }
        ],
    }


def test_save_daily_run_inserts_history_signals_reasons_and_rankings(tmp_path: Path) -> None:
    db_path = tmp_path / "aurum.db"
    run_id = save_daily_run(_sample_payload(), db_path=db_path)

    assert run_id == 1
    assert db_path.exists()
    counts = table_counts(db_path=db_path)
    assert counts["daily_runs"] == 1
    assert counts["signals"] == 4
    assert counts["signal_reasons"] >= 4
    assert counts["rankings"] == 1

    latest = latest_daily_run(db_path=db_path)
    assert latest is not None
    assert latest["profile"] == "CON"
    assert latest["market"] == "RISK_OFF"
    assert latest["model_quality"] == "WEAK"

    short_signals = signals_for_ticker("MGLU3", db_path=db_path)
    assert short_signals
    assert short_signals[0]["bias"] == "SHORT"
    assert short_signals[0]["executable"] == 0
    assert short_signals[0]["permission"] == "SHORT_BLOCKED"

    rankings = latest_rankings(db_path=db_path)
    assert rankings[0]["ticker"] == "ABCD3"
    assert rankings[0]["status"] == "BLOCKED"


def test_save_simulation_inserts_summary_and_trades(tmp_path: Path) -> None:
    db_path = tmp_path / "aurum.db"
    simulation_id = save_simulation(
        {
            "name": "smoke",
            "status": "OK",
            "summary_path": "runtime/sim/summary.txt",
            "trades_csv": "runtime/sim/trades.csv",
        },
        [
            {
                "ticker": "ABCD3",
                "side": "LONG",
                "entry_date": "2026-06-01",
                "exit_date": "2026-06-05",
                "entry_price": 10.0,
                "exit_price": 11.0,
                "pnl": 100.0,
                "pnl_pct": 0.10,
            }
        ],
        db_path=db_path,
    )

    assert simulation_id == 1
    latest = latest_simulation(db_path=db_path)
    assert latest is not None
    assert latest["name"] == "smoke"
    assert latest["status"] == "OK"
    assert len(latest["trades"]) == 1
    assert latest["trades"][0]["ticker"] == "ABCD3"
