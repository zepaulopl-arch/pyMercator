from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DailyRunRecord:
    id: int
    run_date: str
    created_at: str
    profile: str
    list_name: str
    status: str
    reason: str
    market: str
    trend: str
    model_quality: str
    behavior: str
    long_basket_status: str
    actionable: int
    watch: int
    blocked: int
    report_json: str
    report_txt: str
    basket_csv: str
    run_dir: str


@dataclass(frozen=True)
class SignalRecord:
    id: int
    daily_run_id: int
    created_at: str
    ticker: str
    bias: str
    action: str
    status: str
    score: float | None
    signal_class: str
    executable: bool
    borrow_status: str
    permission: str
    source: str


@dataclass(frozen=True)
class RankingRecord:
    id: int
    daily_run_id: int
    rank_position: int
    ticker: str
    score: float | None
    status: str
    reason: str


@dataclass(frozen=True)
class SimulationRecord:
    id: int
    created_at: str
    name: str
    status: str
    summary_path: str
    trades_csv: str
