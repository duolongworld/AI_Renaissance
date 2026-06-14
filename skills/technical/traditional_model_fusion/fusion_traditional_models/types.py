from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, TypedDict

Direction = Literal["bullish", "bearish", "neutral"]
RiskLevel = Literal["low", "medium", "high"]


class EvidenceItem(TypedDict, total=False):
    source_type: str
    source_name: str
    date: str
    metric: str
    value: str
    comparison: str
    note: str


class SignalMeta(TypedDict, total=False):
    output_version: str
    skill_name: str
    owner_group: str
    target: str
    period: str
    time_horizon: str
    risk_level: RiskLevel
    key_findings: List[str]
    evidence: List[EvidenceItem]
    risk_notes: List[str]
    uncertainties: List[str]
    needs_human_review: bool
    sub_signals: Dict[str, Any]


class Signal(TypedDict, total=False):
    direction: Direction
    confidence: float
    reasoning: str
    signals: List[str]
    source: str
    signal_type: str
    stock_code: str
    weight: float
    meta: SignalMeta


class OhlcvRow(TypedDict, total=False):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class ModelRun:
    name: str
    signal: Signal
    base_weight: float
    effective_weight: float
    vote: float
    notes: List[str]

