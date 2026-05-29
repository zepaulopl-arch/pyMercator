from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Permission(str, Enum):
    ALLOW = "ALLOW"
    CAUTION = "CAUTION"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class ExecutionStatus(str, Enum):
    READY = "READY"
    WATCH = "WATCH"
    BLOCKED = "BLOCKED"
    MANUAL_ONLY = "MANUAL_ONLY"
    INVALID = "INVALID"


class HeadlineRisk(str, Enum):
    OFF = "OFF"
    WATCH = "WATCH"
    ACTIVE = "ACTIVE"
    EXTREME = "EXTREME"


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    CHOPPY = "CHOPPY"
    EVENT_RISK = "EVENT_RISK"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"


class UniverseHealth(str, Enum):
    BROAD = "BROAD"
    NORMAL = "NORMAL"
    NARROW = "NARROW"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AssetSnapshot:
    ticker: str
    sector: str
    last_close: float
    avg_volume_brl: float
    trend_score: float
    momentum_score: float
    volatility_pct: float
    atr_pct: float
    liquidity_score: float
    quality_score: float
    news_score: float
    entry: float | None
    stop: float | None
    target: float | None


@dataclass(frozen=True)
class MarketRegimeResult:
    regime: MarketRegime
    permission: Permission
    headline_risk: HeadlineRisk
    headline_tags: tuple[str, ...]
    score_factor: float
    exposure_factor: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class UniverseHealthResult:
    universe_name: str
    total_assets: int
    valid_assets: int
    healthy_assets: int
    health: UniverseHealth
    breadth_label: str
    sector_concentration: str
    permission: Permission
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RankingRow:
    ticker: str
    sector: str
    raw_score: float
    context_score: float
    context_factor: float
    rank: int
    raw_signal: str
    context_signal: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TradeValidationResult:
    ticker: str
    valid: bool
    entry: float | None
    stop: float | None
    target: float | None
    rr: float | None
    liquidity_ok: bool
    volatility_ok: bool
    atr_ok: bool
    status: ExecutionStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPermissionResult:
    ticker: str
    status: ExecutionStatus
    max_position_factor: float
    requires_human_confirmation: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AssetDecision:
    asset: AssetSnapshot
    ranking: RankingRow
    validation: TradeValidationResult
    permission: ExecutionPermissionResult


@dataclass(frozen=True)
class DailyReport:
    universe_name: str
    profile: str
    market_regime: MarketRegimeResult
    universe_health: UniverseHealthResult
    decisions: tuple[AssetDecision, ...]
    posture: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
