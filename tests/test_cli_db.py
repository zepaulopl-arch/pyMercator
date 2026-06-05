from __future__ import annotations

from pathlib import Path

from pymercator.cli import main
from pymercator.storage.repositories import save_daily_run, save_simulation


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
        "files": {},
        "basket": {"status": "BLOCKED"},
        "report": {
            "decisions": [
                {
                    "asset": {"ticker": "ABCD3"},
                    "permission": {"status": "BLOCKED"},
                    "ranking": {"context_score": 42.5},
                    "decision_label": "MODEL_WEAK",
                    "blocker_reasons": ["MODEL_WEAK"],
                }
            ]
        },
        "short_observation_candidates": [
            {
                "ticker": "MGLU3",
                "bias": "SHORT",
                "score": 92.9,
                "class": "SHORT_SETUP",
                "reason": "weak trend/mom + risk-off",
                "executable": False,
                "permission": "SHORT_BLOCKED",
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


def test_cli_db_status_creates_database(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "aurum.db"

    assert main(["db", "status", "--db", str(db_path)]) == 0

    output = capsys.readouterr().out
    assert "DB STATUS" in output
    assert "daily_runs" in output
    assert db_path.exists()


def test_cli_db_queries_last_run_signal_rank_and_simulation(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "aurum.db"
    save_daily_run(_sample_payload(), db_path=db_path)
    save_simulation(
        {"name": "smoke", "status": "OK", "summary_path": "summary.txt"},
        [{"ticker": "ABCD3", "side": "LONG"}],
        db_path=db_path,
    )

    assert main(["db", "last-run", "--db", str(db_path)]) == 0
    assert "DB LAST RUN" in capsys.readouterr().out

    assert main(["db", "signal", "MGLU3", "--db", str(db_path)]) == 0
    signal_output = capsys.readouterr().out
    assert "DB SIGNAL MGLU3" in signal_output
    assert "SHORT" in signal_output

    assert main(["db", "rank-last", "--db", str(db_path)]) == 0
    rank_output = capsys.readouterr().out
    assert "DB RANK LAST" in rank_output
    assert "ABCD3" in rank_output

    assert main(["db", "sim-last", "--db", str(db_path)]) == 0
    sim_output = capsys.readouterr().out
    assert "DB SIM LAST" in sim_output
    assert "smoke" in sim_output
