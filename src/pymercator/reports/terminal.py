from __future__ import annotations

from pymercator.domain import DailyReport, ExecutionStatus
from pymercator.explain import decision_label

LINE_WIDTH = 118
TRUNCATION_SUFFIX = "..."


def _line() -> str:
    return "-" * LINE_WIDTH


def _fmt_text(value: object, width: int) -> str:
    text = str(value) if value is not None else "-"

    if len(text) > width:
        if width <= len(TRUNCATION_SUFFIX):
            return TRUNCATION_SUFFIX[:width]
        return text[: width - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX

    return text.ljust(width)


def _fmt_num(value: float | int | None, width: int, decimals: int = 2) -> str:
    if value is None:
        return "N/A".rjust(width)

    if isinstance(value, int):
        return str(value).rjust(width)

    return f"{value:.{decimals}f}".rjust(width)


def _count_by_status(report: DailyReport, status: ExecutionStatus) -> int:
    return sum(1 for item in report.decisions if item.permission.status == status)


def _headline_tags(report: DailyReport) -> str:
    if not report.market_regime.headline_tags:
        return "-"
    return ", ".join(report.market_regime.headline_tags)


def render_daily_report(report: DailyReport, limit: int = 20) -> str:
    ready_count = _count_by_status(report, ExecutionStatus.READY)
    watch_count = _count_by_status(report, ExecutionStatus.WATCH)
    blocked_count = _count_by_status(report, ExecutionStatus.BLOCKED)

    lines: list[str] = []

    lines.append("PYMERCATOR DAILY OPERATIONAL REPORT")
    lines.append(_line())
    lines.append(f"{'UNIVERSE':<20} {report.universe_name}")
    lines.append(f"{'PROFILE':<20} {report.profile}")
    lines.append(f"{'TODAY POSTURE':<20} {report.posture}")
    lines.append("")

    lines.append("1. MARKET REGIME")
    lines.append(_line())
    lines.append(f"{'REGIME':<20} {report.market_regime.regime.value}")
    lines.append(f"{'PERMISSION':<20} {report.market_regime.permission.value}")
    lines.append(f"{'HEADLINE RISK':<20} {report.market_regime.headline_risk.value}")
    lines.append(f"{'HEADLINE TAGS':<20} {_headline_tags(report)}")
    lines.append(f"{'SCORE FACTOR':<20} {report.market_regime.score_factor:.2f}")
    lines.append(f"{'EXPOSURE FACTOR':<20} {report.market_regime.exposure_factor:.2f}")

    for reason in report.market_regime.reasons:
        lines.append(f"- {reason}")

    lines.append("")

    lines.append("2. UNIVERSE HEALTH")
    lines.append(_line())
    lines.append(f"{'TOTAL ASSETS':<20} {report.universe_health.total_assets}")
    lines.append(f"{'VALID ASSETS':<20} {report.universe_health.valid_assets}")
    lines.append(f"{'HEALTHY ASSETS':<20} {report.universe_health.healthy_assets}")
    lines.append(f"{'HEALTH':<20} {report.universe_health.health.value}")
    lines.append(f"{'BREADTH':<20} {report.universe_health.breadth_label}")
    lines.append(f"{'CONCENTRATION':<20} {report.universe_health.sector_concentration}")
    lines.append(f"{'PERMISSION':<20} {report.universe_health.permission.value}")

    for reason in report.universe_health.reasons:
        lines.append(f"- {reason}")

    lines.append("")

    lines.append("3. ASSET RANKING + 4. VALIDATION + 5. PERMISSION")
    lines.append(_line())

    header = (
        f"{'RK':>2} "
        f"{'TICKER':<6} "
        f"{'SECTOR':<10} "
        f"{'RAW':>6} "
        f"{'FACT':>5} "
        f"{'FINAL':>6} "
        f"{'R_SIG':<7} "
        f"{'C_SIG':<7} "
        f"{'RR':>5} "
        f"{'EXEC':<8} "
        f"{'SIZE':>5} "
        f"{'WHY':<24}"
    )

    lines.append(header)
    lines.append(_line())

    for item in report.decisions[:limit]:
        line = (
            f"{item.ranking.rank:>2} "
            f"{_fmt_text(item.asset.ticker, 6)} "
            f"{_fmt_text(item.asset.sector, 10)} "
            f"{_fmt_num(item.ranking.raw_score, 6)} "
            f"{_fmt_num(item.ranking.context_factor, 5)} "
            f"{_fmt_num(item.ranking.context_score, 6)} "
            f"{_fmt_text(item.ranking.raw_signal, 7)} "
            f"{_fmt_text(item.ranking.context_signal, 7)} "
            f"{_fmt_num(item.validation.rr, 5)} "
            f"{_fmt_text(item.permission.status.value, 8)} "
            f"{_fmt_num(item.permission.max_position_factor, 5)} "
            f"{_fmt_text(decision_label(item), 24)}"
        )
        lines.append(line)

    lines.append("")

    lines.append("LEGEND")
    lines.append(_line())
    lines.append("HEADLINE    headline risk reduced score")
    lines.append("SECTOR      sector sensitivity changed context factor")
    lines.append("CAP         permission capped by policy")
    lines.append("CTX_LOW     context score below operational threshold")
    lines.append("REGIME_DENY market regime denied operation")
    lines.append("RR_LOW      risk/reward below minimum")
    lines.append("ATR_HIGH    ATR above maximum")
    lines.append("VOL_HIGH    volatility above maximum")
    lines.append("LIQ_LOW     liquidity below minimum")
    lines.append("NO_ENTRY    missing entry")
    lines.append("NO_STOP     missing stop")
    lines.append("NO_TARGET   missing target")
    lines.append("")

    lines.append("SUMMARY")
    lines.append(_line())
    lines.append(f"{'READY':<20} {ready_count}")
    lines.append(f"{'WATCH':<20} {watch_count}")
    lines.append(f"{'BLOCKED':<20} {blocked_count}")
    lines.append("")

    lines.append("6. HUMAN CONFIRMATION")
    lines.append(_line())

    if ready_count > 0:
        lines.append("READY tickets require explicit human confirmation before any real operation.")

        ready_items = [
            item
            for item in report.decisions
            if item.permission.status == ExecutionStatus.READY
        ]

        for item in ready_items[:5]:
            lines.append(f"- {item.asset.ticker}: confirmation required")
    else:
        lines.append("No READY tickets generated.")

    lines.append("")

    lines.append("POSTURE REASONS")
    lines.append(_line())

    for reason in report.reasons:
        lines.append(f"- {reason}")

    return "\n".join(lines)
