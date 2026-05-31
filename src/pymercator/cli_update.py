from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from pymercator.data.prices_csv import check_prices_dir
from pymercator.data.prices_yahoo import fetch_yahoo_prices_from_ticker_file
from pymercator.data.universe_builder import build_universe_csv_from_prices
from pymercator.data.universe_csv import validate_universe_csv
from pymercator.features_catalog import validate_features_catalog
from pymercator.features_matrix import write_feature_matrix
from pymercator.indices_prices import check_indices_prices_dir, fetch_indices_prices
from pymercator.market_context import validate_market_context
from pymercator.market_context_auto import write_auto_market_context

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


def _fail_payload(
    *,
    list_name: str,
    step: str,
    reason: str,
    detail: Any,
    steps: list[dict[str, Any]],
    files: dict[str, str],
) -> dict[str, Any]:
    return {
        "command": "update",
        "list": list_name,
        "status": "FAIL",
        "failed_step": step,
        "reason": reason,
        "detail": detail,
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
        context = write_auto_market_context(
            indices_dir=indices_dir,
            output=context_output,
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

    return {
        "command": "update",
        "list": list_text,
        "status": "PARTIAL" if warnings else "OK",
        "start": start,
        "end": resolved_end,
        "use_cache": use_cache,
        "warnings": warnings,
        "steps": steps,
        "files": files,
    }


def render_update_summary(payload: dict[str, Any]) -> str:
    list_name = payload.get("list", "-")
    status = payload.get("status", "-")
    lines = [f"UPDATE | LIST {list_name} | STATUS {status}"]

    if status == "FAIL":
        lines.extend(
            [
                f"STEP: {payload.get('failed_step', '-')}",
                f"REASON: {payload.get('reason', '-')}",
            ]
        )
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
        use_cache=not getattr(args, "no_cache", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_update_summary(payload))

    return 0 if payload["status"] in {"OK", "PARTIAL"} else 1
