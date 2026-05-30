from __future__ import annotations

from pymercator import basket as basket_mod
from pymercator.terminal_ui import line, section


def run_basket_cli(args: object) -> int:
    if getattr(args, "basket_command", "daily") == "show":
        json_path = basket_mod.resolve_basket_paths(args.output)[1]
        payload = basket_mod.load_basket_json(json_path)

        print(section("BASKET SHOW"))
        if payload.get("status") in {"MISSING", "INVALID"}:
            warnings = payload.get("warnings", [])
            if isinstance(warnings, list):
                for warning in warnings:
                    print(warning)
            else:
                print(warnings)
            return 1

        print(basket_mod.render_basket_summary(payload))
        print("\n" + line(100))
        print(f"CSV: {basket_mod.resolve_basket_paths(args.output)[0]}")
        print(f"JSON: {json_path}")
        print(f"TEXT: {basket_mod.resolve_basket_paths(args.output)[2]}")
        return 0

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
    )

    output = [section("DAILY BASKET SUMMARY"), basket_mod.render_basket_summary(payload), ""]
    output.append(f"CSV: {args.output}")
    output.append(f"JSON: {basket_mod.resolve_basket_paths(args.output)[1]}")
    output.append(f"TEXT: {basket_mod.resolve_basket_paths(args.output)[2]}")
    output.append(line(100))
    output.append(f"STATUS: {payload['status']}")

    if payload.get("warnings"):
        output.append(section("WARNINGS"))
        output.append("\n".join(payload["warnings"]))

    print("\n".join(output))
    return 0
