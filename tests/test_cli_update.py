import json
from pathlib import Path

from pymercator.cli import main


def _patch_update_ok(monkeypatch):
    import pymercator.cli_update as update_mod

    monkeypatch.setattr(
        update_mod,
        "fetch_yahoo_prices_from_ticker_file",
        lambda **kwargs: {"failed": 0, "fetched": 1, "requested": 1},
    )
    monkeypatch.setattr(
        update_mod,
        "check_prices_dir",
        lambda prices_dir: {"exists": True, "files": 1, "invalid_files": 0},
    )
    monkeypatch.setattr(
        update_mod,
        "fetch_indices_prices",
        lambda **kwargs: {"status": "OK", "required_failed": 0, "fetched": 1},
    )
    monkeypatch.setattr(
        update_mod,
        "check_indices_prices_dir",
        lambda prices_dir: {"exists": True, "files": 1, "invalid_files": 0},
    )
    monkeypatch.setattr(
        update_mod,
        "write_auto_market_context",
        lambda **kwargs: {
            "output": kwargs["output"],
            "headline_tags": [],
            "market_trend": "CHOPPY",
            "market_volatility": "NORMAL",
        },
    )
    monkeypatch.setattr(
        update_mod,
        "validate_market_context",
        lambda path: {"valid": True, "path": str(path), "errors": []},
    )
    monkeypatch.setattr(
        update_mod,
        "build_universe_csv_from_prices",
        lambda **kwargs: {"asset_count": 1, "error_count": 0, "output": kwargs["output"]},
    )
    monkeypatch.setattr(
        update_mod,
        "validate_universe_csv",
        lambda path: {"valid": True, "path": str(path), "rows": 1},
    )
    monkeypatch.setattr(
        update_mod,
        "validate_features_catalog",
        lambda path: {"valid": True, "file": str(path), "errors": []},
    )
    monkeypatch.setattr(
        update_mod,
        "write_feature_matrix",
        lambda **kwargs: {
            "rows": 1,
            "assets": 1,
            "output": kwargs["output"],
        },
    )


def test_cli_update_accepts_defaults_and_prints_summary(monkeypatch, capsys):
    _patch_update_ok(monkeypatch)

    exit_code = main(["update", "--list", "IBOV"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "UPDATE | LIST IBOV | STATUS OK" in captured.out
    assert "prices_dir" in captured.out


def test_cli_update_json_uses_custom_paths(tmp_path: Path, monkeypatch, capsys):
    _patch_update_ok(monkeypatch)

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--tickers-file",
            str(tmp_path / "tickers.csv"),
            "--prices-dir",
            str(tmp_path / "prices"),
            "--matrix-output",
            str(tmp_path / "matrix.csv"),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "OK"
    assert payload["files"]["prices_dir"] == str(tmp_path / "prices")
    assert payload["files"]["matrix"] == str(tmp_path / "matrix.csv")


def test_cli_update_fails_clearly_on_step_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_update as update_mod

    monkeypatch.setattr(
        update_mod,
        "fetch_yahoo_prices_from_ticker_file",
        lambda **kwargs: {"failed": 1, "fetched": 0, "requested": 1},
    )

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--context-output",
            str(tmp_path / "context.json"),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "UPDATE | LIST IBOV | STATUS FAIL" in captured.out
    assert "STEP: prices" in captured.out


def test_cli_update_passes_default_long_history_and_cache(monkeypatch):
    import pymercator.cli_update as update_mod

    captured: dict[str, object] = {}

    def fake_prices(**kwargs):
        captured["start"] = kwargs["start"]
        captured["use_cache"] = kwargs["use_cache"]
        return {"failed": 0, "fetched": 1, "requested": 1}

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(update_mod, "fetch_yahoo_prices_from_ticker_file", fake_prices)

    exit_code = main(["update", "--list", "IBOV"])

    assert exit_code == 0
    assert captured["start"] == "2000-01-01"
    assert captured["use_cache"] is True


def test_cli_update_no_cache_disables_price_cache(monkeypatch):
    import pymercator.cli_update as update_mod

    captured: dict[str, object] = {}

    def fake_prices(**kwargs):
        captured["use_cache"] = kwargs["use_cache"]
        return {"failed": 0, "fetched": 1, "requested": 1}

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(update_mod, "fetch_yahoo_prices_from_ticker_file", fake_prices)

    exit_code = main(["update", "--list", "IBOV", "--no-cache"])

    assert exit_code == 0
    assert captured["use_cache"] is False


def test_cli_update_fails_when_feature_matrix_loses_universe_assets(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_update as update_mod

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(
        update_mod,
        "build_universe_csv_from_prices",
        lambda **kwargs: {
            "asset_count": 78,
            "error_count": 0,
            "output": kwargs["output"],
        },
    )
    monkeypatch.setattr(
        update_mod,
        "validate_universe_csv",
        lambda path: {"valid": True, "path": str(path), "rows": 78},
    )
    monkeypatch.setattr(
        update_mod,
        "write_feature_matrix",
        lambda **kwargs: {
            "rows": 1,
            "assets": 1,
            "output": kwargs["output"],
        },
    )

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--context-output",
            str(tmp_path / "context.json"),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "UPDATE | LIST IBOV | STATUS FAIL" in captured.out
    assert "STEP: features" in captured.out
    assert "feature matrix lost assets from universe" in captured.out


def test_cli_update_does_not_use_1900_for_indices(monkeypatch):
    import pymercator.cli_update as update_mod

    captured: dict[str, object] = {}

    def fake_indices(**kwargs):
        captured["indices_start"] = kwargs["start"]
        return {"status": "OK", "required_failed": 0, "fetched": 1}

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(update_mod, "fetch_indices_prices", fake_indices)

    exit_code = main(["update", "--list", "IBOV", "--start", "1900-01-01"])

    assert exit_code == 0
    assert captured["indices_start"] == "2000-01-01"


def test_cli_update_marks_optional_index_failure_as_partial(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_update as update_mod

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(
        update_mod,
        "fetch_indices_prices",
        lambda **kwargs: {
            "status": "OK_WITH_WARNINGS",
            "required_failed": 0,
            "optional_failed": 1,
            "cache_fallbacks": 0,
            "warnings": ["optional index IFNC.SA failed: no price data"],
        },
    )

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--context-output",
            str(tmp_path / "context.json"),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "UPDATE | LIST IBOV | STATUS PARTIAL" in captured.out
    assert "- impact: MEDIUM" in captured.out
    assert "- context_valid: YES" in captured.out
    assert "- regime_reliability: DEGRADED" in captured.out
    assert "WARNINGS:" in captured.out
    assert "optional index IFNC.SA failed" in captured.out


def test_cli_update_partial_index_cache_fallback_includes_operational_impact(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_update as update_mod

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(
        update_mod,
        "fetch_indices_prices",
        lambda **kwargs: {
            "status": "OK_WITH_WARNINGS",
            "required_failed": 0,
            "optional_failed": 0,
            "cache_fallbacks": 1,
            "warnings": ["index ^IEE used cache fallback: empty download"],
        },
    )
    context_output = tmp_path / "latest_market_context.json"

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--context-output",
            str(context_output),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PARTIAL"
    assert payload["impact"] == "LOW"
    assert payload["context_valid"] == "YES"
    assert payload["regime_reliability"] == "OK"
    assert payload["update_status"]["status"] == "PARTIAL"
    manifest = context_output.with_name("latest_update_status.json")
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["schema_version"] == "update_status.v1"
    assert manifest_payload["impact"] == "LOW"
    assert manifest_payload["freshness"]["freshness_status"] == "OK"


def test_cli_update_required_index_failure_is_fail(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    import pymercator.cli_update as update_mod

    _patch_update_ok(monkeypatch)
    monkeypatch.setattr(
        update_mod,
        "fetch_indices_prices",
        lambda **kwargs: {
            "status": "FAILED",
            "required_failed": 1,
            "optional_failed": 0,
            "cache_fallbacks": 0,
            "warnings": ["required index ^BVSP failed: empty download"],
        },
    )

    exit_code = main(
        [
            "update",
            "--list",
            "IBOV",
            "--context-output",
            str(tmp_path / "context.json"),
            "--json",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["failed_step"] == "indices"
    assert payload["impact"] == "HIGH"
    assert payload["context_valid"] == "NO"
