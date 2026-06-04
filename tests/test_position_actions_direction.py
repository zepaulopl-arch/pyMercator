import json
from pathlib import Path

from pymercator.domain import ExecutionStatus, MarketRegime
from pymercator.position_actions import build_position_actions, render_position_books
from pymercator.position_actions_config import load_position_actions_config

from test_position_actions import _decision, _report


def _positions(path: Path) -> Path:
    path.write_text(
        (
            "ticker,side,qty,avg_price,entry_date,trade_mode\n"
            "ABCD3,LONG,100,100,2026-05-10,POSITION\n"
        ),
        encoding="utf-8",
    )
    return path


def _short_enabled_config(path: Path) -> Path:
    config = load_position_actions_config("config/position_actions.json")
    config["short"]["requires_borrow_data"] = False
    config["short"]["block_without_borrow_data"] = False
    config["short"]["min_short_score"] = 60.0
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_terminal_uses_directional_book_names(tmp_path: Path):
    report = _report(
        (
            _decision("ABCD3", trend=70.0, momentum=70.0),
            _decision("WEAK3", trend=20.0, momentum=20.0, score=20.0),
        ),
        regime=MarketRegime.RISK_OFF,
    )
    payload = build_position_actions(
        report,
        {"combined_score": 42.0, "model_quality": {"status": "WEAK"}},
        positions_path=tmp_path / "missing.csv",
    )

    summary = "\n".join(render_position_books(payload))

    assert "BUY / LONG BOOK" in summary
    assert "SELL-SHORT / HEDGE BOOK" in summary
    assert "LONG BOOK" in summary
    assert "\nSHORT / HEDGE BOOK\n" not in f"\n{summary}\n"
    assert "direction         LONG" in summary
    assert "direction         SHORT" in summary
    assert "meaning           bought/long position; benefits from price rising" in summary
    assert "meaning           sold/borrowed position; benefits from price falling" in summary
    assert "requires          borrow availability, borrow cost and short risk checks" in summary


def test_long_rows_include_direction_trade_mode_and_action(tmp_path: Path):
    report = _report(
        (
            _decision("READY3", trend=70.0, momentum=70.0),
            _decision(
                "BLOCK3",
                trend=30.0,
                momentum=30.0,
                status=ExecutionStatus.BLOCKED,
            ),
        )
    )

    payload = build_position_actions(report, positions_path=tmp_path / "missing.csv")

    ready = payload["long_book"][0]
    blocked = next(row for row in payload["long_book"] if row["ticker"] == "BLOCK3")
    assert ready["action"] == "BUY_READY"
    assert ready["direction"] == "LONG"
    assert ready["trade_mode"] == "SWING"
    assert blocked["action"] == "BLOCKED"
    assert blocked["direction"] == "LONG"
    assert blocked["trade_mode"] == "SWING"
    assert blocked["trade_mode"] != blocked["direction"]


def test_exit_rows_include_position_direction_and_trade_mode(tmp_path: Path):
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0),))

    payload = build_position_actions(
        report,
        positions_path=_positions(tmp_path / "positions.csv"),
    )

    row = payload["exit_book"]["rows"][0]
    assert row["action"] == "HOLD"
    assert row["direction"] == "LONG"
    assert row["trade_mode"] == "POSITION"
    assert row["trade_mode"] != row["direction"]


def test_short_candidate_rows_include_short_direction(tmp_path: Path):
    report = _report(
        (_decision("WEAK3", trend=20.0, momentum=20.0, score=20.0),),
        regime=MarketRegime.RISK_OFF,
    )

    payload = build_position_actions(
        report,
        {"combined_score": 42.0, "model_quality": {"status": "WEAK"}},
        positions_path=tmp_path / "missing.csv",
        config_path=_short_enabled_config(tmp_path / "position_actions.json"),
    )

    row = payload["short_candidates"][0]
    assert row["action"] == "SHORT_MANUAL_ONLY"
    assert row["direction"] == "SHORT"
    assert row["trade_mode"] == "SWING"
    assert row["trade_mode"] != row["direction"]
    assert payload["defensive_book"]["defensive_mode"] == "active"
