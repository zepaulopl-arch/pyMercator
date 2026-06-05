from __future__ import annotations

import argparse
from typing import Any


def add_run_parser(subparsers: argparse._SubParsersAction[Any]) -> argparse.ArgumentParser:
    run_parser = subparsers.add_parser(
        "run",
        help="Run daily decision using an operational profile.",
        description="Run daily decision using an operational profile.",
    )
    run_parser.set_defaults(command="run")
    run_parser.add_argument("--profile", default="CON")
    run_parser.add_argument("--list", default="IBOV")
    run_parser.add_argument("--policy", default="config/policy.json")
    run_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
    run_parser.add_argument("--context", default="storage/context/latest_market_context.json")
    run_parser.add_argument("--matrix", default="storage/features/latest_feature_matrix.csv")
    run_parser.add_argument("--evaluation", default="storage/prediction/latest_evaluation.json")
    run_parser.add_argument("--observation-config", default="config/observation.json")
    run_parser.add_argument("--positions", default="storage/positions/current_positions.csv")
    run_parser.add_argument("--borrow-data", default="storage/borrow/latest_borrow_data.csv")
    run_parser.add_argument("--prices-dir", default="data/prices")
    run_parser.add_argument("--limit", type=int, default=20)
    run_parser.add_argument("--run-dir", default="storage/runs/latest")
    run_parser.add_argument(
        "--report-output",
        default="storage/reports/latest_daily_report.txt",
    )
    run_parser.add_argument(
        "--json-output",
        default="storage/reports/latest_daily_report.json",
    )
    run_parser.add_argument(
        "--basket",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate basket output. Default: enabled. Use --no-basket to disable.",
    )
    run_parser.add_argument("--slots", type=int, default=5)
    run_parser.add_argument("--min-sectors", type=int, default=3)
    run_parser.add_argument("--min-weight", type=float, default=0.10)
    run_parser.add_argument("--capital", type=float, default=100000.0)
    run_parser.add_argument("--risk-per-trade", type=float, default=0.005)
    run_parser.add_argument("--targets", type=int, default=2)
    run_parser.add_argument("--stop", default="progressive", choices=["progressive"])
    run_parser.add_argument(
        "--basket-output",
        default="storage/baskets/latest_daily_basket.csv",
    )
    run_parser.add_argument(
        "--db",
        default="data/aurum.db",
        help="SQLite operational history database. Default: data/aurum.db",
    )
    run_parser.add_argument("--allow-experimental-model", action="store_true")
    run_parser.add_argument("--json", action="store_true")
    return run_parser


def add_db_parser(subparsers: argparse._SubParsersAction[Any]) -> argparse.ArgumentParser:
    def add_common(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
        parser.add_argument(
            "--db",
            default=argparse.SUPPRESS if suppress_default else "data/aurum.db",
            help="SQLite operational history database. Default: data/aurum.db",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS if suppress_default else False,
        )

    db_parser = subparsers.add_parser(
        "db",
        help="Query local SQLite operational history.",
        description="Query local SQLite operational history.",
    )
    db_parser.set_defaults(command="db", db_command="status")
    add_common(db_parser)
    db_subparsers = db_parser.add_subparsers(dest="db_command")

    status_parser = db_subparsers.add_parser("status", help="Show DB STATUS")
    status_parser.set_defaults(db_command="status")
    add_common(status_parser, suppress_default=True)

    last_run_parser = db_subparsers.add_parser("last-run", help="Show DB LAST RUN")
    last_run_parser.set_defaults(db_command="last-run")
    add_common(last_run_parser, suppress_default=True)

    signal_parser = db_subparsers.add_parser("signal", help="Show DB SIGNAL <TICKER>")
    signal_parser.set_defaults(db_command="signal")
    signal_parser.add_argument("ticker")
    signal_parser.add_argument("--limit", type=int, default=20)
    add_common(signal_parser, suppress_default=True)

    rank_parser = db_subparsers.add_parser("rank-last", help="Show DB RANK LAST")
    rank_parser.set_defaults(db_command="rank-last")
    add_common(rank_parser, suppress_default=True)

    sim_parser = db_subparsers.add_parser("sim-last", help="Show DB SIM LAST")
    sim_parser.set_defaults(db_command="sim-last")
    add_common(sim_parser, suppress_default=True)
    return db_parser


def add_observe_parser(
    subparsers: argparse._SubParsersAction[Any],
) -> argparse.ArgumentParser:
    observe_parser = subparsers.add_parser(
        "observe",
        help="Rank assets for observation without generating trade signals.",
        description="Rank assets for observation without generating trade signals.",
    )
    observe_parser.set_defaults(command="observe", observe_command="run")
    observe_parser.add_argument("--list", default="IBOV")
    observe_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
    observe_parser.add_argument("--config", default="config/observation.json")
    observe_parser.add_argument("--limit", type=int, default=20)
    observe_parser.add_argument("--cluster", action="store_true")
    observe_parser.add_argument("--json", action="store_true")

    observe_subparsers = observe_parser.add_subparsers(dest="observe_command")
    calibrate_parser = observe_subparsers.add_parser(
        "calibrate",
        help="Calibrate observation thresholds from the current universe.",
    )
    calibrate_parser.set_defaults(observe_command="calibrate")
    calibrate_parser.add_argument("--list", default="IBOV")
    calibrate_parser.add_argument("--universe", default="data/universes/ibov_live.csv")
    calibrate_parser.add_argument("--config", default="config/observation.json")
    calibrate_parser.add_argument(
        "--output",
        default="storage/calibration/latest_observation_calibration.json",
    )
    calibrate_parser.add_argument("--json", action="store_true")
    return observe_parser


def add_positions_parser(
    subparsers: argparse._SubParsersAction[Any],
) -> argparse.ArgumentParser:
    pos_parser = subparsers.add_parser("pos", help="Position file utilities")
    pos_parser.set_defaults(command="pos")
    pos_parser.add_argument("--json", action="store_true", dest="pos_json")
    pos_subparsers = pos_parser.add_subparsers(dest="pos_command")
    pos_show_parser = pos_subparsers.add_parser("show", help="Show current positions")
    pos_show_parser.set_defaults(pos_command="show")
    pos_show_parser.add_argument(
        "--file",
        default="storage/positions/current_positions.csv",
    )
    pos_show_parser.add_argument("--json", action="store_true")
    pos_import_parser = pos_subparsers.add_parser("import", help="Import positions CSV")
    pos_import_parser.set_defaults(pos_command="import")
    pos_import_parser.add_argument("--file", required=True)
    pos_import_parser.add_argument(
        "--output",
        default="storage/positions/current_positions.csv",
    )
    pos_import_parser.add_argument("--json", action="store_true")
    return pos_parser


def add_basket_parser(
    subparsers: argparse._SubParsersAction[Any],
    *,
    default_paths: dict[str, Any],
) -> argparse.ArgumentParser:
    basket_parser = subparsers.add_parser("basket", help="Basket utilities")
    basket_parser.set_defaults(command="basket")
    basket_parser.add_argument("--profile", default="")
    basket_parser.add_argument("--json", action="store_true")
    basket_subparsers = basket_parser.add_subparsers(dest="basket_command")

    basket_daily_parser = basket_subparsers.add_parser("daily", help="Create daily basket")
    basket_daily_parser.set_defaults(basket_command="daily")
    basket_daily_parser.add_argument("--slots", type=int, default=5)
    basket_daily_parser.add_argument("--min-sectors", type=int, default=3)
    basket_daily_parser.add_argument("--min-weight", type=float, default=0.10)
    basket_daily_parser.add_argument("--capital", type=float, default=100000.0)
    basket_daily_parser.add_argument("--risk-per-trade", type=float, default=0.005)
    basket_daily_parser.add_argument("--targets", type=int, default=2)
    basket_daily_parser.add_argument(
        "--stop",
        default="progressive",
        choices=["progressive"],
    )
    basket_daily_parser.add_argument(
        "--prices-dir",
        default=default_paths.get("prices_dir", "data/prices"),
    )
    basket_daily_parser.add_argument(
        "--universe",
        default=default_paths.get(
            "universe_output",
            "data/universes/ibov_live.csv",
        ),
    )
    basket_daily_parser.add_argument(
        "--matrix",
        default=default_paths.get(
            "feature_matrix",
            "storage/features/latest_feature_matrix.csv",
        ),
    )
    basket_daily_parser.add_argument(
        "--evaluation",
        default=default_paths.get(
            "prediction_evaluation",
            "storage/prediction/latest_evaluation.json",
        ),
    )
    basket_daily_parser.add_argument(
        "--output",
        default="storage/baskets/latest_daily_basket.csv",
    )
    basket_daily_parser.add_argument("--daily-report", default="")

    basket_show_parser = basket_subparsers.add_parser("show", help="Show latest basket")
    basket_show_parser.set_defaults(basket_command="show")
    basket_show_parser.add_argument(
        "--output",
        default="storage/baskets/latest_daily_basket.csv",
    )
    basket_show_parser.add_argument("--details", action="store_true")
    return basket_parser


def add_borrow_parser(
    subparsers: argparse._SubParsersAction[Any],
) -> argparse.ArgumentParser:
    borrow_parser = subparsers.add_parser("borrow", help="Borrow data utilities")
    borrow_parser.set_defaults(command="borrow")
    borrow_parser.add_argument("--json", action="store_true")
    borrow_subparsers = borrow_parser.add_subparsers(dest="borrow_command")

    show_parser = borrow_subparsers.add_parser("show", help="Show borrow data")
    show_parser.set_defaults(borrow_command="show")
    show_parser.add_argument("--file", default="")
    show_parser.add_argument("--json", action="store_true")

    import_parser = borrow_subparsers.add_parser("import", help="Import borrow CSV")
    import_parser.set_defaults(borrow_command="import")
    import_parser.add_argument("--file", required=True)
    import_parser.add_argument("--output", default="")
    import_parser.add_argument("--json", action="store_true")

    diagnose_parser = borrow_subparsers.add_parser("diagnose", help="Diagnose borrow data")
    diagnose_parser.set_defaults(borrow_command="diagnose")
    diagnose_parser.add_argument("--file", default="")
    diagnose_parser.add_argument("--tickers-file", default="data/universes/ibov_live.csv")
    diagnose_parser.add_argument("--json", action="store_true")
    return borrow_parser


def add_context_parser(
    subparsers: argparse._SubParsersAction[Any],
) -> argparse.ArgumentParser:
    context_parser = subparsers.add_parser("context", help="Manage market context")
    context_parser.set_defaults(command="context")
    context_parser.add_argument("--json", action="store_true")
    context_parser.add_argument("--context", default="")
    context_parser.add_argument("--context-preset", default="")
    context_parser.add_argument("--headline-tags", default="")
    context_parser.add_argument("--market-trend", default="CHOPPY")
    context_parser.add_argument("--market-volatility", default="NORMAL")
    context_subparsers = context_parser.add_subparsers(dest="context_command")

    auto_parser = context_subparsers.add_parser(
        "auto",
        help="Auto generate market context",
    )
    auto_parser.set_defaults(context_command="auto")
    auto_parser.add_argument("--indices-dir", required=True)
    auto_parser.add_argument("--output", required=True)
    auto_parser.add_argument(
        "--thresholds",
        default="config/market_context_thresholds.json",
    )

    calibrate_parser = context_subparsers.add_parser(
        "calibrate",
        help="Calibrate market context thresholds from index history.",
    )
    calibrate_parser.set_defaults(context_command="calibrate")
    calibrate_parser.add_argument("--indices-dir", required=True)
    calibrate_parser.add_argument(
        "--output",
        default="storage/calibration/latest_market_context_calibration.json",
    )

    template_parser = context_subparsers.add_parser(
        "template",
        help="Write market context template",
    )
    template_parser.set_defaults(context_command="template")
    template_parser.add_argument("--output", required=True)
    context_subparsers.add_parser(
        "presets",
        help="List available market context presets",
    ).set_defaults(context_command="presets")
    check_context_parser = context_subparsers.add_parser(
        "check",
        help="Validate a market context file",
    )
    check_context_parser.set_defaults(context_command="check")
    check_context_parser.add_argument("--file", required=True)

    sources_parser = context_subparsers.add_parser(
        "sources",
        help="Show market context source diagnostics",
    )
    sources_parser.set_defaults(context_command="sources")
    sources_parser.add_argument(
        "--file",
        default="storage/context/latest_market_context.json",
    )
    sources_parser.add_argument("--json", action="store_true")

    show_parser = context_subparsers.add_parser(
        "show",
        help="Show consolidated market context",
    )
    show_parser.set_defaults(context_command="show")
    show_parser.add_argument(
        "--file",
        default="storage/context/latest_market_context.json",
    )
    show_parser.add_argument("--json", action="store_true")

    refresh_parser = context_subparsers.add_parser(
        "refresh",
        help="Refresh market context source diagnostics",
    )
    refresh_parser.set_defaults(context_command="refresh")
    refresh_parser.add_argument(
        "--file",
        default="storage/context/latest_market_context.json",
    )
    refresh_parser.add_argument("--source", default="")
    refresh_parser.add_argument("--all", action="store_true")
    refresh_parser.add_argument("--config", default="config/market_context.json")
    refresh_parser.add_argument("--timeout", type=int, default=10)
    refresh_parser.add_argument("--json", action="store_true")
    return context_parser
