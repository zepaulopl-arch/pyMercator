from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pymercator.artifact_metadata import artifact_metadata
from pymercator.data.prices_csv import check_prices_dir
from pymercator.data.prices_yahoo import fetch_yahoo_prices_from_ticker_file
from pymercator.data.universe_builder import build_universe_csv_from_prices
from pymercator.data.universe_csv import validate_universe_csv
from pymercator.features_catalog import validate_features_catalog
from pymercator.features_matrix import write_feature_matrix
from pymercator.indices_prices import check_indices_prices_dir, fetch_indices_prices
from pymercator.market_context import validate_market_context
from pymercator.market_context_auto import write_auto_market_context
from pymercator.market_context_consolidator import write_market_context
from pymercator.update_freshness import build_data_freshness

DEFAULT_UPDATE_START = "2000-01-01"
DEFAULT_INDICES_START = "2000-01-01"


def default_tickers_file(list_name: str) -> str:
    preferred = Path("data") / "tickers" / f"{list_name.lower()}.csv"
    if preferred.exists():
        return str(preferred)
    return f"data/universes/{list_name.lower()}_tickers.csv"


def _step(name: str, status: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": name,
        "status": status,
        "payload": payload,
    }


def _safe_indices_start(start: str) -> str:
    return max(start, DEFAULT_INDICES_START)


def _step_warnings(name: str, payload: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for warning in payload.get("warnings", []) or []:
        warnings.append(f"{name}: {warning}")

    optional_failed = int(payload.get("optional_failed", 0) or 0)
    cache_fallbacks = int(payload.get("cache_fallbacks", 0) or 0)
    if optional_failed:
        warnings.append(f"{name}: {optional_failed} optional item(s) failed")
    if cache_fallbacks:
        warnings.append(f"{name}: {cache_fallbacks} item(s) used cache fallback")

    return warnings


def _find_step(
    steps: list[dict[str, Any]],
    name: str,
) -> dict[str, Any] | None:
    return next((step for step in steps if step.get("step") == name), None)


def _context_valid_from_steps(steps: list[dict[str, Any]]) -> bool:
    context_check = _find_step(steps, "context_check")
    if not context_check:
        return False
    payload = context_check.get("payload", {})
    return context_check.get("status") == "OK" and bool(payload.get("valid", True))


def _build_update_status(
    *,
    status: str,
    steps: list[dict[str, Any]],
    warnings: list[str],
    failed_step: str = "",
) -> dict[str, Any]:
    indices = _find_step(steps, "indices") or {}
    indices_payload = indices.get("payload", {})
    required_failed = int(indices_payload.get("required_failed", 0) or 0)
    optional_failed = int(indices_payload.get("optional_failed", 0) or 0)
    cache_fallbacks = int(indices_payload.get("cache_fallbacks", 0) or 0)
    context_valid = _context_valid_from_steps(steps)

    if status == "FAIL" or required_failed:
        impact = "HIGH"
        regime_reliability = "DEGRADED"
    elif optional_failed:
        impact = "MEDIUM"
        regime_reliability = "DEGRADED"
    elif cache_fallbacks:
        impact = "LOW"
        regime_reliability = "OK" if context_valid else "DEGRADED"
    elif warnings:
        impact = "LOW"
        regime_reliability = "OK" if context_valid else "DEGRADED"
    else:
        impact = "LOW"
        regime_reliability = "OK" if context_valid else "DEGRADED"

    if status == "FAIL" and failed_step in {"prices", "indices", "context", "context_check"}:
        context_valid = False

    freshness = build_data_freshness(steps)
    freshness_status = str(freshness.get("freshness_status", "OK")).upper()
    if freshness_status == "FAIL":
        status = "FAIL"
        failed_step = failed_step or "freshness"
        impact = "HIGH"
        regime_reliability = "DEGRADED"
        context_valid = False
    elif freshness_status == "WARNING" and status == "OK":
        status = "PARTIAL"
        impact = "LOW" if impact == "LOW" else impact

    return {
        "schema_version": "update_status.v1",
        "status": status,
        "impact": impact,
        "context_valid": "YES" if context_valid else "NO",
        "regime_reliability": regime_reliability,
        "warnings": warnings,
        "failed_step": failed_step,
        "freshness": freshness,
        "runtime": artifact_metadata(),
    }


def _update_status_path(context_output: str) -> Path:
    return Path(context_output).with_name("latest_update_status.json")


def _write_update_status(context_output: str, update_status: dict[str, Any]) -> str:
    output = _update_status_path(context_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(update_status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output)


def _fail_payload(
    *,
    list_name: str,
    step: str,
    reason: str,
    detail: Any,
    steps: list[dict[str, Any]],
    files: dict[str, str],
) -> dict[str, Any]:
    update_status = _build_update_status(
        status="FAIL",
        steps=steps,
        warnings=[],
        failed_step=step,
    )
    if "context" in files:
        files["update_status"] = _write_update_status(files["context"], update_status)
    return {
        "command": "update",
        "list": list_name,
        "status": "FAIL",
        "impact": update_status["impact"],
        "context_valid": update_status["context_valid"],
        "regime_reliability": update_status["regime_reliability"],
        "failed_step": step,
        "reason": reason,
        "detail": detail,
        "update_status": update_status,
        "steps": steps,
        "files": files,
    }


def run_update_flow(
    *,
    list_name: str = "IBOV",
    start: str = DEFAULT_UPDATE_START,
    end: str | None = None,
    tickers_file: str | None = None,
    prices_dir: str = "data/prices",
    indices_catalog: str = "config/indices_catalog.json",
    indices_dir: str = "data/indices",
    context_output: str = "storage/context/latest_market_context.json",
    universe_output: str = "data/universes/ibov_live.csv",
    features_catalog: str = "config/features_catalog.json",
    matrix_output: str = "storage/features/latest_feature_matrix.csv",
    context_config: str = "config/market_context.json",
    context_thresholds: str = "config/market_context_thresholds.json",
    use_cache: bool = True,
) -> dict[str, Any]:
    list_text = list_name.upper()
    resolved_end = end or date.today().isoformat()
    resolved_tickers = tickers_file or default_tickers_file(list_text)
    files = {
        "tickers_file": resolved_tickers,
        "prices_dir": prices_dir,
        "indices_catalog": indices_catalog,
        "indices_dir": indices_dir,
        "context": context_output,
        "universe": universe_output,
        "features_catalog": features_catalog,
        "matrix": matrix_output,
        "update_status": str(_update_status_path(context_output)),
        "context_config": context_config,
        "context_thresholds": context_thresholds,
    }
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_step = "startup"

    try:
        current_step = "prices"
        prices = fetch_yahoo_prices_from_ticker_file(
            tickers_file=resolved_tickers,
            start=start,
            end=resolved_end,
            output_dir=prices_dir,
            use_cache=use_cache,
        )
        status = "OK" if int(prices.get("failed", 0)) == 0 else "FAIL"
        if status == "OK" and int(prices.get("cache_fallbacks", 0) or 0) > 0:
            status = "PARTIAL"
        warnings.extend(_step_warnings("prices", prices))
        steps.append(_step("prices", status, prices))
        if status == "FAIL":
            return _fail_payload(
                list_name=list_text,
                step="prices",
                reason=f"price fetch failed for {prices.get('failed', 0)} tickers",
                detail=prices,
                steps=steps,
                files=files,
            )

        current_step = "prices_check"
        prices_check = check_prices_dir(prices_dir)
        status = (
            "OK"
            if prices_check.get("exists")
            and prices_check.get("files", 0) > 0
            and prices_check.get("invalid_files", 0) == 0
            else "FAIL"
        )
        steps.append(_step("prices_check", status, prices_check))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="prices_check",
                reason="prices directory is missing, empty, or invalid",
                detail=prices_check,
                steps=steps,
                files=files,
            )

        current_step = "indices"
        indices_start = _safe_indices_start(start)
        indices = fetch_indices_prices(
            catalog=indices_catalog,
            start=indices_start,
            end=resolved_end,
            output=indices_dir,
            use_cache=use_cache,
        )
        if int(indices.get("required_failed", 0)) > 0:
            status = "FAIL"
        elif (
            int(indices.get("optional_failed", 0) or 0) > 0
            or int(indices.get("cache_fallbacks", 0) or 0) > 0
        ):
            status = "PARTIAL"
        else:
            status = "OK"
        indices["requested_start"] = start
        indices["effective_start"] = indices_start
        warnings.extend(_step_warnings("indices", indices))
        steps.append(_step("indices", status, indices))
        if status == "FAIL":
            return _fail_payload(
                list_name=list_text,
                step="indices",
                reason="required indices failed to update",
                detail=indices,
                steps=steps,
                files=files,
            )

        current_step = "indices_check"
        indices_check = check_indices_prices_dir(indices_dir)
        status = (
            "OK"
            if indices_check.get("exists")
            and indices_check.get("files", 0) > 0
            and indices_check.get("invalid_files", 0) == 0
            else "FAIL"
        )
        steps.append(_step("indices_check", status, indices_check))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="indices_check",
                reason="indices directory is missing, empty, or invalid",
                detail=indices_check,
                steps=steps,
                files=files,
            )

        current_step = "context"
        previous_context: dict[str, Any] = {}
        context_path = Path(context_output)
        if context_path.exists():
            try:
                previous = json.loads(context_path.read_text(encoding="utf-8-sig"))
                previous_context = previous if isinstance(previous, dict) else {}
            except Exception:
                previous_context = {}
        auto_output = context_path.with_name("latest_market_context_auto.json")
        auto_context = write_auto_market_context(
            indices_dir=indices_dir,
            output=auto_output,
        )
        files["auto_context"] = str(auto_output)
        context = write_market_context(
            auto_context=auto_context,
            output=context_output,
            thresholds_path=context_thresholds,
            config_path=context_config,
            previous_context=previous_context,
        )
        steps.append(_step("context", "OK", context))

        current_step = "context_check"
        context_check = validate_market_context(context_output)
        status = "OK" if context_check.get("valid") else "FAIL"
        steps.append(_step("context_check", status, context_check))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="context_check",
                reason="market context is invalid",
                detail=context_check,
                steps=steps,
                files=files,
            )

        current_step = "universe"
        universe = build_universe_csv_from_prices(
            prices_dir=prices_dir,
            output=universe_output,
            tickers_file=resolved_tickers,
        )
        status = (
            "OK"
            if universe.get("asset_count", 0) > 0
            and universe.get("error_count", 0) == 0
            else "FAIL"
        )
        steps.append(_step("universe", status, universe))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="universe",
                reason="universe build failed or produced no assets",
                detail=universe,
                steps=steps,
                files=files,
            )

        current_step = "universe_check"
        universe_check = validate_universe_csv(universe_output)
        status = "OK" if universe_check.get("valid") else "FAIL"
        steps.append(_step("universe_check", status, universe_check))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="universe_check",
                reason="universe output is invalid",
                detail=universe_check,
                steps=steps,
                files=files,
            )

        current_step = "features_check"
        features_check = validate_features_catalog(features_catalog)
        status = "OK" if features_check.get("valid") else "FAIL"
        steps.append(_step("features_check", status, features_check))
        if status != "OK":
            return _fail_payload(
                list_name=list_text,
                step="features_check",
                reason="features catalog is invalid",
                detail=features_check,
                steps=steps,
                files=files,
            )

        current_step = "features"
        matrix_output_path = Path(matrix_output)
        matrix_tmp_output = str(
            matrix_output_path.with_name(f"{matrix_output_path.name}.tmp")
        )
        matrix = write_feature_matrix(
            universe=universe_output,
            prices_dir=prices_dir,
            context=context_output,
            features=features_catalog,
            output=matrix_tmp_output,
        )
        universe_assets = int(universe.get("asset_count", 0) or 0)
        matrix_assets = int(matrix.get("assets", matrix.get("rows", 0)) or 0)
        matrix_rows = int(matrix.get("rows", 0) or 0)
        lost_assets = max(universe_assets - matrix_assets, 0)
        status = (
            "OK"
            if matrix_rows > 0
            and matrix_assets > 0
            and matrix_assets >= universe_assets
            else "FAIL"
        )
        matrix["universe_assets"] = universe_assets
        matrix["matrix_assets"] = matrix_assets
        matrix["lost_assets"] = lost_assets
        steps.append(_step("features", status, matrix))
        if status != "OK":
            matrix["rejected_output"] = matrix.get("output", matrix_tmp_output)
            reason = "feature matrix has no rows"
            if matrix_rows > 0 and matrix_assets < universe_assets:
                reason = "feature matrix lost assets from universe"

            return _fail_payload(
                list_name=list_text,
                step="features",
                reason=reason,
                detail=matrix,
                steps=steps,
                files=files,
            )

        tmp_path = Path(matrix_tmp_output)
        if tmp_path.exists():
            matrix_output_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(matrix_output_path)
        matrix["output"] = str(matrix_output_path)

    except Exception as exc:
        return _fail_payload(
            list_name=list_text,
            step=current_step,
            reason=str(exc),
            detail={"error": str(exc)},
            steps=steps,
            files=files,
        )

    final_status = "PARTIAL" if warnings else "OK"
    update_status = _build_update_status(
        status=final_status,
        steps=steps,
        warnings=warnings,
    )
    final_status = str(update_status.get("status", final_status))
    files["update_status"] = _write_update_status(context_output, update_status)

    return {
        "command": "update",
        "list": list_text,
        "status": final_status,
        "impact": update_status["impact"],
        "context_valid": update_status["context_valid"],
        "regime_reliability": update_status["regime_reliability"],
        "failed_step": update_status.get("failed_step", ""),
        "reason": "data freshness failed" if final_status == "FAIL" else "",
        "start": start,
        "end": resolved_end,
        "use_cache": use_cache,
        "warnings": warnings,
        "update_status": update_status,
        "steps": steps,
        "files": files,
    }


def render_update_summary(payload: dict[str, Any]) -> str:
    list_name = payload.get("list", "-")
    status = payload.get("status", "-")
    lines = [f"UPDATE | LIST {list_name} | STATUS {status}"]
    impact_lines = [
        "",
        "OPERATIONAL IMPACT:",
        f"- impact: {payload.get('impact', '-')}",
        f"- context_valid: {payload.get('context_valid', '-')}",
        f"- regime_reliability: {payload.get('regime_reliability', '-')}",
    ]
    freshness = payload.get("update_status", {}).get("freshness", {})
    context_step = _find_step(payload.get("steps", []), "context") or {}
    context_payload = context_step.get("payload", {})
    if not isinstance(context_payload, dict):
        context_payload = {}

    def append_freshness() -> None:
        if isinstance(freshness, dict) and freshness:
            lines.extend(
                [
                    "",
                    "DATA FRESHNESS",
                    "--------------------------------------------------------------------------------",
                    f"prices_last_date      {freshness.get('prices_last_date', '-') or '-'}",
                    f"indices_last_date     {freshness.get('indices_last_date', '-') or '-'}",
                    f"max_staleness_days    {freshness.get('max_staleness_days', 0)}",
                    f"stale_assets          {freshness.get('stale_assets', 0)}",
                    f"stale_indices         {freshness.get('stale_indices', 0)}",
                    f"freshness_status      {freshness.get('freshness_status', '-')}",
                    f"data_quality_score    {freshness.get('data_quality_score', '-')}",
                ]
            )

    if status == "FAIL":
        lines.extend(
            [
                f"STEP: {payload.get('failed_step', '-')}",
                f"REASON: {payload.get('reason', '-')}",
            ]
        )
        lines.extend(impact_lines)
        append_freshness()
        return "\n".join(lines)

    lines.extend(["", "DATA:"])
    for step in payload.get("steps", []):
        name = str(step.get("step", "-"))
        step_payload = step.get("payload", {})
        if name.endswith("_check"):
            lines.append(f"- {name}: {step.get('status', '-')}")
        elif name in {"prices", "indices"}:
            lines.append(
                f"- {name}: {step.get('status', '-')} "
                f"(updated: {step_payload.get('updated', 0)}, "
                f"cache: {step_payload.get('cache_hits', 0)}, "
                f"fallback: {step_payload.get('cache_fallbacks', 0)})"
            )
        elif name == "universe":
            lines.append(
                f"- {name}: {step.get('status', '-')} "
                f"(assets: {step_payload.get('asset_count', '-')})"
            )
        elif name == "features":
            lines.append(
                f"- {name}: {step.get('status', '-')} "
                f"(assets: {step_payload.get('matrix_assets', step_payload.get('assets', '-'))})"
            )
        elif name == "context":
            lines.append(f"- {name}: {step.get('status', '-')}")

    lines.extend(impact_lines)

    append_freshness()

    regime_summary = context_payload.get("regime_summary", {})
    context_sources = context_payload.get("context_sources", {})
    if isinstance(regime_summary, dict) and regime_summary:
        source_aliases = {
            "auto": "AUTO",
            "thresholds": "THR",
            "manual": "MANUAL",
            "bcb": "BCB",
            "b3": "B3",
            "cvm": "CVM",
            "market_data": "MARKET",
        }
        sources_text = " ".join(
            f"{label}={context_sources.get(key, '-')}"
            for key, label in source_aliases.items()
        )
        lines.extend(
            [
                "",
                "MARKET CONTEXT",
                "--------------------------------------------------------------------------------",
                f"schema             {context_payload.get('schema_version', '-')}",
                f"status             {context_sources.get('auto', '-')}",
                f"quality            {regime_summary.get('context_quality', '-')}",
                f"regime             {regime_summary.get('market_regime', '-')}",
                f"trend              {regime_summary.get('market_trend', '-')}",
                f"volatility         {regime_summary.get('market_volatility', '-')}",
                f"context_score      {regime_summary.get('context_score', '-')}",
                "main_drivers       "
                + ", ".join(regime_summary.get("main_drivers", []) or []),
                "main_risks         "
                + ", ".join(regime_summary.get("main_risks", []) or []),
                f"freshness          {context_payload.get('freshness', {}).get('freshness_status', '-')}",
                f"sources            {sources_text}",
            ]
        )

    files = payload.get("files", {})
    if payload.get("warnings"):
        lines.extend(["", "WARNINGS:"])
        for warning in payload.get("warnings", []):
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "FILES:",
            f"- prices_dir: {files.get('prices_dir', '-')}",
            f"- indices_dir: {files.get('indices_dir', '-')}",
            f"- context: {files.get('context', '-')}",
            f"- universe: {files.get('universe', '-')}",
            f"- matrix: {files.get('matrix', '-')}",
        ]
    )
    return "\n".join(lines)


def run_update_command(args: Any) -> int:
    payload = run_update_flow(
        list_name=args.list,
        start=args.start,
        end=args.end or None,
        tickers_file=args.tickers_file or None,
        prices_dir=args.prices_dir,
        indices_catalog=args.indices_catalog,
        indices_dir=args.indices_dir,
        context_output=args.context_output,
        universe_output=args.universe_output,
        features_catalog=args.features_catalog,
        matrix_output=args.matrix_output,
        context_config=getattr(args, "context_config", "config/market_context.json"),
        context_thresholds=getattr(
            args,
            "context_thresholds",
            "config/market_context_thresholds.json",
        ),
        use_cache=not getattr(args, "no_cache", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_update_summary(payload))

    return 0 if payload["status"] in {"OK", "PARTIAL"} else 1
