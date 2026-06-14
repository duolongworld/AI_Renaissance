from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .data_adapters import load_ohlcv_csv, load_rows_from_code as load_market_rows_from_code
from .types import OhlcvRow, Signal
from .models.oscillator import analyze as analyze_oscillator
from .models.trend_application import analyze as analyze_trend_app
from .models.trend_tracking import analyze as analyze_trend
from .models.volume_price import analyze as analyze_volume_price


@dataclass(frozen=True)
class RunContext:
    stock_code: str = ""
    target: str = ""
    source_name: str = ""


def run_models(rows: List[OhlcvRow], ctx: RunContext) -> Dict[str, Signal]:
    """
    Run the four analyzers and return a dict keyed by skill name.
    """
    return {
        "volume_price_momentum_analysis": analyze_volume_price(rows, stock_code=ctx.stock_code, target=ctx.target, source_name=ctx.source_name),
        "advanced_trend_tracking_system": analyze_trend(rows, stock_code=ctx.stock_code, target=ctx.target, source_name=ctx.source_name),
        "oscillator_check": analyze_oscillator(rows, stock_code=ctx.stock_code, target=ctx.target, source_name=ctx.source_name),
        "trend_application_dulling_divergence": analyze_trend_app(rows, stock_code=ctx.stock_code, target=ctx.target, source_name=ctx.source_name),
    }


def load_rows_from_csv(csv_path: str) -> Tuple[List[OhlcvRow], List[str]]:
    rows = load_ohlcv_csv(csv_path)
    uncertainties: List[str] = []
    if not rows:
        uncertainties.append("CSV 解析后 rows 为空。")
    return rows, uncertainties


def load_rows_from_code(code: str, start: str, end: str, *, freq: str = "D", adjust: str = "none") -> Tuple[List[OhlcvRow], List[str]]:
    """代理到 data_sources.market_ohlcv，保持技术模型与数据接口解耦。"""
    return load_market_rows_from_code(code, start, end, freq=freq, adjust=adjust)
