import json
from pathlib import Path

from pymercator.cli import main
from pymercator.domain import (
    AssetDecision,
    AssetSnapshot,
    DailyReport,
    ExecutionPermissionResult,
    ExecutionStatus,
    HeadlineRisk,
    MarketRegime,
    MarketRegimeResult,
    Permission,
    RankingRow,
    TradeValidationResult,
    UniverseHealth,
    UniverseHealthResult,
)
from pymercator.position_actions import (
    Position,
    build_position_actions,
    load_positions,
)


def _context(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "headline_tags": [],
                "market_trend": "DOWN",
                "market_volatility": "HIGH",
                "notes": "test context",
            }
        ),
        encoding="utf-8",
    )


def _evaluation(path: Path, *, status: str = "OK") -> None:
    path.write_text(
        json.dumps(
            {
                "engine_used": "multi_horizon_ridge",
                "is_baseline": False,
                "status": "OK",
                "experimental": False,
                "horizons": [5, 20, 60],
                "horizon_observer": {
                    "mode": "weighted",
                    "weights": {"D5": 0.25, "D20": 0.35, "D60": 0.4},
                    "scores": {"D5": 42.0, "D20": 43.0, "D60": 44.0},
                    "combined_score": 43.0,
                    "dominant_horizon": "D60",
                    "behavior": "AVOID",
                },
                "model_quality": {
                    "baseline_accuracy": 0.5,
                    "ensemble_accuracy": 0.48,
                    "edge": -0.02,
                    "status": status,
                },
            }
        ),
        encoding="utf-8",
    )


def _decision(
    ticker: str,
    *,
    trend: float,
    momentum: float,
    last_close: float = 100.0,
    stop: float = 90.0,
    status: ExecutionStatus = ExecutionStatus.READY,
    score: float = 50.0,
) -> AssetDecision:
    asset = AssetSnapshot(
        ticker=ticker,
        sector="materials",
        last_close=last_close,
        avg_volume_brl=100_000_000.0,
        trend_score=trend,
        momentum_score=momentum,
        volatility_pct=5.0,
        atr_pct=2.0,
        liquidity_score=80.0,
        quality_score=70.0,
        news_score=50.0,
        entry=last_close,
        stop=stop,
        target=last_close * 1.2,
    )
    return AssetDecision(
        asset=asset,
        ranking=RankingRow(
            ticker=ticker,
            sector="materials",
            raw_score=score,
            context_score=score,
            context_factor=1.0,
            rank=1,
            raw_signal="BUY",
            context_signal="BUY",
            reasons=(),
        ),
        validation=TradeValidationResult(
            ticker=ticker,
            valid=True,
            entry=last_close,
            stop=stop,
            target=last_close * 1.2,
            rr=2.0,
            liquidity_ok=True,
            volatility_ok=True,
            atr_ok=True,
            status=status,
            reasons=(),
        ),
        permission=ExecutionPermissionResult(
            ticker=ticker,
            status=status,
            max_position_factor=1.0,
            requires_human_confirmation=True,
            reasons=(),
        ),
    )


def _report(
    decisions: tuple[AssetDecision, ...],
    *,
    regime: MarketRegime = MarketRegime.RISK_ON,
) -> DailyReport:
    return DailyReport(
        universe_name="IBOV",
        profile="CON",
        market_regime=MarketRegimeResult(
            regime=regime,
            permission=Permission.ALLOW,
            headline_risk=HeadlineRisk.OFF,
            headline_tags=(),
            score_factor=1.0,
            exposure_factor=1.0,
            reasons=(),
        ),
        universe_health=UniverseHealthResult(
            universe_name="IBOV",
            total_assets=len(decisions),
            valid_assets=len(decisions),
            healthy_assets=len(decisions),
            health=UniverseHealth.NORMAL,
            breadth_label="normal",
            sector_concentration="normal",
            permission=Permission.ALLOW,
            reasons=(),
        ),
        decisions=decisions,
        posture="NORMAL",
        reasons=(),
    )


def test_exit_book_without_positions_file_shows_message(tmp_path: Path) -> None:
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0),))

    payload = build_position_actions(report, positions_path=tmp_path / "missing.csv")

    assert payload["exit_book"]["rows"] == []
    assert payload["exit_book"]["message"] == "no open positions loaded."


def test_profitable_position_with_deteriorating_momentum_takes_profit(
    tmp_path: Path,
) -> None:
    report = _report((_decision("ABCD3", trend=45.0, momentum=45.0, last_close=112.0),))
    positions = tmp_path / "positions.csv"
    positions.write_text(
        "ticker,side,qty,avg_price,entry_date\nABCD3,LONG,100,100,2026-05-10\n",
        encoding="utf-8",
    )

    payload = build_position_actions(report, positions_path=positions)

    assert payload["exit_book"]["rows"][0]["action"] == "TAKE_PROFIT"


def test_position_in_defensive_context_generates_reduce(tmp_path: Path) -> None:
    report = _report(
        (_decision("ABCD3", trend=70.0, momentum=70.0, last_close=101.0),),
        regime=MarketRegime.RISK_OFF,
    )
    positions = tmp_path / "positions.csv"
    positions.write_text(
        "ticker,side,qty,avg_price,entry_date\nABCD3,LONG,100,100,2026-05-10\n",
        encoding="utf-8",
    )

    payload = build_position_actions(
        report,
        {"model_quality": {"status": "WEAK"}, "behavior": "AVOID"},
        positions_path=positions,
    )

    assert payload["exit_book"]["rows"][0]["action"] == "REDUCE"


def test_stop_hit_generates_stop_loss(tmp_path: Path) -> None:
    report = _report((_decision("ABCD3", trend=70.0, momentum=70.0, last_close=89.0),))
    positions = tmp_path / "positions.csv"
    positions.write_text(
        "ticker,side,qty,avg_price,entry_date\nABCD3,LONG,100,100,2026-05-10\n",
        encoding="utf-8",
    )

    payload = build_position_actions(report, positions_path=positions)

    row = payload["exit_book"]["rows"][0]
    assert row["action"] == "STOP_LOSS"
    assert row["reason"] == "stop reached"


def test_weak_asset_without_position_generates_short_blocked_not_sell() -> None:
    report = _report(
        (_decision("WEAK3", trend=20.0, momentum=20.0, score=20.0),),
        regime=MarketRegime.RISK_OFF,
    )

    payload = build_position_actions(
        report,
        {"combined_score": 42.0, "model_quality": {"status": "WEAK"}},
    )

    assert payload["short_book"]
    assert payload["short_book"][0]["action"] == "SHORT_BLOCKED"
    assert payload["short_candidates"] == []
    assert "SELL" not in json.dumps(payload)


def test_position_import_and_show_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    output = tmp_path / "current_positions.csv"
    source.write_text(
        "ticker,side,qty,avg_price,entry_date\nPETR4,LONG,1000,37.20,2026-05-10\n",
        encoding="utf-8",
    )

    assert main(["pos", "import", "--file", str(source), "--output", str(output)]) == 0
    assert load_positions(output) == [
        Position("PETR4", "LONG", 1000.0, 37.20, "2026-05-10")
    ]


def test_run_json_contains_position_action_books_and_keeps_long_basket_blocked(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "evaluation.json"
    report_json = tmp_path / "report.json"
    basket_output = tmp_path / "basket.csv"
    _context(context)
    _evaluation(evaluation, status="WEAK")

    weak_report = _report(
        (_decision("WEAK3", trend=20.0, momentum=20.0, score=20.0),),
        regime=MarketRegime.RISK_OFF,
    )
    monkeypatch.setattr(run_mod, "run_daily_pipeline", lambda **kwargs: weak_report)

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--positions",
            str(tmp_path / "missing_positions.csv"),
            "--report-output",
            str(tmp_path / "report.txt"),
            "--json-output",
            str(report_json),
            "--run-dir",
            str(tmp_path / "latest"),
            "--basket",
            "--basket-output",
            str(basket_output),
            "--json",
        ]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decision"]["actionable"] == 0
    assert result["basket"]["status"] == "BLOCKED"
    assert result["short_candidates"] == []
    assert result["position_actions"]["short_book"][0]["action"] == "SHORT_BLOCKED"
    assert result["position_actions"]["exit_book"]["message"] == (
        "no open positions loaded."
    )
    assert result["top"][0]["decision"] == "BLOCKED"
    assert result["top"][0]["decision"] != "SELL"
    assert "SELL" not in json.dumps(result["position_actions"])

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["exit_book"]["message"] == "no open positions loaded."
    assert payload["short_candidates"] == []
    assert payload["position_actions"]["short_book"][0]["action"] == "SHORT_BLOCKED"
    assert payload["hedge_candidates"] == []

    summary = run_mod.render_run_summary(result)
    assert "OBSERVATION CANDIDATES" in summary
    assert "EXIT BOOK" in summary
    assert "SHORT / HEDGE BOOK" in summary
