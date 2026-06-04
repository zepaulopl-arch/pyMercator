from __future__ import annotations

from pymercator import basket as basket_mod
from pymercator.terminal_render import render_files, render_key_values


def run_basket_cli(args: object) -> int:
    if getattr(args, "basket_command", "daily") == "show":
        csv_path, json_path, txt_path = basket_mod.resolve_basket_paths(args.output)
        payload = basket_mod.load_basket_json(json_path)

        if payload.get("status") in {"MISSING", "INVALID"}:
            warnings = payload.get("warnings", [])
            if isinstance(warnings, list):
                for warning in warnings:
                    print(warning)
            else:
                print(warnings)
            return 1

        print(
            basket_mod.render_basket_summary(
                payload,
                color=None,
                details=getattr(args, "details", False),
            )
        )
        print("")
        print(
            render_files(
                [
                    ("basket_csv", csv_path),
                    ("basket_json", json_path),
                    ("basket_txt", txt_path),
                ],
                label_width=16,
            )
        )
        return 0

    daily_report = getattr(args, "daily_report", "")
    ordered_candidates = (
        basket_mod.ready_candidates_from_daily_report(daily_report)
        if daily_report
        else None
    )
    eligible_tickers = [item["ticker"] for item in ordered_candidates] if ordered_candidates else None

    payload = basket_mod.run_daily_basket(
        slots=args.slots,
        min_sectors=args.min_sectors,
        min_weight=args.min_weight,
        capital=args.capital,
        risk_per_trade=args.risk_per_trade,
        targets=args.targets,
        stop_mode=args.stop,
        prices_dir=args.prices_dir,
        universe=args.universe,
        matrix=args.matrix,
        evaluation=args.evaluation,
        output_csv=args.output,
        eligible_tickers=eligible_tickers,
        ordered_candidates=ordered_candidates,
    )

    csv_path, json_path, txt_path = basket_mod.resolve_basket_paths(args.output)
    output = [basket_mod.render_basket_summary(payload, color=None, details=False), ""]
    output.append(
        render_key_values(
            "FILES",
            [
                ("basket_csv", csv_path),
                ("basket_json", json_path),
                ("basket_txt", txt_path),
                ("status", payload["status"], payload["status"]),
            ],
            label_width=16,
        )
    )

    if payload.get("warnings"):
        output.append("")
        output.append("WARNINGS")
        output.append("\n".join(payload["warnings"]))

    print("\n".join(output))
    return 0
