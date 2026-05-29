from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import check_prices_dir
from pymercator.data.prices_yahoo import fetch_yahoo_prices_from_ticker_file
from pymercator.data.universe_builder import build_universe_csv_from_prices
from pymercator.data.universe_csv import validate_universe_csv
from pymercator.data.universe_diagnostics import diagnose_universe_csv
from pymercator.features_catalog import validate_features_catalog
from pymercator.manifest import (
    append_manifest_txt_section,
    load_manifest,
    save_manifest,
    update_manifest_files,
)
from pymercator.scenario_pack import run_scenario_pack, write_json, write_text


def _build_features_snapshot(features_file: str | Path) -> dict[str, Any]:
    payload = validate_features_catalog(features_file)

    return {
        "file": payload.get("file", str(features_file)),
        "valid": payload.get("valid", False),
        "features": payload.get("features", 0),
        "enabled": payload.get("enabled", 0),
        "required": payload.get("required", 0),
        "groups": payload.get("groups", {}),
        "errors": payload.get("errors", []),
    }


def _build_sentiment_snapshot(
    assets: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for asset in assets:
        ticker = str(asset.get("ticker", "")).strip()
        sector = str(asset.get("sector", "")).strip()
        value = asset.get("news_score")

        if value is None:
            continue

        try:
            news_score = float(value)
        except (TypeError, ValueError):
            continue

        rows.append(
            {
                "ticker": ticker,
                "sector": sector,
                "news_score": round(news_score, 2),
            }
        )

    if not rows:
        return {
            "assets": len(assets),
            "assets_with_news_score": 0,
            "avg_news_score": 0.0,
            "min_news_score": 0.0,
            "max_news_score": 0.0,
            "top_news": [],
            "bottom_news": [],
        }

    scores = [item["news_score"] for item in rows]

    return {
        "assets": len(assets),
        "assets_with_news_score": len(rows),
        "avg_news_score": round(sum(scores) / len(scores), 2),
        "min_news_score": round(min(scores), 2),
        "max_news_score": round(max(scores), 2),
        "top_news": sorted(
            rows,
            key=lambda item: item["news_score"],
            reverse=True,
        )[:limit],
        "bottom_news": sorted(
            rows,
            key=lambda item: item["news_score"],
        )[:limit],
    }


def _update_real_pack_manifest(
    *,
    pack_dir: str | Path,
    created_at: str,
    tickers_file: str,
    sentiment_dir: str | Path | None = None,
    features_file: str | Path = "config/features_catalog.json",
    prices_dir: str,
    universe_output: str,
    skip_fetch: bool,
    prices_check: dict[str, Any],
    universe_build: dict[str, Any],
    universe_diagnosis: dict[str, Any],
    context_source: str,
    context_file: str,
    context_preset: str,
    context_notes: str,
    context_snapshot: dict[str, Any] | None,
    execution_mode: str,
    allow_order_routing: bool,
    require_human_confirmation: bool,
) -> None:
    pack_path = Path(pack_dir)
    manifest = load_manifest(pack_path)
    files = update_manifest_files(
        manifest,
        (
            "00_real_pack_summary.txt",
            "00_real_pack_summary.json",
        ),
    )

    for file_name in (
        "00_real_pack_summary.txt",
        "00_real_pack_summary.json",
    ):
        if file_name not in files:
            files.append(file_name)

    manifest.update(
        {
            "source_command": "real-pack",
            "real_pack": True,
            "real_pack_created_at": created_at,
            "tickers_file": tickers_file,
            "sentiment_dir": str(sentiment_dir or ""),
            "sentiment_snapshot": _build_sentiment_snapshot(
                universe_build.get("assets", [])
            ),
            "features_file": str(features_file),
            "features_snapshot": _build_features_snapshot(features_file),
            "prices_dir": prices_dir,
            "universe_output": universe_output,
            "skip_fetch": skip_fetch,
            "prices_files": prices_check.get("files", 0),
            "prices_valid_files": prices_check.get("valid_files", 0),
            "prices_invalid_files": prices_check.get("invalid_files", 0),
            "universe_assets": universe_build.get("asset_count", 0),
            "universe_errors": universe_build.get("error_count", 0),
            "diagnosis_status": universe_diagnosis.get("data_status", "-"),
            "diagnosis_warnings": universe_diagnosis.get("warning_count", 0),
            "context_source": context_source,
            "context_file": context_file,
            "context_preset": context_preset,
            "context_notes": context_notes,
            "context_snapshot": context_snapshot or {},
            "execution_mode": execution_mode,
            "allow_order_routing": allow_order_routing,
            "require_human_confirmation": require_human_confirmation,
            "files": files,
        }
    )

    save_manifest(pack_path, manifest)

    append_manifest_txt_section(
        pack_path,
        "REAL PACK",
        [
            "SOURCE COMMAND      real-pack",
            "REAL PACK           True",
            f"TICKERS FILE        {tickers_file}",
            f"PRICES DIR          {prices_dir}",
            f"UNIVERSE OUTPUT     {universe_output}",
            f"SKIP FETCH          {skip_fetch}",
            f"PRICE FILES         {prices_check.get('files', 0)}",
            f"VALID PRICES        {prices_check.get('valid_files', 0)}",
            f"UNIVERSE ASSETS     {universe_build.get('asset_count', 0)}",
            "SENTIMENT SNAP      YES",
            f"FEATURES FILE       {features_file}",
            "FEATURES SNAP       YES",
            f"DIAGNOSIS           {universe_diagnosis.get('data_status', '-')}",
            f"CONTEXT SOURCE      {context_source}",
            f"CONTEXT FILE        {context_file or '-'}",
            f"CONTEXT PRESET      {context_preset or '-'}",
            f"CONTEXT NOTES       {context_notes or '-'}",
            f"CONTEXT SNAPSHOT    {'YES' if context_snapshot else 'NO'}",
            f"EXECUTION MODE      {execution_mode}",
            f"ORDER ROUTING       {'ENABLED' if allow_order_routing else 'DISABLED'}",
            f"HUMAN CONFIRM       {'REQUIRED' if require_human_confirmation else 'OPTIONAL'}",
        ],
    )


def _render_real_pack_summary(payload: dict[str, Any]) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR REAL PACK SUMMARY")
    lines.append(line)
    lines.append(f"{'STATUS':<20} {payload['status']}")
    lines.append(f"{'CREATED AT':<20} {payload['created_at']}")
    lines.append(f"{'TICKERS FILE':<20} {payload['tickers_file']}")
    lines.append(f"{'SENTIMENT DIR':<20} {payload.get('sentiment_dir') or '-'}")
    lines.append(f"{'PRICES DIR':<20} {payload['prices_dir']}")
    lines.append(f"{'UNIVERSE OUTPUT':<20} {payload['universe_output']}")
    lines.append(f"{'HEADLINE TAGS':<20} {', '.join(payload['headline_tags']) or '-'}")
    lines.append(f"{'CONTEXT SOURCE':<20} {payload.get('context_source', 'default')}")
    lines.append(f"{'CONTEXT FILE':<20} {payload.get('context_file') or '-'}")
    lines.append(f"{'CONTEXT PRESET':<20} {payload.get('context_preset') or '-'}")
    lines.append(f"{'CONTEXT NOTES':<20} {payload.get('context_notes') or '-'}")
    lines.append(f"{'EXECUTION MODE':<20} {payload.get('execution_mode', 'ANALYSIS_ONLY')}")
    lines.append(
        f"{'ORDER ROUTING':<20} "
        f"{'ENABLED' if payload.get('allow_order_routing') else 'DISABLED'}"
    )
    lines.append(
        f"{'HUMAN CONFIRM':<20} "
        f"{'REQUIRED' if payload.get('require_human_confirmation') else 'OPTIONAL'}"
    )
    lines.append("")

    lines.append("PRICES")
    lines.append(line)
    prices = payload.get("prices_check", {})
    lines.append(f"{'EXISTS':<20} {prices.get('exists', '-')}")
    lines.append(f"{'FILES':<20} {prices.get('files', '-')}")
    lines.append(f"{'VALID FILES':<20} {prices.get('valid_files', '-')}")
    lines.append(f"{'INVALID FILES':<20} {prices.get('invalid_files', '-')}")
    lines.append("")

    if payload.get("universe_build"):
        build = payload["universe_build"]
        lines.append("UNIVERSE BUILD")
        lines.append(line)
        lines.append(f"{'ASSETS':<20} {build.get('asset_count', '-')}")
        lines.append(f"{'ERRORS':<20} {build.get('error_count', '-')}")
        lines.append("")

    if payload.get("universe_validation"):
        validation = payload["universe_validation"]
        lines.append("UNIVERSE VALIDATION")
        lines.append(line)
        lines.append(f"{'VALID':<20} {validation.get('valid', '-')}")
        lines.append(f"{'ROWS':<20} {validation.get('rows', '-')}")
        lines.append("")

    if payload.get("universe_diagnosis"):
        diagnosis = payload["universe_diagnosis"]
        lines.append("UNIVERSE DIAGNOSIS")
        lines.append(line)
        lines.append(f"{'DATA STATUS':<20} {diagnosis.get('data_status', '-')}")
        lines.append(f"{'WARNINGS':<20} {diagnosis.get('warning_count', '-')}")
        lines.append(
            f"{'CONCENTRATION':<20} "
            f"{diagnosis.get('sector_concentration', {}).get('status', '-')}"
        )
        lines.append("")

    if payload.get("pack_dir"):
        lines.append("SCENARIO PACK")
        lines.append(line)
        lines.append(f"{'PACK DIR':<20} {payload['pack_dir']}")
        lines.append("")

    if payload.get("errors"):
        lines.append("ERRORS")
        lines.append(line)
        for error in payload["errors"]:
            lines.append(str(error))

    return "\n".join(lines)


def _failure_payload(
    *,
    status: str,
    created_at: str,
    tickers_file: str,
    sentiment_dir: str | Path | None = None,
    start: str,
    end: str | None,
    prices_dir: str,
    universe_output: str,
    headline_tags: list[str],
    errors: list[str],
    fetch_payload: dict[str, Any] | None = None,
    prices_check: dict[str, Any] | None = None,
    context_source: str = "default",
    context_file: str = "",
    context_preset: str = "",
    context_notes: str = "",
    context_snapshot: dict[str, Any] | None = None,
    execution_mode: str = "ANALYSIS_ONLY",
    allow_order_routing: bool = False,
    require_human_confirmation: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "created_at": created_at,
        "tickers_file": tickers_file,
        "sentiment_dir": str(sentiment_dir or ""),
        "start": start,
        "end": end,
        "prices_dir": prices_dir,
        "universe_output": universe_output,
        "headline_tags": headline_tags,
        "context_source": context_source,
        "context_file": context_file,
        "context_preset": context_preset,
        "context_notes": context_notes,
        "context_snapshot": context_snapshot or {},
        "execution_mode": execution_mode,
        "allow_order_routing": allow_order_routing,
        "require_human_confirmation": require_human_confirmation,
        "fetch": fetch_payload,
        "prices_check": prices_check,
        "universe_build": None,
        "universe_validation": None,
        "universe_diagnosis": None,
        "pack_dir": "",
        "errors": errors,
    }
    payload["summary_text"] = _render_real_pack_summary(payload)
    return payload


def run_real_pack(
    *,
    tickers_file: str,
    sentiment_dir: str | Path | None = None,
    features_file: str | Path = "config/features_catalog.json",
    start: str,
    prices_dir: str,
    universe_output: str,
    run_dir: str,
    headline_tags: list[str],
    universe_name: str = "IBOV",
    market_trend: str = "CHOPPY",
    market_volatility: str = "NORMAL",
    policy_path: str = "config/policy.json",
    limit: int = 20,
    end: str | None = None,
    skip_fetch: bool = False,
    context_source: str = "default",
    context_file: str = "",
    context_preset: str = "",
    context_notes: str = "",
    context_snapshot: dict[str, Any] | None = None,
    execution_mode: str = "ANALYSIS_ONLY",
    allow_order_routing: bool = False,
    require_human_confirmation: bool = True,
) -> dict[str, Any]:
    created_at = datetime.now().isoformat(timespec="seconds")
    errors: list[str] = []

    fetch_payload: dict[str, Any] | None = None

    if skip_fetch:
        fetch_payload = {
            "skipped": True,
            "reason": "skip_fetch enabled",
        }
    else:
        fetch_payload = fetch_yahoo_prices_from_ticker_file(
            tickers_file=tickers_file,
            start=start,
            end=end,
            output_dir=prices_dir,
        )

        if fetch_payload["failed"] > 0:
            errors.append(f"price fetch failed for {fetch_payload['failed']} tickers")

    prices_check = check_prices_dir(prices_dir)

    if (
        not prices_check["exists"]
        or prices_check["files"] == 0
        or prices_check["invalid_files"] > 0
    ):
        return _failure_payload(
            status="FAIL_PRICES",
            created_at=created_at,
            tickers_file=tickers_file,
            start=start,
            end=end,
            prices_dir=prices_dir,
            universe_output=universe_output,
            headline_tags=headline_tags,
            errors=errors or ["price directory is missing, empty, or invalid"],
            fetch_payload=fetch_payload,
            prices_check=prices_check,
            context_source=context_source,
            context_file=context_file,
            context_preset=context_preset,
            context_notes=context_notes,
        )

    universe_build = build_universe_csv_from_prices(
        prices_dir=prices_dir,
        output=universe_output,
        tickers_file=tickers_file,
        sentiment_dir=sentiment_dir,
    )

    universe_validation = validate_universe_csv(universe_output)

    if not universe_validation["valid"] or universe_build["asset_count"] == 0:
        payload = _failure_payload(
            status="FAIL_UNIVERSE",
            created_at=created_at,
            tickers_file=tickers_file,
            start=start,
            end=end,
            prices_dir=prices_dir,
            universe_output=universe_output,
            headline_tags=headline_tags,
            errors=errors or ["universe output is invalid"],
            fetch_payload=fetch_payload,
            prices_check=prices_check,
            context_source=context_source,
            context_file=context_file,
            context_preset=context_preset,
            context_notes=context_notes,
        )
        payload["universe_build"] = universe_build
        payload["universe_validation"] = universe_validation
        payload["summary_text"] = _render_real_pack_summary(payload)
        return payload

    universe_diagnosis = diagnose_universe_csv(
        path=universe_output,
        policy_path=policy_path,
    )

    pack_dir, scenario_summary_text, stability_text = run_scenario_pack(
        universe_path=universe_output,
        universe_name=universe_name,
        headline_tags=headline_tags,
        market_trend=market_trend,
        market_volatility=market_volatility,
        policy_path=policy_path,
        run_dir=run_dir,
        limit=limit,
    )

    payload = {
        "status": "OK",
        "created_at": created_at,
        "tickers_file": tickers_file,
        "start": start,
        "end": end,
        "prices_dir": prices_dir,
        "universe_output": universe_output,
        "headline_tags": headline_tags,
        "context_source": context_source,
        "context_file": context_file,
        "context_preset": context_preset,
        "context_notes": context_notes,
        "context_snapshot": context_snapshot or {},
        "execution_mode": execution_mode,
        "allow_order_routing": allow_order_routing,
        "require_human_confirmation": require_human_confirmation,
        "fetch": fetch_payload,
        "prices_check": prices_check,
        "universe_build": universe_build,
        "universe_validation": universe_validation,
        "universe_diagnosis": universe_diagnosis,
        "pack_dir": str(pack_dir),
        "scenario_summary_text": scenario_summary_text,
        "stability_text": stability_text,
        "errors": errors,
    }
    payload["summary_text"] = _render_real_pack_summary(payload)

    write_text(Path(pack_dir) / "00_real_pack_summary.txt", payload["summary_text"])
    write_json(Path(pack_dir) / "00_real_pack_summary.json", payload)

    _update_real_pack_manifest(
        pack_dir=pack_dir,
        created_at=created_at,
        tickers_file=tickers_file,
        sentiment_dir=sentiment_dir,
        features_file=features_file,
        prices_dir=prices_dir,
        universe_output=universe_output,
        skip_fetch=skip_fetch,
        prices_check=prices_check,
        universe_build=universe_build,
        universe_diagnosis=universe_diagnosis,
        context_source=context_source,
        context_file=context_file,
        context_preset=context_preset,
        context_notes=context_notes,
        context_snapshot=context_snapshot,
        execution_mode=execution_mode,
        allow_order_routing=allow_order_routing,
        require_human_confirmation=require_human_confirmation,
    )

    return payload
