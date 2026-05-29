from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pymercator.domain import AssetDecision, DailyReport, ExecutionStatus
from pymercator.explain import decision_codes, decision_label
from pymercator.pipeline import run_daily_pipeline
from pymercator.reports.json_report import write_daily_report_json
from pymercator.reports.terminal import render_daily_report

STATUS_SCORE = {
    "READY": 3,
    "WATCH": 2,
    "MANUAL_ONLY": 1,
    "BLOCKED": 0,
    "INVALID": 0,
}


def make_timestamped_run_dir(base_dir: str | Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_path = Path(base_dir)

    candidate = base_path / stamp
    suffix = 1

    while candidate.exists():
        candidate = base_path / f"{stamp}_{suffix:02d}"
        suffix += 1

    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def write_json(path: str | Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def scenario_definitions(tags: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "key": "01_off_con",
            "title": "OFF / CON",
            "profile": "CON",
            "headline_risk": "OFF",
            "headline_tags": [],
        },
        {
            "key": "02_watch_bal",
            "title": "WATCH / BAL",
            "profile": "BAL",
            "headline_risk": "WATCH",
            "headline_tags": tags,
        },
        {
            "key": "03_active_agr",
            "title": "ACTIVE / AGR",
            "profile": "AGR",
            "headline_risk": "ACTIVE",
            "headline_tags": tags,
        },
        {
            "key": "04_extreme_agr",
            "title": "EXTREME / AGR",
            "profile": "AGR",
            "headline_risk": "EXTREME",
            "headline_tags": tags,
        },
    ]


def run_scenario_report(
    *,
    universe_path: str,
    universe_name: str,
    market_trend: str,
    market_volatility: str,
    policy_path: str,
    scenario: dict[str, Any],
) -> DailyReport:
    return run_daily_pipeline(
        universe_path=universe_path,
        universe_name=universe_name,
        profile=str(scenario["profile"]),
        headline_risk=str(scenario["headline_risk"]),
        headline_tags=list(scenario["headline_tags"]),
        market_trend=market_trend,
        market_volatility=market_volatility,
        policy_path=policy_path,
    )


def count_status(report: DailyReport, status: ExecutionStatus) -> int:
    return sum(1 for item in report.decisions if item.permission.status == status)


def top_decision(report: DailyReport) -> AssetDecision | None:
    if not report.decisions:
        return None
    return report.decisions[0]


def scenario_summary_row(
    *,
    scenario: dict[str, Any],
    report: DailyReport,
) -> dict[str, Any]:
    top = top_decision(report)

    if top is None:
        top_payload: dict[str, Any] = {}
    else:
        top_payload = {
            "ticker": top.asset.ticker,
            "sector": top.asset.sector,
            "raw_score": top.ranking.raw_score,
            "context_factor": top.ranking.context_factor,
            "context_score": top.ranking.context_score,
            "raw_signal": top.ranking.raw_signal,
            "context_signal": top.ranking.context_signal,
            "permission": top.permission.status.value,
            "decision_label": decision_label(top),
        }

    return {
        "key": scenario["key"],
        "title": scenario["title"],
        "profile": report.profile,
        "headline_risk": report.market_regime.headline_risk.value,
        "headline_tags": list(report.market_regime.headline_tags),
        "posture": report.posture,
        "ready": count_status(report, ExecutionStatus.READY),
        "watch": count_status(report, ExecutionStatus.WATCH),
        "blocked": count_status(report, ExecutionStatus.BLOCKED),
        "top": top_payload,
    }


def render_pack_summary(rows: list[dict[str, Any]], pack_dir: Path) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR SCENARIO PACK SUMMARY")
    lines.append(line)
    lines.append(f"{'PACK DIR':<16} {pack_dir}")
    lines.append("")
    lines.append(
        f"{'SCENARIO':<16} "
        f"{'POSTURE':<12} "
        f"{'READY':>5} "
        f"{'WATCH':>5} "
        f"{'BLOCK':>5} "
        f"{'TOP':<6} "
        f"{'TOP_EXEC':<8} "
        f"{'TOP_LABEL':<28}"
    )
    lines.append(line)

    for row in rows:
        top = row["top"]
        lines.append(
            f"{row['key']:<16} "
            f"{row['posture']:<12} "
            f"{row['ready']:>5} "
            f"{row['watch']:>5} "
            f"{row['blocked']:>5} "
            f"{top.get('ticker', '-'):<6} "
            f"{top.get('permission', '-'):<8} "
            f"{top.get('decision_label', '-'):<28}"
        )

    lines.append("")
    lines.append("FILES")
    lines.append(line)

    for row in rows:
        lines.append(f"{row['key']}/report.txt")
        lines.append(f"{row['key']}/report.json")

    return "\n".join(lines)


def collect_stability_rows(
    scenario_reports: list[tuple[dict[str, Any], DailyReport]],
) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}

    for scenario, report in scenario_reports:
        for decision in report.decisions:
            ticker = decision.asset.ticker
            status = decision.permission.status.value
            codes = decision_codes(decision)

            row = by_ticker.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "sector": decision.asset.sector,
                    "scenarios": [],
                    "ready": 0,
                    "watch": 0,
                    "blocked": 0,
                    "invalid": 0,
                    "manual_only": 0,
                    "scores": [],
                    "factors": [],
                    "labels": set(),
                    "codes": set(),
                    "status_scores": [],
                },
            )

            row["scenarios"].append(
                {
                    "key": scenario["key"],
                    "headline_risk": report.market_regime.headline_risk.value,
                    "posture": report.posture,
                    "status": status,
                    "context_score": decision.ranking.context_score,
                    "context_factor": decision.ranking.context_factor,
                    "decision_label": decision_label(decision),
                    "decision_codes": list(codes),
                }
            )

            if status == "READY":
                row["ready"] += 1
            elif status == "WATCH":
                row["watch"] += 1
            elif status == "BLOCKED":
                row["blocked"] += 1
            elif status == "MANUAL_ONLY":
                row["manual_only"] += 1
            else:
                row["invalid"] += 1

            row["scores"].append(decision.ranking.context_score)
            row["factors"].append(decision.ranking.context_factor)
            row["labels"].add(decision_label(decision))
            row["codes"].update(codes)
            row["status_scores"].append(STATUS_SCORE.get(status, 0))

    stability_rows: list[dict[str, Any]] = []

    for row in by_ticker.values():
        scenario_count = len(row["scenarios"])
        avg_final = sum(row["scores"]) / scenario_count if scenario_count else 0.0
        avg_factor = sum(row["factors"]) / scenario_count if scenario_count else 0.0
        survival_score = sum(row["status_scores"])
        survived = row["ready"] + row["watch"] + row["manual_only"]

        stability_rows.append(
            {
                "ticker": row["ticker"],
                "sector": row["sector"],
                "scenario_count": scenario_count,
                "survived": survived,
                "ready": row["ready"],
                "watch": row["watch"],
                "blocked": row["blocked"],
                "manual_only": row["manual_only"],
                "invalid": row["invalid"],
                "avg_final": round(avg_final, 2),
                "avg_factor": round(avg_factor, 4),
                "survival_score": survival_score,
                "labels": sorted(row["labels"]),
                "codes": sorted(row["codes"]),
                "scenarios": row["scenarios"],
            }
        )

    stability_rows.sort(
        key=lambda item: (
            item["survival_score"],
            item["survived"],
            item["avg_final"],
        ),
        reverse=True,
    )

    return stability_rows


def render_stability_ranking(rows: list[dict[str, Any]]) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR STABILITY RANKING")
    lines.append(line)
    lines.append(
        f"{'RK':>2} "
        f"{'TICKER':<6} "
        f"{'SECTOR':<10} "
        f"{'SURV':>4} "
        f"{'READY':>5} "
        f"{'WATCH':>5} "
        f"{'BLOCK':>5} "
        f"{'AVG':>6} "
        f"{'FACTOR':>6} "
        f"{'SCORE':>5} "
        f"{'CODES':<34}"
    )
    lines.append(line)

    for index, row in enumerate(rows, start=1):
        codes = ",".join(row["codes"]) if row["codes"] else "-"
        if len(codes) > 34:
            codes = codes[:31] + "..."

        lines.append(
            f"{index:>2} "
            f"{row['ticker']:<6} "
            f"{row['sector']:<10} "
            f"{row['survived']:>4} "
            f"{row['ready']:>5} "
            f"{row['watch']:>5} "
            f"{row['blocked']:>5} "
            f"{row['avg_final']:>6.2f} "
            f"{row['avg_factor']:>6.2f} "
            f"{row['survival_score']:>5} "
            f"{codes:<34}"
        )

    return "\n".join(lines)


def build_manifest(
    *,
    created_at: str,
    pack_dir: Path,
    universe_path: str,
    universe_name: str,
    headline_tags: list[str],
    market_trend: str,
    market_volatility: str,
    policy_path: str,
    limit: int,
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    files = [
        "00_manifest.txt",
        "00_manifest.json",
        "00_pack_summary.txt",
        "00_pack_summary.json",
        "00_stability_ranking.txt",
        "00_stability_ranking.json",
    ]

    for scenario in scenarios:
        files.append(f"{scenario['key']}/report.txt")
        files.append(f"{scenario['key']}/report.json")

    return {
        "created_at": created_at,
        "command": "scenario-pack",
        "pack_dir": str(pack_dir),
        "universe": universe_path,
        "universe_name": universe_name,
        "headline_tags": headline_tags,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "policy": policy_path,
        "limit": limit,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "files": files,
    }


def render_manifest(manifest: dict[str, Any]) -> str:
    line = "-" * 118
    lines: list[str] = []

    lines.append("PYMERCATOR SCENARIO PACK MANIFEST")
    lines.append(line)
    lines.append(f"{'CREATED AT':<18} {manifest['created_at']}")
    lines.append(f"{'PACK DIR':<18} {manifest['pack_dir']}")
    lines.append(f"{'UNIVERSE':<18} {manifest['universe_name']}")
    lines.append(f"{'UNIVERSE FILE':<18} {manifest['universe']}")
    lines.append(f"{'POLICY':<18} {manifest['policy']}")
    lines.append(f"{'MARKET TREND':<18} {manifest['market_trend']}")
    lines.append(f"{'VOLATILITY':<18} {manifest['market_volatility']}")
    lines.append(f"{'HEADLINE TAGS':<18} {', '.join(manifest['headline_tags']) or '-'}")
    lines.append(f"{'SCENARIOS':<18} {manifest['scenario_count']}")
    lines.append("")

    lines.append("SCENARIOS")
    lines.append(line)

    for scenario in manifest["scenarios"]:
        tags = ", ".join(scenario["headline_tags"]) or "-"
        lines.append(
            f"{scenario['key']:<16} "
            f"{scenario['title']:<14} "
            f"profile={scenario['profile']:<3} "
            f"risk={scenario['headline_risk']:<7} "
            f"tags={tags}"
        )

    lines.append("")
    lines.append("FILES")
    lines.append(line)

    for file_path in manifest["files"]:
        lines.append(str(file_path))

    return "\n".join(lines)


def run_scenario_pack(
    *,
    universe_path: str,
    universe_name: str,
    headline_tags: list[str],
    market_trend: str,
    market_volatility: str,
    policy_path: str,
    run_dir: str,
    limit: int,
) -> tuple[Path, str, str]:
    created_at = datetime.now().isoformat(timespec="seconds")
    pack_dir = make_timestamped_run_dir(run_dir)
    scenarios = scenario_definitions(headline_tags)

    manifest = build_manifest(
        created_at=created_at,
        pack_dir=pack_dir,
        universe_path=universe_path,
        universe_name=universe_name,
        headline_tags=headline_tags,
        market_trend=market_trend,
        market_volatility=market_volatility,
        policy_path=policy_path,
        limit=limit,
        scenarios=scenarios,
    )

    write_text(pack_dir / "00_manifest.txt", render_manifest(manifest))
    write_json(pack_dir / "00_manifest.json", manifest)

    summary_rows: list[dict[str, Any]] = []
    scenario_reports: list[tuple[dict[str, Any], DailyReport]] = []

    for scenario in scenarios:
        report = run_scenario_report(
            universe_path=universe_path,
            universe_name=universe_name,
            market_trend=market_trend,
            market_volatility=market_volatility,
            policy_path=policy_path,
            scenario=scenario,
        )

        scenario_reports.append((scenario, report))

        scenario_dir = pack_dir / str(scenario["key"])
        scenario_dir.mkdir(parents=True, exist_ok=True)

        rendered = render_daily_report(report, limit=limit)
        write_text(scenario_dir / "report.txt", rendered)
        write_daily_report_json(report, scenario_dir / "report.json")

        summary_rows.append(scenario_summary_row(scenario=scenario, report=report))

    stability_rows = collect_stability_rows(scenario_reports)
    stability_text = render_stability_ranking(stability_rows)

    summary_text = render_pack_summary(summary_rows, pack_dir)
    summary_json = {
        "pack_dir": str(pack_dir),
        "universe_name": universe_name,
        "universe": universe_path,
        "market_trend": market_trend,
        "market_volatility": market_volatility,
        "scenarios": summary_rows,
        "stability_ranking": stability_rows,
    }

    write_text(pack_dir / "00_pack_summary.txt", summary_text)
    write_json(pack_dir / "00_pack_summary.json", summary_json)
    write_text(pack_dir / "00_stability_ranking.txt", stability_text)
    write_json(pack_dir / "00_stability_ranking.json", stability_rows)

    return pack_dir, summary_text, stability_text
