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


def _write_context(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "headline_tags": [],
                "market_trend": "UP",
                "market_volatility": "NORMAL",
                "notes": "test context",
            }
        ),
        encoding="utf-8",
    )


def _write_multi_horizon_evaluation(path: Path) -> None:
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
                    "scores": {"D5": 51.0, "D20": 58.0, "D60": 66.0},
                    "combined_score": 59.85,
                    "dominant_horizon": "D60",
                    "behavior": "POSITIONAL_SETUP",
                },
                "model_quality": {
                    "baseline_accuracy": 0.5,
                    "ensemble_accuracy": 0.58,
                    "edge": 0.08,
                    "precision": 0.57,
                    "recall": 0.55,
                    "false_positive_rate": 0.2,
                    "status": "OK",
                },
            }
        ),
        encoding="utf-8",
    )


def _fake_report(profile: str) -> DailyReport:
    asset = AssetSnapshot(
        ticker="PRIO3",
        sector="energy",
        last_close=10.0,
        avg_volume_brl=1_000_000.0,
        trend_score=70.0,
        momentum_score=70.0,
        volatility_pct=10.0,
        atr_pct=2.0,
        liquidity_score=80.0,
        quality_score=70.0,
        news_score=70.0,
        entry=10.0,
        stop=9.0,
        target=12.0,
    )
    decision = AssetDecision(
        asset=asset,
        ranking=RankingRow(
            ticker="PRIO3",
            sector="energy",
            raw_score=70.0,
            context_score=70.0,
            context_factor=1.0,
            rank=1,
            raw_signal="BUY",
            context_signal="BUY",
            reasons=(),
        ),
        validation=TradeValidationResult(
            ticker="PRIO3",
            valid=True,
            entry=10.0,
            stop=9.0,
            target=12.0,
            rr=2.0,
            liquidity_ok=True,
            volatility_ok=True,
            atr_ok=True,
            status=ExecutionStatus.READY,
            reasons=(),
        ),
        permission=ExecutionPermissionResult(
            ticker="PRIO3",
            status=ExecutionStatus.READY,
            max_position_factor=1.0,
            requires_human_confirmation=True,
            reasons=(),
        ),
    )
    return DailyReport(
        universe_name="IBOV",
        profile=profile,
        market_regime=MarketRegimeResult(
            regime=MarketRegime.RISK_ON,
            permission=Permission.ALLOW,
            headline_risk=HeadlineRisk.OFF,
            headline_tags=(),
            score_factor=1.0,
            exposure_factor=1.0,
            reasons=(),
        ),
        universe_health=UniverseHealthResult(
            universe_name="IBOV",
            total_assets=1,
            valid_assets=1,
            healthy_assets=1,
            health=UniverseHealth.NORMAL,
            breadth_label="normal",
            sector_concentration="normal",
            permission=Permission.ALLOW,
            reasons=(),
        ),
        decisions=(decision,),
        posture="NORMAL",
        reasons=(),
    )


def test_cli_run_executes_daily_with_defaults_for_outputs(tmp_path: Path, capsys):
    context = tmp_path / "context.json"
    report = tmp_path / "report.txt"
    json_report = tmp_path / "report.json"
    run_dir = tmp_path / "latest"
    basket_output = tmp_path / "basket.csv"
    evaluation = tmp_path / "evaluation.json"
    _write_context(context)
    _write_multi_horizon_evaluation(evaluation)

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--report-output",
            str(report),
            "--json-output",
            str(json_report),
            "--run-dir",
            str(run_dir),
            "--evaluation",
            str(evaluation),
            "--basket-output",
            str(basket_output),
            "--json",
        ]
    )

    assert exit_code == 0
    assert report.exists()
    assert json_report.exists()
    assert (run_dir / "report.txt").exists()
    assert (run_dir / "report.json").exists()
    assert not basket_output.exists()

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["profile"] == "CON"
    assert payload["basket"] is None


def test_cli_run_with_basket_generates_basket(tmp_path: Path, monkeypatch, capsys):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    report = tmp_path / "report.txt"
    json_report = tmp_path / "report.json"
    run_dir = tmp_path / "latest"
    basket_output = tmp_path / "basket.csv"
    evaluation = tmp_path / "evaluation.json"
    _write_context(context)
    _write_multi_horizon_evaluation(evaluation)

    def fake_basket(**kwargs):
        assert kwargs["eligible_tickers"]
        Path(kwargs["output_csv"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_csv"]).write_text("ticker,weight\nPRIO3,0.2\n", encoding="utf-8")
        return {
            "status": "OK",
            "slots": kwargs["slots"],
            "output_csv": kwargs["output_csv"],
            "rows": [{"ticker": "PRIO3"}],
        }

    monkeypatch.setattr(run_mod, "run_daily_basket", fake_basket)

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--report-output",
            str(report),
            "--json-output",
            str(json_report),
            "--run-dir",
            str(run_dir),
            "--evaluation",
            str(evaluation),
            "--basket",
            "--basket-output",
            str(basket_output),
            "--json",
        ]
    )

    assert exit_code == 0
    assert basket_output.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["actionable"] > 0
    assert payload["basket"]["status"] == "OK"
    assert payload["basket"]["assets"] == 1


def test_cli_run_blocks_invalid_unknown_context(
    tmp_path: Path,
    capsys,
):
    context = tmp_path / "context.json"
    report = tmp_path / "report.txt"
    json_report = tmp_path / "report.json"
    run_dir = tmp_path / "latest"
    context.write_text(
        json.dumps(
            {
                "headline_tags": [],
                "market_trend": "UNKNOWN",
                "market_volatility": "NORMAL",
                "notes": "unknown trend blocks operational basket",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--report-output",
            str(report),
            "--json-output",
            str(json_report),
            "--run-dir",
            str(run_dir),
            "--json",
        ]
    )

    assert exit_code == 1
    assert not report.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "invalid or insufficient market context"


def test_cli_run_with_basket_blocks_when_no_actionable_assets(
    tmp_path: Path,
    capsys,
):
    context = tmp_path / "context.json"
    report = tmp_path / "report.txt"
    json_report = tmp_path / "report.json"
    run_dir = tmp_path / "latest"
    basket_output = tmp_path / "basket.csv"
    evaluation = tmp_path / "evaluation.json"
    _write_multi_horizon_evaluation(evaluation)
    context.write_text(
        json.dumps(
            {
                "headline_tags": ["RISK_OFF"],
                "market_trend": "DOWN",
                "market_volatility": "NORMAL",
                "notes": "defensive context should not create operational basket",
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--report-output",
            str(report),
            "--json-output",
            str(json_report),
            "--run-dir",
            str(run_dir),
            "--evaluation",
            str(evaluation),
            "--basket",
            "--basket-output",
            str(basket_output),
            "--json",
        ]
    )

    assert exit_code == 0
    assert basket_output.exists()
    assert basket_output.read_text(encoding="utf-8").splitlines() == [
        (
            "ticker,sector,rank,score,entry,initial_stop,target_1,target_2,"
            "stop_after_t1,trailing_rule,weight,position_value,risk_per_share,"
            "max_loss,quantity,status,warnings"
        )
    ]

    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["actionable"] == 0
    assert payload["basket"]["status"] == "BLOCKED"
    assert payload["basket"]["assets"] == 0
    assert payload["basket"]["reason"] == "no actionable assets"

    basket_manifest = json.loads(basket_output.with_suffix(".json").read_text(encoding="utf-8"))
    assert basket_manifest["status"] == "BLOCKED"
    assert basket_manifest["rows"] == []


def test_cli_run_applies_requested_profile_to_policy_layer(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    _write_context(context)
    calls = []

    def fake_pipeline(**kwargs):
        calls.append(kwargs)
        return _fake_report(kwargs["profile"])

    monkeypatch.setattr(run_mod, "run_daily_pipeline", fake_pipeline)

    for profile in ("CON", "AGR"):
        exit_code = main(
            [
                "run",
                "--profile",
                profile,
                "--universe",
                "data/universes/ibov_sample.csv",
                "--context",
                str(context),
                "--report-output",
                str(tmp_path / f"{profile}_report.txt"),
                "--json-output",
                str(tmp_path / f"{profile}_report.json"),
                "--run-dir",
                str(tmp_path / profile),
                "--evaluation",
                str(tmp_path / "same_evaluation.json"),
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)

        assert exit_code == 0
        assert payload["profile"] == profile
        assert payload["report"]["profile"] == profile

    assert [call["profile"] for call in calls] == ["CON", "AGR"]


def test_cli_run_reuses_same_evaluation_across_profiles_for_basket(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "same_evaluation.json"
    _write_context(context)
    evaluation.write_text("{}", encoding="utf-8")
    pipeline_profiles = []
    basket_evaluations = []

    def fake_pipeline(**kwargs):
        pipeline_profiles.append(kwargs["profile"])
        return _fake_report(kwargs["profile"])

    def fake_basket(**kwargs):
        basket_evaluations.append(kwargs["evaluation"])
        Path(kwargs["output_csv"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_csv"]).write_text("ticker,weight\nPRIO3,0.2\n", encoding="utf-8")
        return {
            "status": "OK",
            "slots": kwargs["slots"],
            "output_csv": kwargs["output_csv"],
            "rows": [{"ticker": "PRIO3"}],
        }

    monkeypatch.setattr(run_mod, "run_daily_pipeline", fake_pipeline)
    monkeypatch.setattr(run_mod, "run_daily_basket", fake_basket)

    for profile in ("CON", "AGR"):
        exit_code = main(
            [
                "run",
                "--profile",
                profile,
                "--universe",
                "data/universes/ibov_sample.csv",
                "--context",
                str(context),
                "--report-output",
                str(tmp_path / f"{profile}_report.txt"),
                "--json-output",
                str(tmp_path / f"{profile}_report.json"),
                "--run-dir",
                str(tmp_path / profile),
                "--evaluation",
                str(evaluation),
                "--basket",
                "--basket-output",
                str(tmp_path / f"{profile}_basket.csv"),
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)

        assert exit_code == 0
        assert payload["basket"]["status"] == "OK"

    assert pipeline_profiles == ["CON", "AGR"]
    assert basket_evaluations == [str(evaluation), str(evaluation)]


def test_cli_run_exposes_multi_horizon_prediction_observer(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "latest_evaluation.json"
    _write_context(context)
    _write_multi_horizon_evaluation(evaluation)

    monkeypatch.setattr(
        run_mod,
        "run_daily_pipeline",
        lambda **kwargs: _fake_report(kwargs["profile"]),
    )

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--report-output",
            str(tmp_path / "report.txt"),
            "--json-output",
            str(tmp_path / "report.json"),
            "--run-dir",
            str(tmp_path / "latest"),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["prediction"]["engine_used"] == "multi_horizon_ridge"
    assert payload["prediction"]["horizons"] == [5, 20, 60]
    assert payload["prediction"]["d5_score"] == 51.0
    assert payload["prediction"]["d20_score"] == 58.0
    assert payload["prediction"]["d60_score"] == 66.0
    assert payload["prediction"]["combined_score"] == 59.85
    assert payload["prediction"]["dominant_horizon"] == "D60"
    assert payload["prediction"]["behavior"] == "POSITIONAL_SETUP"
    assert payload["prediction"]["weights"] == {"D5": 0.25, "D20": 0.35, "D60": 0.4}
    assert payload["prediction"]["model_quality"]["status"] == "OK"
    assert payload["top"][0]["dominant_horizon"] == "D60"
    assert payload["top"][0]["behavior"] == "POSITIONAL_SETUP"

    report_payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report_payload["prediction"]["engine"] == "multi_horizon_ridge"
    assert report_payload["prediction"]["horizons"] == [5, 20, 60]
    assert report_payload["prediction"]["combined_score"] == 59.85
    assert report_payload["prediction"]["dominant_horizon"] == "D60"
    assert report_payload["prediction"]["behavior"] == "POSITIONAL_SETUP"
    assert report_payload["decisions"][0]["prediction"] == {
        "d5_score": 51.0,
        "d20_score": 58.0,
        "d60_score": 66.0,
        "combined_score": 59.85,
        "dominant_horizon": "D60",
        "behavior": "POSITIONAL_SETUP",
    }


def test_cli_run_downgrades_actionable_when_model_quality_is_weak(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "latest_evaluation.json"
    _write_context(context)
    _write_multi_horizon_evaluation(evaluation)
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    payload["model_quality"]["status"] = "WEAK"
    payload["model_quality"]["ensemble_accuracy"] = 0.48
    payload["model_quality"]["edge"] = -0.02
    evaluation.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        run_mod,
        "run_daily_pipeline",
        lambda **kwargs: _fake_report(kwargs["profile"]),
    )

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--report-output",
            str(tmp_path / "report.txt"),
            "--json-output",
            str(tmp_path / "report.json"),
            "--run-dir",
            str(tmp_path / "latest"),
            "--json",
        ]
    )

    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["decision"]["actionable"] == 0
    assert result["decision"]["watch"] == 1
    assert result["report"]["decisions"][0]["permission"]["status"] == "WATCH"
    assert "model quality is weak" in result["report"]["decisions"][0]["permission"]["reasons"]


def test_cli_run_blocks_non_ok_prediction_evaluation(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "latest_evaluation.json"
    _write_context(context)
    evaluation.write_text(
        json.dumps(
            {
                "engine_used": "multi_horizon_ridge",
                "status": "FAIL",
                "reason": "insufficient assets for operational training",
                "experimental": False,
            }
        ),
        encoding="utf-8",
    )

    pipeline_called = False

    def fake_pipeline(**kwargs):
        nonlocal pipeline_called
        pipeline_called = True
        return _fake_report(kwargs["profile"])

    monkeypatch.setattr(run_mod, "run_daily_pipeline", fake_pipeline)

    exit_code = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--json",
        ]
    )

    assert exit_code == 1
    assert pipeline_called is False
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED"
    assert payload["reason"] == "invalid prediction evaluation"


def test_cli_run_blocks_experimental_prediction_without_explicit_allow(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_run as run_mod

    context = tmp_path / "context.json"
    evaluation = tmp_path / "latest_evaluation.json"
    _write_context(context)
    _write_multi_horizon_evaluation(evaluation)
    payload = json.loads(evaluation.read_text(encoding="utf-8"))
    payload["experimental"] = True
    evaluation.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        run_mod,
        "run_daily_pipeline",
        lambda **kwargs: _fake_report(kwargs["profile"]),
    )

    blocked_exit = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--json",
        ]
    )
    blocked = json.loads(capsys.readouterr().out)

    allowed_exit = main(
        [
            "run",
            "--profile",
            "CON",
            "--universe",
            "data/universes/ibov_sample.csv",
            "--context",
            str(context),
            "--evaluation",
            str(evaluation),
            "--allow-experimental-model",
            "--json",
        ]
    )
    allowed = json.loads(capsys.readouterr().out)

    assert blocked_exit == 1
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason"] == (
        "experimental prediction evaluation requires --allow-experimental-model"
    )
    assert allowed_exit == 0
    assert allowed["status"] == "OK"
    assert allowed["prediction"]["experimental"] is True
