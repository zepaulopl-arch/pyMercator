from dataclasses import replace
from pathlib import Path

from pymercator.domain import MarketRegime
from pymercator.position_actions import build_position_actions, render_position_books

from test_position_actions import _decision, _report


def _positions(path: Path, ticker: str = "ABCD3", avg_price: float = 100.0) -> Path:
    path.write_text(
        (
            "ticker,side,qty,avg_price,entry_date\n"
            f"{ticker},LONG,100,{avg_price},2026-05-10\n"
        ),
        encoding="utf-8",
    )
    return path


def test_loss_threshold_generates_stop_loss(tmp_path: Path):
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0, last_close=96.0, stop=90.0),))
    payload = build_position_actions(report, positions_path=_positions(tmp_path / "positions.csv"))

    row = payload["exit_book"]["rows"][0]
    assert row["action"] == "STOP_LOSS"
    assert row["reason"] == "loss threshold"


def test_structural_risk_without_stop_generates_exit_full(tmp_path: Path):
    decision = _decision("ABCD3", trend=70.0, momentum=70.0, last_close=99.0, stop=80.0)
    decision = replace(
        decision,
        asset=replace(decision.asset, volatility_pct=12.0, atr_pct=7.0),
        validation=replace(decision.validation, volatility_ok=False, atr_ok=False, stop=80.0),
    )
    report = _report((decision,), regime=MarketRegime.RISK_OFF)

    payload = build_position_actions(report, positions_path=_positions(tmp_path / "positions.csv"))

    row = payload["exit_book"]["rows"][0]
    assert row["action"] == "EXIT_FULL"
    assert row["reason"] == "structural risk breach"


def test_position_outside_universe_requires_manual_review(tmp_path: Path):
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0),))
    payload = build_position_actions(
        report,
        positions_path=_positions(tmp_path / "positions.csv", ticker="XXXX3"),
    )

    row = payload["exit_book"]["rows"][0]
    assert row["action"] == "HOLD"
    assert row["risk"] == "UNKNOWN"
    assert row["manual_review_required"] is True
    assert row["reason"] == "position outside current universe"

    summary = "\n".join(render_position_books(payload))
    assert "REVIEW" in summary
    assert "YES" in summary


def test_position_inside_universe_does_not_require_manual_review(tmp_path: Path):
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0),))
    payload = build_position_actions(report, positions_path=_positions(tmp_path / "positions.csv"))

    assert payload["exit_book"]["rows"][0]["manual_review_required"] is False
