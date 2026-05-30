from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pymercator.features_matrix import write_feature_matrix
from pymercator.indices_prices import check_indices_prices_dir, fetch_indices_prices
from pymercator.market_context_auto import write_auto_market_context
from pymercator.prediction_lab import run_prediction_lab
from pymercator.real_run import run_real_pack


def _attach_feature_matrix_to_manifest(
    *,
    pack_dir: str,
    feature_matrix: dict[str, Any],
) -> None:
    if not pack_dir:
        return

    manifest_path = Path(pack_dir) / "00_manifest.json"

    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["feature_matrix"] = {
        "file": str(feature_matrix.get("output", "")),
        "rows": int(feature_matrix.get("rows", 0)),
        "columns": len(feature_matrix.get("columns", [])),
        "missing_price_files": int(
            feature_matrix.get("missing_price_files_count", 0)
        ),
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )



def _attach_prediction_lab_to_manifest(
    *,
    pack_dir: str,
    prediction_lab: dict[str, object],
) -> None:
    if not pack_dir:
        return

    manifest_path = Path(pack_dir) / "00_manifest.json"

    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["prediction_lab"] = prediction_lab

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_daily_auto(
    *,
    indices_catalog: str = "config/indices_catalog.json",
    indices_start: str = "2025-01-01",
    indices_dir: str = "data/indices",
    context_output: str = "config/market_context_auto.json",
    features_file: str = "config/features_catalog.json",
    feature_matrix_output: str = "storage/features/latest_feature_matrix.csv",
    prediction_dataset_output: str = "storage/prediction/latest_prediction_dataset.csv",
    prediction_evaluation_output: str = "storage/prediction/latest_evaluation.json",
    prediction_horizon: int = 5,
    prediction_min_history: int = 20,
    prediction_min_train_rows: int = 100,
    prediction_engines: list[str] | None = None,
    prediction_n_jobs: int = 4,
    prediction_autotune: bool = False,
    prediction_autotune_iter: int = 15,
    prediction_autotune_cv: int = 3,
    tickers_file: str = "data/universes/ibov_tickers.csv",
    sentiment_dir: str = "data/sentiment",
    prices_start: str = "2025-01-01",
    prices_dir: str = "data/prices",
    universe_output: str = "data/universes/ibov_live.csv",
    run_dir: str = "storage/scenario_runs",
    universe_name: str = "IBOV",
    policy_path: str = "config/policy.json",
    execution_mode: str = "ANALYSIS_ONLY",
    allow_order_routing: bool = False,
    require_human_confirmation: bool = True,
    skip_asset_fetch: bool = True,
    fetch_indices: bool = True,
    limit: int = 20,
) -> dict[str, Any]:
    indices_fetch = {
        "status": "SKIPPED",
        "requested": 0,
        "fetched": 0,
        "failed": 0,
        "required_failed": 0,
        "optional_failed": 0,
        "skipped": 0,
        "results": [],
    }

    if fetch_indices:
        indices_fetch = fetch_indices_prices(
            catalog=indices_catalog,
            start=indices_start,
            output=indices_dir,
        )

    indices_check = check_indices_prices_dir(indices_dir)

    context_payload = write_auto_market_context(
        indices_dir=indices_dir,
        output=context_output,
    )

    real_payload = run_real_pack(
        tickers_file=tickers_file,
        sentiment_dir=sentiment_dir,
        features_file=features_file,
        start=prices_start,
        prices_dir=prices_dir,
        universe_output=universe_output,
        run_dir=run_dir,
        headline_tags=context_payload["headline_tags"],
        universe_name=universe_name,
        market_trend=context_payload["market_trend"],
        market_volatility=context_payload["market_volatility"],
        policy_path=policy_path,
        skip_fetch=skip_asset_fetch,
        context_source="file",
        context_file=context_output,
        context_preset="",
        context_notes=context_payload["notes"],
        context_snapshot={
            "headline_tags": context_payload["headline_tags"],
            "market_trend": context_payload["market_trend"],
            "market_volatility": context_payload["market_volatility"],
            "notes": context_payload["notes"],
            "source": "auto_indices",
            "metrics": context_payload["metrics"],
            "context_source": "file",
            "context_file": context_output,
            "context_preset": "",
        },
        execution_mode=execution_mode,
        allow_order_routing=allow_order_routing,
        require_human_confirmation=require_human_confirmation,
    )

    feature_matrix = write_feature_matrix(
        universe=universe_output,
        prices_dir=prices_dir,
        context=context_output,
        features=features_file,
        output=feature_matrix_output,
    )

    _attach_feature_matrix_to_manifest(
        pack_dir=str(real_payload.get("pack_dir", "")),
        feature_matrix=feature_matrix,
    )

    prediction_lab = run_prediction_lab(
        matrix=feature_matrix.get("output", feature_matrix_output),
        prices_dir=prices_dir,
        dataset_output=prediction_dataset_output,
        evaluation_output=prediction_evaluation_output,
        horizon=prediction_horizon,
        min_history=prediction_min_history,
        min_train_rows=prediction_min_train_rows,
        engines=prediction_engines,
        n_jobs=prediction_n_jobs,
        autotune=prediction_autotune,
        autotune_iter=prediction_autotune_iter,
        autotune_cv=prediction_autotune_cv,
    )

    _attach_prediction_lab_to_manifest(
        pack_dir=str(real_payload.get("pack_dir", "")),
        prediction_lab=prediction_lab,
    )

    return {
        "status": "OK" if real_payload.get("status") == "OK" else "FAILED",
        "indices_catalog": indices_catalog,
        "indices_dir": str(Path(indices_dir)),
        "sentiment_dir": str(Path(sentiment_dir)),
        "features_file": str(Path(features_file)),
        "indices_fetch": indices_fetch,
        "indices_check": indices_check,
        "context_output": context_output,
        "feature_matrix": {
            "file": feature_matrix.get("output", feature_matrix_output),
            "rows": feature_matrix.get("rows", 0),
            "columns": len(feature_matrix.get("columns", [])),
            "missing_price_files": feature_matrix.get(
                "missing_price_files_count",
                0,
            ),
        },
        "prediction_lab": prediction_lab,
        "context": context_payload,
        "real_pack": {
            "status": real_payload.get("status"),
            "pack_dir": real_payload.get("pack_dir"),
            "summary_text": real_payload.get("summary_text", ""),
        },
        "limit": limit,
    }


def render_daily_auto_summary(payload: dict[str, Any]) -> str:
    line = "-" * 118
    context = payload["context"]
    real_pack = payload["real_pack"]
    indices_fetch = payload["indices_fetch"]
    indices_check = payload["indices_check"]

    lines = [
        "PYMERCATOR DAILY AUTO SUMMARY",
        line,
        f"{'STATUS':<22} {payload['status']}",
        f"{'INDICES CATALOG':<22} {payload['indices_catalog']}",
        f"{'INDICES DIR':<22} {payload['indices_dir']}",
        f"{'SENTIMENT DIR':<22} {payload.get('sentiment_dir', '-')}",
        f"{'FEATURES FILE':<22} {payload.get('features_file', '-')}",
        f"{'CONTEXT OUTPUT':<22} {payload['context_output']}",
        "",
        "INDICES FETCH",
        line,
        f"{'STATUS':<22} {indices_fetch.get('status', '-')}",
        f"{'REQUESTED':<22} {indices_fetch.get('requested', 0)}",
        f"{'FETCHED':<22} {indices_fetch.get('fetched', 0)}",
        f"{'FAILED':<22} {indices_fetch.get('failed', 0)}",
        f"{'REQUIRED FAILED':<22} {indices_fetch.get('required_failed', 0)}",
        f"{'OPTIONAL FAILED':<22} {indices_fetch.get('optional_failed', 0)}",
        "",
        "INDICES CHECK",
        line,
        f"{'FILES':<22} {indices_check.get('files', 0)}",
        f"{'VALID FILES':<22} {indices_check.get('valid_files', 0)}",
        f"{'INVALID FILES':<22} {indices_check.get('invalid_files', 0)}",
        "",
        "AUTO CONTEXT",
        line,
        f"{'HEADLINE TAGS':<22} {', '.join(context['headline_tags']) or '-'}",
        f"{'MARKET TREND':<22} {context['market_trend']}",
        f"{'VOLATILITY':<22} {context['market_volatility']}",
        f"{'NOTES':<22} {context['notes'] or '-'}",
        "",
        "METRICS",
        line,
    ]

    for key, value in context["metrics"].items():
        lines.append(f"{key:<42} {value}")

    lines.extend(
        [
            "",
            "REAL PACK",
            line,
            f"{'STATUS':<22} {real_pack.get('status', '-')}",
            f"{'PACK DIR':<22} {real_pack.get('pack_dir', '-')}",
        ]
    )

    return "\n".join(lines)
