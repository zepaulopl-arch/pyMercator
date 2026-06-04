from __future__ import annotations

from typing import Any

from pymercator.terminal_render import muted_line, truncate

DEFAULT_BUY_TRADE_MODE = "SWING"
DEFAULT_EXIT_TRADE_MODE = "POSITION"
DEFAULT_SHORT_TRADE_MODE = "SWING"


def _defensive_permission_label(row: dict[str, Any]) -> str:
    permission = str(row.get("short_permission", row.get("permission", "-")) or "-")
    if permission == "SHORT_BLOCKED":
        return "MANUAL_BLOCK"
    if permission == "SHORT_MANUAL_ONLY":
        return "MANUAL_ONLY"
    if permission == "SHORT_READY":
        return "MANUAL_READY"
    return permission


def _defensive_short_action(row: dict[str, Any]) -> str:
    permission = str(row.get("short_permission", row.get("permission", "-")) or "-")
    borrow_status = str(row.get("borrow_status", "") or "")
    if permission == "SHORT_BLOCKED" and borrow_status in {
        "BORROW_DATA_MISSING",
        "BORROW_STALE",
    }:
        return "check borrow"
    if permission == "SHORT_BLOCKED":
        return "blocked"
    if permission == "SHORT_MANUAL_ONLY":
        return "manual review"
    if permission == "SHORT_READY":
        return "manual confirm"
    return "watch"


def _render_defensive_book(position_actions: dict[str, Any]) -> list[str]:
    defensive_book = position_actions.get("defensive_book", {})
    if not isinstance(defensive_book, dict):
        return []
    if str(defensive_book.get("defensive_mode", "inactive")).lower() != "active":
        return []

    lines = [
        "DEFENSIVE BOOK",
        muted_line(),
        f"market_read        {defensive_book.get('market_read', '-')}",
        f"long_action        {defensive_book.get('long_action', '-')}",
        f"defensive_mode     {defensive_book.get('defensive_mode', '-')}",
        "",
        "SELL-SHORT CANDIDATES",
        muted_line(),
        (
            f"{'#':>2} {'TICKER':<8} {'SCORE':>7} {'SETUP':<16} "
            f"{'RISK':<10} {'BORROW':<20} {'PERMISSION':<14} ACTION"
        ),
    ]
    short_candidates = defensive_book.get("short_candidates", [])
    if not isinstance(short_candidates, list) or not short_candidates:
        lines.append("no sell-short setup candidates.")
    else:
        for index, row in enumerate(short_candidates, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{float(row.get('short_score', row.get('score', 0.0))):>7.1f} "
                f"{str(row.get('short_setup_status', '-')):<16} "
                f"{str(row.get('short_risk_status', '-')):<10} "
                f"{str(row.get('borrow_status', '-')):<20} "
                f"{_defensive_permission_label(row):<14} "
                f"{_defensive_short_action(row)}"
            )

    lines.extend(
        [
            "",
            "HEDGE CANDIDATES",
            muted_line(),
            f"{'#':>2} {'TARGET':<10} {'ACTION':<12} REASON",
        ]
    )
    hedge_candidates = defensive_book.get("hedge_candidates", [])
    if not isinstance(hedge_candidates, list) or not hedge_candidates:
        lines.append("no hedge watch candidates.")
    else:
        for index, row in enumerate(hedge_candidates, start=1):
            lines.append(
                f"{index:>2} {str(row.get('target', '-')):<10} "
                f"{str(row.get('action', '-')):<12} "
                f"{truncate(str(row.get('reason', '-')), 60)}"
            )

    cash_mode = defensive_book.get("cash_wait_mode", {})
    if not isinstance(cash_mode, dict):
        cash_mode = {}
    lines.extend(
        [
            "",
            "CASH / WAIT MODE",
            muted_line(),
            f"action             {cash_mode.get('action', '-')}",
            f"reason             {cash_mode.get('reason', '-')}",
        ]
    )
    return lines


def render_position_books(position_actions: dict[str, Any]) -> list[str]:
    if not position_actions:
        return []

    lines = [
        "BUY / LONG BOOK",
        muted_line(),
        "direction         LONG",
        "meaning           bought/long position; benefits from price rising",
        f"mode              {DEFAULT_BUY_TRADE_MODE}",
        "",
        (
            f"{'#':>2} {'TICKER':<8} {'DIR':<5} {'MODE':<10} "
            f"{'ACTION':<10} {'SCORE':>7} REASON"
        ),
    ]
    long_rows = position_actions.get("long_book", [])
    if not isinstance(long_rows, list) or not long_rows:
        lines.append("no long book rows.")
    else:
        for index, row in enumerate(long_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{str(row.get('direction', 'LONG')):<5} "
                f"{str(row.get('trade_mode', DEFAULT_BUY_TRADE_MODE)):<10} "
                f"{row['action']:<10} "
                f"{float(row['score']):>7.2f} {truncate(row['reason'], 48)}"
            )

    exit_book = position_actions.get("exit_book", {})
    exit_rows = exit_book.get("rows", []) if isinstance(exit_book, dict) else []
    lines.extend(["", "EXIT BOOK", muted_line()])
    if not exit_rows:
        message = "no open positions loaded"
        if isinstance(exit_book, dict):
            message = str(exit_book.get("message") or message).rstrip(".")
        lines.extend(["status             EMPTY", f"reason             {message}"])
    else:
        lines.append(
            f"{'#':>2} {'TICKER':<8} {'DIR':<5} {'MODE':<10} {'ACTION':<12} {'PNL%':>7} "
            f"{'RISK':<7} {'REVIEW':<6} REASON"
        )
        for index, row in enumerate(exit_rows, start=1):
            pnl_value = row.get("pnl_pct")
            pnl = "n/a" if pnl_value is None else f"{float(pnl_value):+7.1f}"
            review = "YES" if row.get("manual_review_required") else "NO"
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{str(row.get('direction', 'LONG')):<5} "
                f"{str(row.get('trade_mode', DEFAULT_EXIT_TRADE_MODE)):<10} "
                f"{row['action']:<12} "
                f"{pnl:>7} {row['risk']:<7} {review:<6} {truncate(row['reason'], 44)}"
            )

    defensive_lines = _render_defensive_book(position_actions)
    if defensive_lines:
        lines.extend(["", *defensive_lines])

    short_rows = position_actions.get("short_book", [])
    short_policy = position_actions.get("short_policy", {})
    if not isinstance(short_policy, dict):
        short_policy = {}
    lines.extend(
        [
            "",
            "SELL-SHORT / HEDGE BOOK",
            muted_line(),
            "direction         SHORT",
            "meaning           sold/borrowed position; benefits from price falling",
            f"mode              {DEFAULT_SHORT_TRADE_MODE}",
            f"policy            {short_policy.get('mode', 'MANUAL_ONLY')}",
            "requires          borrow availability, borrow cost and short risk checks",
            "",
            (
                f"{'#':>2} {'TICKER':<8} {'SCORE':>7} {'SETUP':<16} "
                f"{'RISK':<12} {'BORROW':<20} {'EVENT':<14} "
                f"{'PERMISSION':<17} REASON"
            ),
        ]
    )
    if not isinstance(short_rows, list) or not short_rows:
        lines.append("no short or hedge candidates.")
    else:
        for index, row in enumerate(short_rows, start=1):
            lines.append(
                f"{index:>2} {row['ticker']:<8} "
                f"{float(row.get('short_score', row.get('score', 0.0))):>7.1f} "
                f"{str(row.get('short_setup_status', '-')):<16} "
                f"{str(row.get('short_risk_status', '-')):<12} "
                f"{str(row.get('borrow_status', '-')):<20} "
                f"{str(row.get('event_status', '-')):<14} "
                f"{str(row.get('short_permission', row.get('action', '-'))):<17} "
                f"{truncate(row['reason'], 44)}"
            )
    return lines
