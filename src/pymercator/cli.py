from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pymercator.daily_auto import render_daily_auto_summary, run_daily_auto
from pymercator.data.prices_csv import check_prices_dir
from pymercator.data.prices_yahoo import (
    fetch_yahoo_prices_from_ticker_file,
    fetch_yahoo_prices_to_dir,
)
from pymercator.data.ticker_list import (
    validate_ticker_list_csv,
    write_starter_ticker_list,
)
from pymercator.data.universe_builder import build_universe_csv_from_prices
from pymercator.data.universe_csv import (
    summarize_universe_csv,
    validate_universe_csv,
    write_universe_template,
)
from pymercator.data.universe_diagnostics import diagnose_universe_csv
from pymercator.execution_policy import (
    load_execution_policy,
    validate_execution_policy,
    write_execution_policy_template,
)
from pymercator.features_catalog import (
    migrate_legacy_features_catalog,
    render_features_catalog,
    validate_features_catalog,
)
from pymercator.features_matrix import (
    render_feature_matrix_summary,
    write_feature_matrix,
)
from pymercator.human_confirmation import register_human_confirmation
from pymercator.indices_catalog import (
    render_indices_catalog,
    validate_indices_catalog,
)
from pymercator.indices_prices import (
    check_indices_prices_dir,
    fetch_indices_prices,
)
from pymercator.legacy_classification import write_legacy_classification
from pymercator.legacy_indices import migrate_legacy_indices_catalog
from pymercator.legacy_inventory import write_legacy_inventory
from pymercator.legacy_universe import write_legacy_universe_ticker_list
from pymercator.market_context import (
    list_market_context_presets,
    load_market_context,
    load_market_context_preset,
    validate_market_context,
    write_market_context_template,
)
from pymercator.market_context_auto import write_auto_market_context
from pymercator.pipeline import run_daily_pipeline
from pymercator.prediction_lab import (
    render_evaluation_summary,
    render_prediction_dataset_summary,
    render_prediction_lab_summary,
    run_prediction_lab,
    write_evaluation_report,
    write_prediction_dataset,
)
from pymercator.real_run import run_real_pack
from pymercator.reports.json_report import write_daily_report_json
from pymercator.reports.terminal import render_daily_report
from pymercator.scenario_pack import make_timestamped_run_dir, run_scenario_pack
from pymercator.sentiment_store import (
    check_sentiment_dir,
    migrate_legacy_sentiment,
    render_sentiment_check,
)


def _split_tags(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pymercator",
        description="Operational market permission system.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    daily = subparsers.add_parser("daily", help="Run daily operational pipeline.")
    _add_common_daily_arguments(daily)
    daily.add_argument(
        "--output",
        default="",
        help="Optional path to save the rendered TXT report.",
    )
    daily.add_argument(
        "--json-output",
        default="",
        help="Optional path to save the structured JSON report.",
    )
    daily.add_argument(
        "--run-dir",
        default="",
        help="Optional base directory for timestamped TXT and JSON outputs.",
    )

    pack = subparsers.add_parser(
        "scenario-pack",
        help="Run a standard multi-scenario operational pack.",
    )
    _add_common_daily_arguments(pack)
    pack.add_argument(
        "--run-dir",
        default="storage/scenario_runs",
        help="Base directory for timestamped scenario pack outputs.",
    )

    execution = subparsers.add_parser(
        "execution",
        help="Create and validate execution safety policy.",
    )
    execution_subparsers = execution.add_subparsers(
        dest="execution_command",
        required=True,
    )

    execution_template = execution_subparsers.add_parser(
        "template",
        help="Create an execution policy JSON template.",
    )
    execution_template.add_argument(
        "--output",
        default="config/execution_policy.json",
        help="Output execution policy JSON path.",
    )

    execution_check = execution_subparsers.add_parser(
        "check",
        help="Validate execution policy JSON.",
    )
    execution_check.add_argument(
        "--file",
        default="config/execution_policy.json",
        help="Execution policy JSON path.",
    )
    execution_check.add_argument(
        "--json",
        action="store_true",
        help="Print validation as JSON.",
    )

    confirm = subparsers.add_parser(
        "confirm",
        help="Register human confirmation for a pack decision.",
    )
    confirm.add_argument(
        "--pack",
        required=True,
        help="Scenario pack directory.",
    )
    confirm.add_argument(
        "--ticker",
        required=True,
        help="Ticker to confirm, e.g. PETR4.",
    )
    confirm.add_argument(
        "--decision",
        required=True,
        choices=["APPROVED", "REJECTED", "WATCH", "SKIPPED"],
        help="Human decision.",
    )
    confirm.add_argument(
        "--notes",
        default="",
        help="Optional human notes.",
    )
    confirm.add_argument(
        "--operator",
        default="manual",
        help="Operator name or identifier.",
    )
    confirm.add_argument(
        "--execution-policy",
        default="config/execution_policy.json",
        help="Path to execution policy JSON.",
    )
    confirm.add_argument(
        "--json",
        action="store_true",
        help="Print confirmation as JSON.",
    )

    context = subparsers.add_parser(
        "context",
        help="Create and validate market context files.",
    )
    context_subparsers = context.add_subparsers(
        dest="context_command",
        required=True,
    )

    context_auto = context_subparsers.add_parser(
        "auto",
        help="Build market context automatically from fetched indices.",
    )
    context_auto.add_argument(
        "--indices-dir",
        default="data/indices",
        help="Directory with fetched index price CSV files.",
    )
    context_auto.add_argument(
        "--output",
        default="config/market_context_auto.json",
        help="Output market context JSON path.",
    )
    context_auto.add_argument(
        "--json",
        action="store_true",
        help="Print generated context as JSON.",
    )

    context_template = context_subparsers.add_parser(
        "template",
        help="Create a market context JSON template.",
    )
    context_template.add_argument(
        "--output",
        default="config/market_context.json",
        help="Output context JSON path.",
    )

    context_presets = context_subparsers.add_parser(
        "presets",
        help="List available market context presets.",
    )
    context_presets.add_argument(
        "--json",
        action="store_true",
        help="Print presets as JSON.",
    )

    context_check = context_subparsers.add_parser(
        "check",
        help="Validate a market context JSON file.",
    )
    context_check.add_argument(
        "--file",
        default="config/market_context.json",
        help="Market context JSON path.",
    )
    context_check.add_argument(
        "--json",
        action="store_true",
        help="Print validation as JSON.",
    )

    indices = subparsers.add_parser(
        "indices",
        help="Inspect market indices catalog.",
    )
    indices_subparsers = indices.add_subparsers(
        dest="indices_command",
        required=True,
    )

    indices_catalog = indices_subparsers.add_parser(
        "catalog",
        help="Print indices catalog.",
    )
    indices_catalog.add_argument(
        "--file",
        default="config/indices_catalog.json",
        help="Indices catalog JSON path.",
    )
    indices_catalog.add_argument(
        "--json",
        action="store_true",
        help="Print catalog as JSON.",
    )

    indices_fetch = indices_subparsers.add_parser(
        "fetch",
        help="Fetch price CSV files for indices in catalog.",
    )
    indices_fetch.add_argument(
        "--catalog",
        default="config/indices_catalog.json",
        help="Indices catalog JSON path.",
    )
    indices_fetch.add_argument("--start", required=True, help="Start date YYYY-MM-DD.")
    indices_fetch.add_argument("--end", default="", help="Optional end date YYYY-MM-DD.")
    indices_fetch.add_argument(
        "--output",
        default="data/indices",
        help="Output directory for index price CSV files.",
    )
    indices_fetch.add_argument(
        "--json",
        action="store_true",
        help="Print fetch result as JSON.",
    )

    indices_prices_check = indices_subparsers.add_parser(
        "prices-check",
        help="Validate fetched index price CSV files.",
    )
    indices_prices_check.add_argument(
        "--prices-dir",
        default="data/indices",
        help="Directory with index price CSV files.",
    )
    indices_prices_check.add_argument(
        "--json",
        action="store_true",
        help="Print price check as JSON.",
    )

    indices_check = indices_subparsers.add_parser(
        "check",
        help="Validate indices catalog.",
    )
    indices_check.add_argument(
        "--file",
        default="config/indices_catalog.json",
        help="Indices catalog JSON path.",
    )
    indices_check.add_argument(
        "--json",
        action="store_true",
        help="Print validation as JSON.",
    )

    sentiment = subparsers.add_parser(
        "sentiment",
        help="Inspect sentiment/news score CSV files.",
    )
    sentiment_subparsers = sentiment.add_subparsers(
        dest="sentiment_command",
        required=True,
    )

    sentiment_check = sentiment_subparsers.add_parser(
        "check",
        help="Validate sentiment CSV directory.",
    )
    sentiment_check.add_argument(
        "--sentiment-dir",
        default="data/sentiment",
        help="Directory with sentiment CSV files.",
    )
    sentiment_check.add_argument(
        "--json",
        action="store_true",
        help="Print sentiment check as JSON.",
    )

    predict = subparsers.add_parser(
        "predict",
        help="Build prediction datasets and baseline evaluations.",
    )
    predict_subparsers = predict.add_subparsers(
        dest="predict_command",
        required=True,
    )

    predict_dataset = predict_subparsers.add_parser(
        "dataset",
        help="Build prediction dataset with engineered targets.",
    )
    predict_dataset.add_argument(
        "--matrix",
        default="storage/features/latest_feature_matrix.csv",
        help="Feature matrix CSV file.",
    )
    predict_dataset.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory with asset price CSV files.",
    )
    predict_dataset.add_argument(
        "--output",
        default="storage/prediction/latest_prediction_dataset.csv",
        help="Output prediction dataset CSV file.",
    )
    predict_dataset.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Forward target horizon in trading rows.",
    )
    predict_dataset.add_argument(
        "--min-history",
        type=int,
        default=20,
        help="Minimum historical rows before first observation.",
    )
    predict_dataset.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    predict_evaluate = predict_subparsers.add_parser(
        "evaluate",
        help="Run walk-forward baseline evaluation.",
    )
    predict_evaluate.add_argument(
        "--dataset",
        default="storage/prediction/latest_prediction_dataset.csv",
        help="Prediction dataset CSV file.",
    )
    predict_evaluate.add_argument(
        "--output",
        default="storage/prediction/latest_evaluation.json",
        help="Output evaluation JSON file.",
    )
    predict_evaluate.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Forward target horizon in trading rows.",
    )
    predict_evaluate.add_argument(
        "--min-train-rows",
        type=int,
        default=100,
        help="Minimum prior rows before walk-forward evaluation starts.",
    )
    predict_evaluate.add_argument(
        "--engines",
        default="",
        help="Comma-separated prediction engines. Empty means legacy default.",
    )
    predict_evaluate.add_argument(
        "--n-jobs",
        type=int,
        default=4,
        help="Training parallelism for legacy engines.",
    )
    predict_evaluate.add_argument(
        "--autotune",
        action="store_true",
        help="Enable optional legacy engine autotune.",
    )
    predict_evaluate.add_argument(
        "--autotune-iter",
        type=int,
        default=15,
        help="Autotune candidate iterations.",
    )
    predict_evaluate.add_argument(
        "--autotune-cv",
        type=int,
        default=3,
        help="Autotune time-series CV folds.",
    )

    predict_evaluate.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    predict_lab = predict_subparsers.add_parser(
        "lab",
        help="Build prediction dataset and run baseline evaluation.",
    )
    predict_lab.add_argument(
        "--matrix",
        default="storage/features/latest_feature_matrix.csv",
        help="Feature matrix CSV file.",
    )
    predict_lab.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory with asset price CSV files.",
    )
    predict_lab.add_argument(
        "--dataset-output",
        default="storage/prediction/latest_prediction_dataset.csv",
        help="Output prediction dataset CSV file.",
    )
    predict_lab.add_argument(
        "--evaluation-output",
        default="storage/prediction/latest_evaluation.json",
        help="Output evaluation JSON file.",
    )
    predict_lab.add_argument(
        "--horizon",
        type=int,
        default=5,
        help="Forward target horizon in trading rows.",
    )
    predict_lab.add_argument(
        "--min-history",
        type=int,
        default=20,
        help="Minimum historical rows before first observation.",
    )
    predict_lab.add_argument(
        "--min-train-rows",
        type=int,
        default=100,
        help="Minimum prior rows before walk-forward evaluation starts.",
    )
    predict_lab.add_argument(
        "--engines",
        default="",
        help="Comma-separated prediction engines. Empty means legacy default.",
    )
    predict_lab.add_argument(
        "--n-jobs",
        type=int,
        default=4,
        help="Training parallelism for legacy engines.",
    )
    predict_lab.add_argument(
        "--autotune",
        action="store_true",
        help="Enable optional legacy engine autotune.",
    )
    predict_lab.add_argument(
        "--autotune-iter",
        type=int,
        default=15,
        help="Autotune candidate iterations.",
    )
    predict_lab.add_argument(
        "--autotune-cv",
        type=int,
        default=3,
        help="Autotune time-series CV folds.",
    )

    predict_lab.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    features = subparsers.add_parser(
        "features",
        help="Inspect feature catalog.",
    )
    features_subparsers = features.add_subparsers(
        dest="features_command",
        required=True,
    )

    features_check = features_subparsers.add_parser(
        "check",
        help="Validate features catalog.",
    )
    features_check.add_argument(
        "--file",
        default="config/features_catalog.json",
        help="Features catalog JSON file.",
    )
    features_check.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    features_catalog = features_subparsers.add_parser(
        "catalog",
        help="Render features catalog.",
    )
    features_catalog.add_argument(
        "--file",
        default="config/features_catalog.json",
        help="Features catalog JSON file.",
    )
    features_catalog.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    features_matrix = features_subparsers.add_parser(
        "matrix",
        help="Build feature matrix preview from universe, prices, context, and catalog.",
    )
    features_matrix.add_argument(
        "--universe",
        default="data/universes/ibov_live.csv",
        help="Universe CSV file.",
    )
    features_matrix.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory with asset price CSV files.",
    )
    features_matrix.add_argument(
        "--context",
        default="config/market_context_auto.json",
        help="Market context JSON file.",
    )
    features_matrix.add_argument(
        "--features",
        default="config/features_catalog.json",
        help="Features catalog JSON file.",
    )
    features_matrix.add_argument(
        "--output",
        default="storage/features/latest_feature_matrix.csv",
        help="Output feature matrix CSV file.",
    )
    features_matrix.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    legacy = subparsers.add_parser(
        "legacy",
        help="Inspect legacy projects before selective migration.",
    )
    legacy_subparsers = legacy.add_subparsers(
        dest="legacy_command",
        required=True,
    )

    legacy_migrate_sentiment = legacy_subparsers.add_parser(
        "migrate-sentiment",
        help="Copy legacy sentiment CSV files into pyMercator.",
    )
    legacy_migrate_sentiment.add_argument(
        "--legacy-path",
        required=True,
        help="Path to the legacy pyTrade project.",
    )
    legacy_migrate_sentiment.add_argument(
        "--source-dir",
        default="data/sentiment",
        help="Relative legacy sentiment directory.",
    )
    legacy_migrate_sentiment.add_argument(
        "--output",
        default="data/sentiment",
        help="Output sentiment directory.",
    )
    legacy_migrate_sentiment.add_argument(
        "--json",
        action="store_true",
        help="Print migration summary as JSON.",
    )

    legacy_migrate_features = legacy_subparsers.add_parser(
        "migrate-features",
        help="Create pyMercator feature catalog from legacy project.",
    )
    legacy_migrate_features.add_argument(
        "--legacy-path",
        required=True,
        help="Path to the legacy pyTrade project.",
    )
    legacy_migrate_features.add_argument(
        "--output",
        default="config/features_catalog.json",
        help="Output features catalog JSON path.",
    )
    legacy_migrate_features.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON.",
    )

    legacy_migrate_indices = legacy_subparsers.add_parser(
        "migrate-indices",
        help="Migrate legacy indices YAML catalog into pyMercator JSON catalog.",
    )
    legacy_migrate_indices.add_argument(
        "--legacy-path",
        required=True,
        help="Path to the legacy pyTrade project.",
    )
    legacy_migrate_indices.add_argument(
        "--catalog-file",
        default="config/indices/catalog.yaml",
        help="Relative path to legacy indices catalog YAML.",
    )
    legacy_migrate_indices.add_argument(
        "--output",
        default="config/indices_catalog.json",
        help="Output indices catalog JSON path.",
    )
    legacy_migrate_indices.add_argument(
        "--json",
        action="store_true",
        help="Print migration summary as JSON.",
    )

    legacy_migrate_universe = legacy_subparsers.add_parser(
        "migrate-universe",
        help="Migrate legacy universe YAML files into pyMercator ticker CSV.",
    )
    legacy_migrate_universe.add_argument(
        "--legacy-path",
        required=True,
        help="Path to the legacy pyTrade project.",
    )
    legacy_migrate_universe.add_argument(
        "--assets-file",
        default="config/assets/ibov_assets.yaml",
        help="Relative path to legacy asset metadata YAML.",
    )
    legacy_migrate_universe.add_argument(
        "--universe-file",
        default="config/universes/ibov.yaml",
        help="Relative path to legacy universe YAML.",
    )
    legacy_migrate_universe.add_argument(
        "--output",
        default="data/universes/ibov_tickers.csv",
        help="Output ticker list CSV path.",
    )
    legacy_migrate_universe.add_argument(
        "--json",
        action="store_true",
        help="Print migration summary as JSON.",
    )

    legacy_classify = legacy_subparsers.add_parser(
        "classify",
        help="Classify a legacy inventory for selective migration.",
    )
    legacy_classify.add_argument(
        "--inventory",
        default="storage/legacy_inventory/legacy_inventory.json",
        help="Path to legacy_inventory.json.",
    )
    legacy_classify.add_argument(
        "--output",
        default="storage/legacy_inventory",
        help="Output directory for classification files.",
    )
    legacy_classify.add_argument(
        "--json",
        action="store_true",
        help="Print classification summary as JSON.",
    )

    legacy_scan = legacy_subparsers.add_parser(
        "scan",
        help="Scan a legacy project and write inventory reports.",
    )
    legacy_scan.add_argument(
        "--path",
        required=True,
        help="Path to the legacy project.",
    )
    legacy_scan.add_argument(
        "--output",
        default="storage/legacy_inventory",
        help="Output directory for inventory files.",
    )
    legacy_scan.add_argument(
        "--json",
        action="store_true",
        help="Print inventory summary as JSON.",
    )

    daily_auto = subparsers.add_parser(
        "daily-auto",
        help="Fetch indices, build automatic context, and run daily real workflow.",
    )
    daily_auto.add_argument(
        "--indices-catalog",
        default="config/indices_catalog.json",
        help="Indices catalog JSON path.",
    )
    daily_auto.add_argument(
        "--indices-start",
        default="2025-01-01",
        help="Start date for indices fetch.",
    )
    daily_auto.add_argument(
        "--indices-dir",
        default="data/indices",
        help="Directory for index price CSV files.",
    )
    daily_auto.add_argument(
        "--context-output",
        default="config/market_context_auto.json",
        help="Output path for automatic market context.",
    )
    daily_auto.add_argument(
        "--features-file",
        default="config/features_catalog.json",
        help="Features catalog JSON file.",
    )
    daily_auto.add_argument(
        "--feature-matrix-output",
        default="storage/features/latest_feature_matrix.csv",
        help="Output feature matrix CSV file.",
    )
    daily_auto.add_argument(
        "--prediction-dataset-output",
        default="storage/prediction/latest_prediction_dataset.csv",
        help="Output prediction dataset CSV file.",
    )
    daily_auto.add_argument(
        "--prediction-evaluation-output",
        default="storage/prediction/latest_evaluation.json",
        help="Output prediction evaluation JSON file.",
    )
    daily_auto.add_argument(
        "--prediction-horizon",
        type=int,
        default=5,
        help="Prediction target horizon.",
    )
    daily_auto.add_argument(
        "--prediction-min-history",
        type=int,
        default=20,
        help="Minimum history rows for prediction dataset.",
    )
    daily_auto.add_argument(
        "--prediction-min-train-rows",
        type=int,
        default=100,
        help="Minimum train rows for walk-forward evaluation.",
    )
    daily_auto.add_argument(
        "--prediction-engines",
        default="",
        help="Comma-separated prediction engines. Empty means all engines.",
    )



    daily_auto.add_argument(
        "--tickers-file",
        default="data/universes/ibov_tickers.csv",
        help="CSV file with ticker,sector columns.",
    )
    daily_auto.add_argument(
        "--sentiment-dir",
        default="data/sentiment",
        help="Directory with sentiment CSV files.",
    )

    daily_auto.add_argument(
        "--prices-start",
        default="2025-01-01",
        help="Start date for asset price fetch.",
    )
    daily_auto.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory where asset price CSV files are stored.",
    )
    daily_auto.add_argument(
        "--universe-output",
        default="data/universes/ibov_live.csv",
        help="Output universe CSV path.",
    )
    daily_auto.add_argument(
        "--run-dir",
        default="storage/scenario_runs",
        help="Base directory for timestamped scenario pack outputs.",
    )
    daily_auto.add_argument(
        "--universe-name",
        default="IBOV",
        help="Universe display name.",
    )
    daily_auto.add_argument(
        "--policy",
        default="config/policy.json",
        help="Path to policy JSON.",
    )
    daily_auto.add_argument(
        "--execution-policy",
        default="config/execution_policy.json",
        help="Path to execution policy JSON.",
    )
    daily_auto.add_argument(
        "--skip-asset-fetch",
        action="store_true",
        help="Skip asset price fetch and use existing asset CSV files.",
    )
    daily_auto.add_argument(
        "--skip-indices-fetch",
        action="store_true",
        help="Skip indices fetch and use existing index CSV files.",
    )
    daily_auto.add_argument(
        "--json",
        action="store_true",
        help="Print daily auto result as JSON.",
    )

    daily_real = subparsers.add_parser(
        "daily-real",
        help="Run the default daily real operational workflow.",
    )
    daily_real.add_argument(
        "--tickers-file",
        default="data/universes/ibov_tickers.csv",
        help="CSV file with ticker,sector columns.",
    )
    daily_real.add_argument(
        "--sentiment-dir",
        default="data/sentiment",
        help="Directory with sentiment CSV files.",
    )
    daily_real.add_argument(
        "--features-file",
        default="config/features_catalog.json",
        help="Features catalog JSON file.",
    )


    daily_real.add_argument(
        "--start",
        default="2025-01-01",
        help="Start date YYYY-MM-DD.",
    )
    daily_real.add_argument("--end", default="", help="Optional end date YYYY-MM-DD.")
    daily_real.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory where price CSV files are stored.",
    )
    daily_real.add_argument(
        "--universe-output",
        default="data/universes/ibov_live.csv",
        help="Output universe CSV path.",
    )
    daily_real.add_argument(
        "--universe-name",
        default="IBOV",
        help="Universe display name.",
    )
    daily_real.add_argument(
        "--headline-tags",
        default="",
        help="Comma-separated headline tags, e.g. IRAN,OIL,WAR.",
    )
    daily_real.add_argument(
        "--context",
        default="",
        help="Optional market context JSON file.",
    )
    daily_real.add_argument(
        "--context-preset",
        default="",
        help="Optional market context preset name.",
    )
    daily_real.add_argument(
        "--market-trend",
        default="CHOPPY",
        help="Market trend: UP, DOWN, CHOPPY, UNKNOWN.",
    )
    daily_real.add_argument(
        "--market-volatility",
        default="NORMAL",
        help="Market volatility: LOW, NORMAL, HIGH.",
    )
    daily_real.add_argument(
        "--policy",
        default="config/policy.json",
        help="Path to policy JSON.",
    )
    daily_real.add_argument(
        "--execution-policy",
        default="config/execution_policy.json",
        help="Path to execution policy JSON.",
    )
    daily_real.add_argument(
        "--run-dir",
        default="storage/scenario_runs",
        help="Base directory for timestamped scenario pack outputs.",
    )
    daily_real.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Rows to print in scenario reports.",
    )
    daily_real.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip Yahoo fetch and use existing price CSV files.",
    )
    daily_real.add_argument(
        "--json",
        action="store_true",
        help="Print daily real result as JSON.",
    )

    real = subparsers.add_parser(
        "real-pack",
        help="Fetch prices, build universe, diagnose it, and run scenario pack.",
    )
    real.add_argument(
        "--tickers-file",
        required=True,
        help="CSV file with ticker,sector columns.",
    )
    real.add_argument("--start", required=True, help="Start date YYYY-MM-DD.")
    real.add_argument("--end", default="", help="Optional end date YYYY-MM-DD.")
    real.add_argument(
        "--prices-dir",
        default="data/prices",
        help="Directory where price CSV files are stored.",
    )
    real.add_argument(
        "--universe-output",
        default="data/universes/ibov_live.csv",
        help="Output universe CSV path.",
    )
    real.add_argument(
        "--universe-name",
        default="IBOV",
        help="Universe display name.",
    )
    real.add_argument(
        "--headline-tags",
        default="",
        help="Comma-separated headline tags, e.g. IRAN,OIL,WAR.",
    )
    real.add_argument(
        "--context",
        default="",
        help="Optional market context JSON file.",
    )
    real.add_argument(
        "--context-preset",
        default="",
        help="Optional market context preset name.",
    )
    real.add_argument(
        "--market-trend",
        default="CHOPPY",
        help="Market trend: UP, DOWN, CHOPPY, UNKNOWN.",
    )
    real.add_argument(
        "--market-volatility",
        default="NORMAL",
        help="Market volatility: LOW, NORMAL, HIGH.",
    )
    real.add_argument(
        "--policy",
        default="config/policy.json",
        help="Path to policy JSON.",
    )
    real.add_argument(
        "--execution-policy",
        default="config/execution_policy.json",
        help="Path to execution policy JSON.",
    )
    real.add_argument(
        "--run-dir",
        default="storage/scenario_runs",
        help="Base directory for timestamped scenario pack outputs.",
    )
    real.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Rows to print in scenario reports.",
    )
    real.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip Yahoo fetch and use existing price CSV files.",
    )
    real.add_argument(
        "--json",
        action="store_true",
        help="Print real pack result as JSON.",
    )

    packs = subparsers.add_parser(
        "packs",
        help="List previously generated scenario packs.",
    )
    packs.add_argument(
        "--run-dir",
        default="storage/scenario_runs",
        help="Base directory containing scenario pack folders.",
    )
    packs.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of packs to list.",
    )
    packs.add_argument(
        "--json",
        action="store_true",
        help="Print pack index as JSON.",
    )

    prices = subparsers.add_parser(
        "prices",
        help="Fetch and inspect OHLCV price data.",
    )
    prices_subparsers = prices.add_subparsers(
        dest="prices_command",
        required=True,
    )

    fetch_prices = prices_subparsers.add_parser(
        "fetch",
        help="Fetch OHLCV prices from Yahoo Finance.",
    )
    fetch_prices.add_argument(
        "--tickers",
        required=True,
        help="Comma-separated tickers, e.g. PRIO3.SA,VALE3.SA.",
    )
    fetch_prices.add_argument("--start", required=True, help="Start date YYYY-MM-DD.")
    fetch_prices.add_argument("--end", default="", help="Optional end date YYYY-MM-DD.")
    fetch_prices.add_argument("--output", required=True, help="Output prices directory.")
    fetch_prices.add_argument(
        "--json",
        action="store_true",
        help="Print fetch result as JSON.",
    )

    fetch_list_prices = prices_subparsers.add_parser(
        "fetch-list",
        help="Fetch OHLCV prices from a ticker list CSV.",
    )
    fetch_list_prices.add_argument(
        "--tickers-file",
        required=True,
        help="CSV file with ticker,sector columns.",
    )
    fetch_list_prices.add_argument(
        "--start",
        required=True,
        help="Start date YYYY-MM-DD.",
    )
    fetch_list_prices.add_argument(
        "--end",
        default="",
        help="Optional end date YYYY-MM-DD.",
    )
    fetch_list_prices.add_argument(
        "--output",
        required=True,
        help="Output prices directory.",
    )
    fetch_list_prices.add_argument(
        "--json",
        action="store_true",
        help="Print fetch result as JSON.",
    )

    tickers_template = prices_subparsers.add_parser(
        "tickers-template",
        help="Create a starter ticker list CSV.",
    )
    tickers_template.add_argument(
        "--output",
        required=True,
        help="Output ticker list CSV path.",
    )

    tickers_check = prices_subparsers.add_parser(
        "tickers-check",
        help="Validate a ticker list CSV.",
    )
    tickers_check.add_argument(
        "--file",
        required=True,
        help="Ticker list CSV path.",
    )
    tickers_check.add_argument(
        "--json",
        action="store_true",
        help="Print validation as JSON.",
    )

    check_prices = prices_subparsers.add_parser(
        "check",
        help="Validate all price CSV files in a directory.",
    )
    check_prices.add_argument("--prices-dir", required=True, help="Prices directory.")
    check_prices.add_argument(
        "--json",
        action="store_true",
        help="Print check result as JSON.",
    )

    universe = subparsers.add_parser(
        "universe",
        help="Inspect and manage universe CSV files.",
    )
    universe_subparsers = universe.add_subparsers(
        dest="universe_command",
        required=True,
    )

    check = universe_subparsers.add_parser(
        "check",
        help="Validate a universe CSV schema and rows.",
    )
    check.add_argument("--file", required=True, help="Universe CSV path.")
    check.add_argument("--json", action="store_true", help="Print validation as JSON.")

    summary = universe_subparsers.add_parser(
        "summary",
        help="Summarize a universe CSV.",
    )
    summary.add_argument("--file", required=True, help="Universe CSV path.")
    summary.add_argument("--json", action="store_true", help="Print summary as JSON.")

    template = universe_subparsers.add_parser(
        "template",
        help="Create a universe CSV template.",
    )
    template.add_argument("--output", required=True, help="Output CSV path.")

    diagnose = universe_subparsers.add_parser(
        "diagnose",
        help="Diagnose universe quality and operational readiness.",
    )
    diagnose.add_argument("--file", required=True, help="Universe CSV path.")
    diagnose.add_argument(
        "--policy",
        default="config/policy.json",
        help="Policy JSON path.",
    )
    diagnose.add_argument(
        "--json",
        action="store_true",
        help="Print diagnosis as JSON.",
    )

    build = universe_subparsers.add_parser(
        "build",
        help="Build an operational universe CSV from price CSV files.",
    )
    build.add_argument(
        "--prices-dir",
        required=True,
        help="Directory with price CSV files.",
    )
    build.add_argument(
        "--sentiment-dir",
        default="",
        help="Optional directory with sentiment CSV files.",
    )

    build.add_argument("--output", required=True, help="Output universe CSV path.")
    build.add_argument(
        "--tickers-file",
        default="",
        help="Optional ticker list CSV used as sector source.",
    )
    build.add_argument(
        "--json",
        action="store_true",
        help="Print build result as JSON.",
    )

    return parser


def _add_common_daily_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--universe", required=True, help="Path to universe CSV.")
    parser.add_argument("--universe-name", default="IBOV", help="Universe display name.")
    parser.add_argument("--profile", default="CON", help="Profile: CON, BAL, AGR, RLX.")
    parser.add_argument(
        "--headline-risk",
        default="OFF",
        help="Headline risk: OFF, WATCH, ACTIVE, EXTREME.",
    )
    parser.add_argument(
        "--headline-tags",
        default="",
        help="Comma-separated headline tags, e.g. IRAN,OIL,WAR.",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Optional market context JSON file.",
    )
    parser.add_argument(
        "--context-preset",
        default="",
        help="Optional market context preset name.",
    )
    parser.add_argument(
        "--market-trend",
        default="CHOPPY",
        help="Market trend: UP, DOWN, CHOPPY, UNKNOWN.",
    )
    parser.add_argument(
        "--market-volatility",
        default="NORMAL",
        help="Market volatility: LOW, NORMAL, HIGH.",
    )
    parser.add_argument(
        "--policy",
        default="config/policy.json",
        help="Path to policy JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Rows to print in board.",
    )


def _write_output(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def _resolve_output_paths(
    *,
    output: str,
    json_output: str,
    run_dir: str,
) -> tuple[str, str, str]:
    if not run_dir:
        return output, json_output, ""

    resolved_run_dir = make_timestamped_run_dir(run_dir)

    resolved_output = output or str(resolved_run_dir / "report.txt")
    resolved_json_output = json_output or str(resolved_run_dir / "report.json")

    return resolved_output, resolved_json_output, str(resolved_run_dir)


def _run_sentiment_command(args: argparse.Namespace) -> int:
    if args.sentiment_command == "check":
        payload = check_sentiment_dir(args.sentiment_dir)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_sentiment_check(payload))

        return 0 if payload["exists"] and payload["invalid_files"] == 0 else 1

    raise ValueError(f"Unknown sentiment command: {args.sentiment_command}")


def _run_predict_command(args: argparse.Namespace) -> int:
    if args.predict_command == "dataset":
        payload = write_prediction_dataset(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            output=args.output,
            horizon=args.horizon,
            min_history=args.min_history,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_prediction_dataset_summary(payload))

        return 0

    if args.predict_command == "evaluate":
        payload = write_evaluation_report(
            dataset=args.dataset,
            output=args.output,
            horizon=args.horizon,
            min_train_rows=args.min_train_rows,
            engines=_parse_csv_arg(args.engines),
            n_jobs=args.n_jobs,
            autotune=args.autotune,
            autotune_iter=args.autotune_iter,
            autotune_cv=args.autotune_cv,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_evaluation_summary(payload))

        return 0

    if args.predict_command == "lab":
        payload = run_prediction_lab(
            matrix=args.matrix,
            prices_dir=args.prices_dir,
            dataset_output=args.dataset_output,
            evaluation_output=args.evaluation_output,
            horizon=args.horizon,
            min_history=args.min_history,
            min_train_rows=args.min_train_rows,
            engines=_parse_csv_arg(args.engines),
            n_jobs=args.n_jobs,
            autotune=args.autotune,
            autotune_iter=args.autotune_iter,
            autotune_cv=args.autotune_cv,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_prediction_lab_summary(payload))

        return 0

    raise ValueError(f"Unknown predict command: {args.predict_command}")


def _run_features_command(args: argparse.Namespace) -> int:
    if args.features_command in {"check", "catalog"}:
        payload = validate_features_catalog(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_features_catalog(payload))

        return 0 if payload["valid"] else 1

    if args.features_command == "matrix":
        payload = write_feature_matrix(
            universe=args.universe,
            prices_dir=args.prices_dir,
            context=args.context,
            features=args.features,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_feature_matrix_summary(payload))

        return 0

    raise ValueError(f"Unknown features command: {args.features_command}")


def _run_indices_command(args: argparse.Namespace) -> int:
    if args.indices_command == "fetch":
        payload = fetch_indices_prices(
            catalog=args.catalog,
            start=args.start,
            end=args.end or None,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES FETCH")
            print("-" * 100)
            print(f"{'CATALOG':<20} {payload['catalog']}")
            print(f"{'OUTPUT DIR':<20} {payload['output']}")
            print(f"{'STATUS':<20} {payload['status']}")
            print(f"{'REQUESTED':<20} {payload['requested']}")
            print(f"{'FETCHED':<20} {payload['fetched']}")
            print(f"{'FAILED':<20} {payload['failed']}")
            print(f"{'REQUIRED FAILED':<20} {payload['required_failed']}")
            print(f"{'OPTIONAL FAILED':<20} {payload['optional_failed']}")
            print(f"{'SKIPPED':<20} {payload['skipped']}")
            print(f"{'START':<20} {payload['start']}")
            print(f"{'END':<20} {payload['end'] or '-'}")
            print("")
            print("RESULTS")
            print("-" * 100)

            for item in payload["results"]:
                print(
                    f"{item['symbol']:<14} "
                    f"{item['status']:<8} "
                    f"{item['rows']:>5} "
                    f"{item['start'] or '-':<10} "
                    f"{item['end'] or '-':<10} "
                    f"{item['path']}"
                )

        return 0 if payload["required_failed"] == 0 else 1

    if args.indices_command == "prices-check":
        payload = check_indices_prices_dir(args.prices_dir)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES PRICES CHECK")
            print("-" * 100)
            print(f"{'PRICES DIR':<20} {payload['prices_dir']}")
            print(f"{'EXISTS':<20} {payload['exists']}")
            print(f"{'FILES':<20} {payload['files']}")
            print(f"{'VALID FILES':<20} {payload['valid_files']}")
            print(f"{'INVALID FILES':<20} {payload['invalid_files']}")
            print("")
            print("FILES")
            print("-" * 100)

            files = (
                payload.get("results")
                or payload.get("file_results")
                or payload.get("files_detail")
                or []
            )

            if not files:
                prices_path = Path(args.prices_dir)
                files = [
                    {
                        "file": item.name,
                        "status": "OK",
                        "rows": 0,
                        "start": "-",
                        "end": "-",
                    }
                    for item in sorted(prices_path.glob("*.csv"))
                ]

            for item in files:
                file_name = item.get("file") or item.get("path") or item.get("name") or "-"
                status = item.get("status") or ("OK" if item.get("valid") else "INVALID")

                print(
                    f"{file_name:<24} "
                    f"{status:<8} "
                    f"rows={item.get('rows', 0):<6} "
                    f"start={item.get('start', '-') or '-'} "
                    f"end={item.get('end', '-') or '-'}"
                )

        return 0 if payload["exists"] and payload["invalid_files"] == 0 else 1

    payload = validate_indices_catalog(args.file)

    if args.indices_command == "catalog":
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(render_indices_catalog(payload))

        return 0 if payload["valid"] else 1

    if args.indices_command == "check":
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR INDICES CATALOG CHECK")
            print("-" * 100)
            print(f"{'FILE':<20} {payload['path']}")
            print(f"{'VALID':<20} {payload['valid']}")
            print(f"{'INDICES':<20} {payload['count']}")

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    raise ValueError(f"Unknown indices command: {args.indices_command}")


def _run_execution_command(args: argparse.Namespace) -> int:
    if args.execution_command == "template":
        write_execution_policy_template(args.output)
        print(f"Execution policy template written to: {args.output}")
        return 0

    if args.execution_command == "check":
        payload = validate_execution_policy(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR EXECUTION POLICY CHECK")
            print("-" * 100)
            print(f"{'FILE':<24} {payload['path']}")
            print(f"{'VALID':<24} {payload['valid']}")

            policy = payload.get("policy", {})
            if policy:
                print(f"{'EXECUTION MODE':<24} {policy['execution_mode']}")
                print(f"{'ORDER ROUTING':<24} {policy['allow_order_routing']}")
                print(
                    f"{'HUMAN CONFIRMATION':<24} "
                    f"{policy['require_human_confirmation']}"
                )

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    raise ValueError(f"Unknown execution command: {args.execution_command}")


def _run_confirm_command(args: argparse.Namespace) -> int:
    payload = register_human_confirmation(
        pack=args.pack,
        ticker=args.ticker,
        decision=args.decision,
        notes=args.notes,
        operator=args.operator,
        execution_policy_path=args.execution_policy,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("PYMERCATOR HUMAN CONFIRMATION")
        print("-" * 100)
        print(f"{'PACK':<20} {payload['pack']}")
        print(f"{'TICKER':<20} {payload['ticker']}")
        print(f"{'DECISION':<20} {payload['human_decision']}")
        print(f"{'FOUND IN PACK':<20} {payload['found_in_pack']}")
        print(f"{'COUNT':<20} {payload['confirmation_count']}")
        print(f"{'MODE':<20} {payload['execution_mode']}")
        print(f"{'JSON':<20} {payload['json_path']}")
        print(f"{'TXT':<20} {payload['txt_path']}")

    return 0


def _resolve_market_context_args(args: argparse.Namespace) -> dict[str, Any]:
    context = {}
    context_source = "default"
    context_file = ""
    context_preset = ""

    if getattr(args, "context_preset", ""):
        context_preset = args.context_preset
        context = load_market_context_preset(context_preset)
        context_source = "preset"

    if getattr(args, "context", ""):
        context_file = args.context
        context = load_market_context(context_file)
        context_source = "file"

    cli_tags = _split_tags(getattr(args, "headline_tags", ""))

    if cli_tags:
        context_source = "cli"

    headline_tags = cli_tags or context.get("headline_tags", [])

    market_trend = getattr(args, "market_trend", "CHOPPY")
    if context and market_trend == "CHOPPY":
        market_trend = context.get("market_trend", market_trend)

    market_volatility = getattr(args, "market_volatility", "NORMAL")
    if context and market_volatility == "NORMAL":
        market_volatility = context.get(
            "market_volatility",
            market_volatility,
        )

    context_snapshot = dict(context)
    context_snapshot.update(
        {
            "headline_tags": headline_tags,
            "market_trend": market_trend,
            "market_volatility": market_volatility,
            "context_source": context_source,
            "context_file": context_file,
            "context_preset": context_preset,
        }
    )

    return {
        "headline_tags": headline_tags,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "context_source": context_source,
        "context_file": context_file,
        "context_preset": context_preset,
        "context_notes": context.get("notes", ""),
        "context_snapshot": context_snapshot,
    }


def _run_context_command(args: argparse.Namespace) -> int:
    if args.context_command == "auto":
        payload = write_auto_market_context(
            indices_dir=args.indices_dir,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT AUTO")
            print("-" * 100)
            print(f"{'INDICES DIR':<20} {payload['indices_dir']}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'HEADLINE TAGS':<20} {', '.join(payload['headline_tags']) or '-'}")
            print(f"{'MARKET TREND':<20} {payload['market_trend']}")
            print(f"{'VOLATILITY':<20} {payload['market_volatility']}")
            print(f"{'NOTES':<20} {payload['notes'] or '-'}")
            print("")
            print("METRICS")
            print("-" * 100)
            for key, value in payload["metrics"].items():
                print(f"{key:<42} {value}")

        return 0

    if args.context_command == "template":
        write_market_context_template(args.output)
        print(f"Market context template written to: {args.output}")
        return 0

    if args.context_command == "presets":
        payload = list_market_context_presets()

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT PRESETS")
            print("-" * 100)

            for name, context in payload.items():
                tags = ", ".join(context["headline_tags"]) or "-"
                print(
                    f"{name:<16} "
                    f"trend={context['market_trend']:<7} "
                    f"vol={context['market_volatility']:<7} "
                    f"tags={tags}"
                )

        return 0

    if args.context_command == "check":
        payload = validate_market_context(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR MARKET CONTEXT CHECK")
            print("-" * 100)
            print(f"{'FILE':<20} {payload['path']}")
            print(f"{'VALID':<20} {payload['valid']}")

            context = payload.get("context", {})
            if context:
                print(f"{'HEADLINE TAGS':<20} {', '.join(context['headline_tags']) or '-'}")
                print(f"{'MARKET TREND':<20} {context['market_trend']}")
                print(f"{'VOLATILITY':<20} {context['market_volatility']}")
                print(f"{'NOTES':<20} {context['notes']}")

            if payload["errors"]:
                print("")
                print("ERRORS")
                print("-" * 100)
                for error in payload["errors"]:
                    print(f"- {error}")

        return 0 if payload["valid"] else 1

    raise ValueError(f"Unknown context command: {args.context_command}")


def _run_legacy_command(args: argparse.Namespace) -> int:
    if args.legacy_command == "classify":
        payload = write_legacy_classification(
            inventory_path=args.inventory,
            output_dir=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY CLASSIFY")
            print("-" * 100)
            print(f"{'INVENTORY':<20} {payload['inventory_path']}")
            print(f"{'OUTPUT DIR':<20} {payload['output_dir']}")
            print(f"{'FILES':<20} {payload['file_count']}")
            print(f"{'TXT':<20} {payload['txt_path']}")
            print(f"{'JSON':<20} {payload['json_path']}")
            print("")
            print("DECISIONS")
            print("-" * 100)
            for decision, count in payload["decision_counts"].items():
                print(f"{decision:<20} {count}")

        return 0

    if args.legacy_command == "migrate-sentiment":
        payload = migrate_legacy_sentiment(
            legacy_path=args.legacy_path,
            source_dir=args.source_dir,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY SENTIMENT MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'SOURCE DIR':<20} {payload['source_dir']}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'COPIED':<20} {payload['copied']}")
            print(f"{'VALID FILES':<20} {payload['valid_files']}")
            print(f"{'INVALID FILES':<20} {payload['invalid_files']}")
            print(f"{'TICKERS':<20} {payload['tickers']}")

        return 0 if payload["copied"] > 0 and payload["invalid_files"] == 0 else 1

    if args.legacy_command == "migrate-features":
        payload = migrate_legacy_features_catalog(
            legacy_path=args.legacy_path,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY FEATURES MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'SOURCE FILE':<20} {payload['source_file'] or '-'}")
            print(f"{'OUTPUT':<20} {payload['output']}")
            print(f"{'VALID':<20} {payload['valid']}")
            print(f"{'FEATURES':<20} {payload['features']}")
            print(f"{'ENABLED':<20} {payload['enabled']}")
            print(f"{'REQUIRED':<20} {payload['required']}")

        return 0 if payload["valid"] else 1

    if args.legacy_command == "migrate-indices":
        payload = migrate_legacy_indices_catalog(
            legacy_path=args.legacy_path,
            catalog_file=args.catalog_file,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY INDICES MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<22} {payload['legacy_path']}")
            print(f"{'CATALOG YAML':<22} {payload['catalog_path']}")
            print(f"{'OUTPUT':<22} {payload['output']}")
            print(f"{'INDICES':<22} {payload['count']}")
            print(f"{'VALID':<22} {payload['valid']}")

        return 0 if payload["valid"] and payload["count"] > 0 else 1

    if args.legacy_command == "migrate-universe":
        payload = write_legacy_universe_ticker_list(
            legacy_path=args.legacy_path,
            assets_file=args.assets_file,
            universe_file=args.universe_file,
            output=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY UNIVERSE MIGRATION")
            print("-" * 100)
            print(f"{'LEGACY PATH':<22} {payload['legacy_path']}")
            print(f"{'ASSETS YAML':<22} {payload['assets_path']}")
            print(f"{'UNIVERSE YAML':<22} {payload['universe_path']}")
            print(f"{'OUTPUT':<22} {payload['output']}")
            print(f"{'ASSETS FOUND':<22} {payload['assets_found']}")
            print(f"{'UNIVERSE TICKERS':<22} {payload['universe_tickers_found']}")
            print(f"{'ROWS':<22} {payload['rows']}")
            print(f"{'UNKNOWN SECTORS':<22} {payload['unknown_sector_count']}")
            print(f"{'VALID':<22} {payload['valid']}")

        return 0 if payload["valid"] and payload["rows"] > 0 else 1

    if args.legacy_command == "scan":
        payload = write_legacy_inventory(
            legacy_path=args.path,
            output_dir=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("PYMERCATOR LEGACY SCAN")
            print("-" * 100)
            print(f"{'LEGACY PATH':<20} {payload['legacy_path']}")
            print(f"{'OUTPUT DIR':<20} {payload['output_dir']}")
            print(f"{'FILES':<20} {payload['file_count']}")
            print(f"{'PYTHON FILES':<20} {payload['python_files']}")
            print(f"{'DATA FILES':<20} {payload['data_files']}")
            print(f"{'LARGE FILES':<20} {payload['large_files_count']}")
            print(f"{'TXT':<20} {payload['txt_path']}")
            print(f"{'JSON':<20} {payload['json_path']}")

        return 0

    raise ValueError(f"Unknown legacy command: {args.legacy_command}")



def _parse_csv_arg(value: str) -> list[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


def _run_daily_auto_command(args: argparse.Namespace) -> int:
    execution_policy = load_execution_policy(args.execution_policy)

    payload = run_daily_auto(
        indices_catalog=args.indices_catalog,
        indices_start=args.indices_start,
        indices_dir=args.indices_dir,
        context_output=args.context_output,
        features_file=args.features_file,
        feature_matrix_output=args.feature_matrix_output,
        prediction_dataset_output=args.prediction_dataset_output,
        prediction_evaluation_output=args.prediction_evaluation_output,
        prediction_horizon=args.prediction_horizon,
        prediction_min_history=args.prediction_min_history,
        prediction_min_train_rows=args.prediction_min_train_rows,
        prediction_engines=_parse_csv_arg(args.prediction_engines),
        tickers_file=args.tickers_file,
        sentiment_dir=args.sentiment_dir,
        prices_start=args.prices_start,
        prices_dir=args.prices_dir,
        universe_output=args.universe_output,
        run_dir=args.run_dir,
        universe_name=args.universe_name,
        policy_path=args.policy,
        execution_mode=execution_policy["execution_mode"],
        allow_order_routing=execution_policy["allow_order_routing"],
        require_human_confirmation=execution_policy["require_human_confirmation"],
        skip_asset_fetch=args.skip_asset_fetch,
        fetch_indices=not args.skip_indices_fetch,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_daily_auto_summary(payload))

    return 0 if payload["status"] == "OK" else 1


def _run_real_pack_command(args: argparse.Namespace) -> int:
    context_values = _resolve_market_context_args(args)

    execution_policy = load_execution_policy(args.execution_policy)

    payload = run_real_pack(
        tickers_file=args.tickers_file,
        features_file=getattr(args, "features_file", "config/features_catalog.json"),
        start=args.start,
        end=args.end or None,
        prices_dir=args.prices_dir,
        universe_output=args.universe_output,
        run_dir=args.run_dir,
        headline_tags=context_values["headline_tags"],
        universe_name=args.universe_name,
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
        limit=args.limit,
        skip_fetch=args.skip_fetch,
        context_source=context_values["context_source"],
        context_file=context_values["context_file"],
        context_preset=context_values["context_preset"],
        context_notes=context_values["context_notes"],
        context_snapshot=context_values["context_snapshot"],
        execution_mode=execution_policy["execution_mode"],
        allow_order_routing=execution_policy["allow_order_routing"],
        require_human_confirmation=execution_policy["require_human_confirmation"],
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["summary_text"])

    return 0 if payload["status"] == "OK" else 1


def _run_daily_command(args: argparse.Namespace) -> int:
    output, json_output, resolved_run_dir = _resolve_output_paths(
        output=args.output,
        json_output=args.json_output,
        run_dir=args.run_dir,
    )

    context_values = _resolve_market_context_args(args)

    report = run_daily_pipeline(
        universe_path=args.universe,
        universe_name=args.universe_name,
        profile=args.profile,
        headline_risk=args.headline_risk,
        headline_tags=context_values["headline_tags"],
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
    )

    rendered = render_daily_report(report, limit=args.limit)

    if output:
        _write_output(output, rendered)

    if json_output:
        write_daily_report_json(report, json_output)

    print(rendered)

    if resolved_run_dir:
        print("")
        print(f"RUN DIR              {resolved_run_dir}")

    return 0


def _run_scenario_pack_command(args: argparse.Namespace) -> int:
    context_values = _resolve_market_context_args(args)

    pack_dir, summary_text, stability_text = run_scenario_pack(
        universe_path=args.universe,
        universe_name=args.universe_name,
        headline_tags=context_values["headline_tags"],
        market_trend=context_values["market_trend"],
        market_volatility=context_values["market_volatility"],
        policy_path=args.policy,
        run_dir=args.run_dir,
        limit=args.limit,
    )

    print(summary_text)
    print("")
    print(stability_text)
    print("")
    print(f"PACK DIR             {pack_dir}")

    return 0


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pack_top_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    scenarios = summary.get("scenarios", [])

    if not scenarios:
        return {}

    active = next(
        (
            scenario
            for scenario in scenarios
            if scenario.get("key") == "03_active_agr"
        ),
        None,
    )

    selected = active or scenarios[0]
    top = selected.get("top", {})

    return {
        "scenario": selected.get("key", "-"),
        "ticker": top.get("ticker", "-"),
        "permission": top.get("permission", "-"),
        "label": top.get("decision_label", "-"),
    }


def _load_pack_index(run_dir: str, limit: int) -> list[dict[str, Any]]:
    base = Path(run_dir)

    if not base.exists():
        return []

    rows: list[dict[str, Any]] = []

    for pack_dir in sorted(
        [path for path in base.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        manifest_path = pack_dir / "00_manifest.json"
        summary_path = pack_dir / "00_pack_summary.json"

        if not manifest_path.exists() or not summary_path.exists():
            continue

        manifest = _read_json(manifest_path)
        summary = _read_json(summary_path)
        top = _pack_top_from_summary(summary)

        scenarios = summary.get("scenarios", [])
        active = next(
            (
                scenario
                for scenario in scenarios
                if scenario.get("key") == "03_active_agr"
            ),
            scenarios[0] if scenarios else {},
        )

        is_real_pack = bool(manifest.get("real_pack", False))
        pack_type = "REAL" if is_real_pack else "SCEN"

        rows.append(
            {
                "pack": pack_dir.name,
                "path": str(pack_dir),
                "type": pack_type,
                "source_command": manifest.get("source_command", "scenario-pack"),
                "created_at": manifest.get(
                    "real_pack_created_at",
                    manifest.get("created_at", "-"),
                ),
                "universe_name": manifest.get("universe_name", "-"),
                "headline_tags": manifest.get("headline_tags", []),
                "market_trend": manifest.get("market_trend", "-"),
                "market_volatility": manifest.get("market_volatility", "-"),
                "active_posture": active.get("posture", "-"),
                "active_ready": active.get("ready", 0),
                "active_watch": active.get("watch", 0),
                "active_blocked": active.get("blocked", 0),
                "top_scenario": top.get("scenario", "-"),
                "top_ticker": top.get("ticker", "-"),
                "top_permission": top.get("permission", "-"),
                "top_label": top.get("label", "-"),
                "tickers_file": manifest.get("tickers_file", ""),
                "prices_dir": manifest.get("prices_dir", ""),
                "universe_output": manifest.get("universe_output", ""),
                "prices_valid_files": manifest.get("prices_valid_files", None),
                "universe_assets": manifest.get("universe_assets", None),
                "diagnosis_status": manifest.get("diagnosis_status", ""),
                "diagnosis_warnings": manifest.get("diagnosis_warnings", None),
            }
        )

        if len(rows) >= limit:
            break

    return rows


def _render_pack_index(rows: list[dict[str, Any]], run_dir: str) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR PACK INDEX")
    lines.append(line)
    lines.append(f"{'RUN DIR':<14} {run_dir}")
    lines.append(f"{'PACKS':<14} {len(rows)}")
    lines.append("")

    if not rows:
        lines.append("No scenario packs found.")
        return "\n".join(lines)

    lines.append(
        f"{'PACK':<16} "
        f"{'TYPE':<5} "
        f"{'CREATED_AT':<19} "
        f"{'ASSETS':>6} "
        f"{'STATUS':<18} "
        f"{'POSTURE':<12} "
        f"{'R/W/B':<9} "
        f"{'TOP':<6} "
        f"{'EXEC':<8} "
        f"{'LABEL':<20}"
    )
    lines.append(line)

    for row in rows:
        rwb = f"{row['active_ready']}/{row['active_watch']}/{row['active_blocked']}"

        label = str(row["top_label"])
        if len(label) > 20:
            label = label[:17] + "..."

        assets = row["universe_assets"]
        assets_text = str(assets) if assets is not None else "-"

        status = row["diagnosis_status"] or "-"
        if len(status) > 18:
            status = status[:15] + "..."

        lines.append(
            f"{row['pack']:<16} "
            f"{row['type']:<5} "
            f"{row['created_at']:<19} "
            f"{assets_text:>6} "
            f"{status:<18} "
            f"{row['active_posture']:<12} "
            f"{rwb:<9} "
            f"{row['top_ticker']:<6} "
            f"{row['top_permission']:<8} "
            f"{label:<20}"
        )

    return "\n".join(lines)


def _run_packs_command(args: argparse.Namespace) -> int:
    rows = _load_pack_index(args.run_dir, args.limit)

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(_render_pack_index(rows, args.run_dir))
    return 0


def _render_ticker_list_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR TICKER LIST CHECK",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'ROWS':<20} {payload['rows']}",
        f"{'MISSING COLUMNS':<20} {', '.join(payload['missing_columns']) or '-'}",
        f"{'EXTRA COLUMNS':<20} {', '.join(payload['extra_columns']) or '-'}",
        f"{'DUPLICATES':<20} {', '.join(payload['duplicate_tickers']) or '-'}",
        f"{'ROW ERRORS':<20} {len(payload['row_errors'])}",
    ]

    if payload["row_errors"]:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)

        for error in payload["row_errors"][:20]:
            lines.append(
                f"line={error['line']} field={error['field']} error={error['error']}"
            )

    return "\n".join(lines)


def _render_prices_fetch(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR PRICES FETCH",
        line,
        f"{'OUTPUT DIR':<20} {payload['output_dir']}",
        f"{'REQUESTED':<20} {payload['requested']}",
        f"{'FETCHED':<20} {payload['fetched']}",
        f"{'FAILED':<20} {payload['failed']}",
        f"{'START':<20} {payload['start']}",
        f"{'END':<20} {payload['end'] or '-'}",
        "",
        "RESULTS",
        line,
    ]

    for item in payload["results"]:
        status = "OK" if item["valid"] else "FAILED"
        lines.append(
            f"{item['ticker']:<12} "
            f"{status:<8} "
            f"{item['rows']:>6} "
            f"{str(item['start_date'] or '-'):>10} "
            f"{str(item['end_date'] or '-'):>10} "
            f"{item['path']}"
        )

        if item["error"]:
            lines.append(f"{'':<12} error={item['error']}")

    return "\n".join(lines)


def _render_prices_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR PRICES CHECK",
        line,
        f"{'PRICES DIR':<20} {payload['prices_dir']}",
        f"{'EXISTS':<20} {payload['exists']}",
        f"{'FILES':<20} {payload['files']}",
        f"{'VALID FILES':<20} {payload['valid_files']}",
        f"{'INVALID FILES':<20} {payload['invalid_files']}",
        "",
        "FILES",
        line,
    ]

    for item in payload["results"]:
        status = "OK" if item.get("valid") else "FAILED"
        lines.append(
            f"{Path(item['path']).name:<18} "
            f"{status:<8} "
            f"rows={item.get('rows', 0):<6} "
            f"start={item.get('start_date') or '-'} "
            f"end={item.get('end_date') or '-'}"
        )

        if item.get("error"):
            lines.append(f"{'':<18} error={item['error']}")

    return "\n".join(lines)


def _run_prices_command(args: argparse.Namespace) -> int:
    if args.prices_command == "fetch":
        payload = fetch_yahoo_prices_to_dir(
            tickers=_split_tags(args.tickers),
            start=args.start,
            end=args.end or None,
            output_dir=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_fetch(payload))

        return 0 if payload["required_failed"] == 0 else 1

    if args.prices_command == "fetch-list":
        payload = fetch_yahoo_prices_from_ticker_file(
            tickers_file=args.tickers_file,
            start=args.start,
            end=args.end or None,
            output_dir=args.output,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_fetch(payload))

        return 0 if payload["required_failed"] == 0 else 1

    if args.prices_command == "tickers-template":
        write_starter_ticker_list(args.output)
        print(f"Ticker list template written to: {args.output}")
        return 0

    if args.prices_command == "tickers-check":
        payload = validate_ticker_list_csv(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_ticker_list_check(payload))

        return 0 if payload["valid"] else 1

    if args.prices_command == "check":
        payload = check_prices_dir(args.prices_dir)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_prices_check(payload))

        if not payload["exists"] or payload["files"] == 0:
            return 1

        return 0 if payload["invalid_files"] == 0 else 1

    raise ValueError(f"Unknown prices command: {args.prices_command}")


def _render_universe_check(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE CHECK",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'VALID':<20} {payload['valid']}",
        f"{'ROWS':<20} {payload['rows']}",
        f"{'MISSING COLUMNS':<20} {', '.join(payload['missing_columns']) or '-'}",
        f"{'EXTRA COLUMNS':<20} {', '.join(payload['extra_columns']) or '-'}",
        f"{'DUPLICATES':<20} {', '.join(payload['duplicate_tickers']) or '-'}",
        f"{'ROW ERRORS':<20} {len(payload['row_errors'])}",
    ]

    if payload["row_errors"]:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)
        for error in payload["row_errors"][:20]:
            lines.append(
                f"line={error['line']} field={error['field']} error={error['error']}"
            )

    return "\n".join(lines)


def _render_universe_summary(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE SUMMARY",
        line,
        f"{'FILE':<20} {payload['path']}",
        f"{'ASSETS':<20} {payload['assets']}",
        f"{'AVG VOLUME BRL':<20} {payload['avg_volume_brl']:.2f}",
        f"{'AVG TREND':<20} {payload['avg_trend_score']:.2f}",
        f"{'AVG MOMENTUM':<20} {payload['avg_momentum_score']:.2f}",
        f"{'AVG VOLATILITY':<20} {payload['avg_volatility_pct']:.2f}",
        "",
        "SECTORS",
        line,
    ]

    for sector, count in payload["sectors"].items():
        lines.append(f"{sector:<20} {count}")

    lines.append("")
    lines.append("TOP VOLUME")
    lines.append(line)

    for item in payload["top_volume"]:
        lines.append(
            f"{item['ticker']:<8} "
            f"{item['sector']:<12} "
            f"{item['avg_volume_brl']:>14.2f}"
        )

    return "\n".join(lines)


def _render_universe_diagnose(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE DIAGNOSE",
        line,
        f"{'FILE':<22} {payload['path']}",
        f"{'POLICY':<22} {payload['policy']}",
        f"{'ASSETS':<22} {payload['assets']}",
        f"{'MIN ASSETS':<22} {payload['min_assets']}",
        f"{'DATA STATUS':<22} {payload['data_status']}",
        f"{'ASSET COUNT':<22} {payload['asset_count_status']}",
        f"{'WARNINGS':<22} {payload['warning_count']}",
        "",
        "COUNTS",
        line,
        f"{'LIQUIDITY LOW':<22} {payload['liquidity_low']}",
        f"{'VOLATILITY HIGH':<22} {payload['volatility_high']}",
        f"{'ATR HIGH':<22} {payload['atr_high']}",
        f"{'WEAK TREND':<22} {payload['weak_trend']}",
        f"{'WEAK MOMENTUM':<22} {payload['weak_momentum']}",
        f"{'MISSING TRADE PLAN':<22} {payload['missing_trade_plan']}",
        "",
        "SECTOR CONCENTRATION",
        line,
        f"{'STATUS':<22} {payload['sector_concentration']['status']}",
        f"{'TOP SECTOR':<22} {payload['sector_concentration']['top_sector']}",
        f"{'TOP COUNT':<22} {payload['sector_concentration']['top_sector_count']}",
        f"{'TOP PCT':<22} {payload['sector_concentration']['top_sector_pct']:.2f}%",
        "",
        "WARNINGS BY ASSET",
        line,
    ]

    warned = [item for item in payload["diagnostics"] if item["codes"]]

    if not warned:
        lines.append("No asset warnings.")
    else:
        for item in warned:
            lines.append(
                f"{item['ticker']:<8} "
                f"{item['sector']:<12} "
                f"vol={item['volatility_pct']:<6} "
                f"atr={item['atr_pct']:<6} "
                f"trend={item['trend_score']:<6} "
                f"mom={item['momentum_score']:<6} "
                f"{item['label']}"
            )

    return "\n".join(lines)


def _render_universe_build(payload: dict[str, Any]) -> str:
    line = "-" * 100
    lines = [
        "PYMERCATOR UNIVERSE BUILD",
        line,
        f"{'PRICES DIR':<20} {payload['prices_dir']}",
        f"{'TICKERS FILE':<20} {payload.get('tickers_file') or '-'}",
        f"{'OUTPUT':<20} {payload['output']}",
        f"{'ASSETS':<20} {payload['asset_count']}",
        f"{'ERRORS':<20} {payload['error_count']}",
        "",
        "ASSETS",
        line,
    ]

    lines.append(
        f"{'TICKER':<8} "
        f"{'SECTOR':<24} "
        f"{'CLOSE':>9} "
        f"{'TREND':>8} "
        f"{'MOM':>8} "
        f"{'VOL':>8} "
        f"{'ATR':>8} "
        f"{'NEWS':>8}"
    )
    lines.append(line)

    for asset in payload["assets"]:
        lines.append(
            f"{asset['ticker']:<8} "
            f"{asset['sector']:<24} "
            f"{asset['last_close']:>9.2f} "
            f"{asset['trend_score']:>8.2f} "
            f"{asset['momentum_score']:>8.2f} "
            f"{asset['volatility_pct']:>8.2f} "
            f"{asset['atr_pct']:>8.2f} "
            f"{asset.get('news_score', 50.0):>8.2f}"
        )

    if payload["errors"]:
        lines.append("")
        lines.append("ERRORS")
        lines.append(line)

        for error in payload["errors"]:
            lines.append(f"{error['file']} error={error['error']}")

    return "\n".join(lines)


def _run_universe_command(args: argparse.Namespace) -> int:
    if args.universe_command == "check":
        payload = validate_universe_csv(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_check(payload))

        return 0 if payload["valid"] else 1

    if args.universe_command == "summary":
        payload = summarize_universe_csv(args.file)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_summary(payload))

        return 0

    if args.universe_command == "template":
        write_universe_template(args.output)
        print(f"Universe template written to: {args.output}")
        return 0

    if args.universe_command == "build":
        payload = build_universe_csv_from_prices(
            prices_dir=args.prices_dir,
            output=args.output,
            sentiment_dir=getattr(args, "sentiment_dir", "") or None,
            tickers_file=getattr(args, "tickers_file", "") or None,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_build(payload))

        return 0 if payload["error_count"] == 0 and payload["asset_count"] > 0 else 1

    if args.universe_command == "diagnose":
        payload = diagnose_universe_csv(
            path=args.file,
            policy_path=args.policy,
        )

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_render_universe_diagnose(payload))

        return 0 if payload["data_status"] in {"PASS", "PASS_WITH_WARNINGS"} else 1

    raise ValueError(f"Unknown universe command: {args.universe_command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "daily":
            return _run_daily_command(args)

        if args.command == "scenario-pack":
            return _run_scenario_pack_command(args)

        if args.command == "packs":
            return _run_packs_command(args)

        if args.command == "daily-real":
            return _run_real_pack_command(args)

        if args.command == "daily-auto":
            return _run_daily_auto_command(args)

        if args.command == "context":
            return _run_context_command(args)

        if args.command == "execution":
            return _run_execution_command(args)

        if args.command == "indices":
            return _run_indices_command(args)

        if args.command == "sentiment":
            return _run_sentiment_command(args)

        if args.command == "predict":
            return _run_predict_command(args)

        if args.command == "features":
            return _run_features_command(args)

        if args.command == "confirm":
            return _run_confirm_command(args)

        if args.command == "legacy":
            return _run_legacy_command(args)

        if args.command == "real-pack":
            return _run_real_pack_command(args)

        if args.command == "prices":
            return _run_prices_command(args)

        if args.command == "universe":
            return _run_universe_command(args)

        parser.error(f"Unknown command: {args.command}")
        return 2

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
