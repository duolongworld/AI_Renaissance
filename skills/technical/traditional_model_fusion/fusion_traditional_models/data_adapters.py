from __future__ import annotations

"""兼容层：技术模型不再持有行情接口实现。

OHLCV CSV / EastMoney / Tencent 行情加载代码已迁移到
`data_sources.market_ohlcv` 统一管理。本模块仅保留旧导入路径，
避免 CLI、runner 或外部调用方因迁移而中断。
"""

import sys
from pathlib import Path
from typing import Optional


def _find_repo_root(path: Path) -> Optional[Path]:
    for parent in [path, *path.parents]:
        if (parent / "data_sources" / "market_ohlcv.py").exists():
            return parent
    return None


_REPO_ROOT = _find_repo_root(Path(__file__).resolve())
if _REPO_ROOT and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data_sources.market_ohlcv import (  # noqa: E402,F401
    EastMoneyConfig,
    fetch_ohlcv_eastmoney,
    fetch_ohlcv_tencent,
    load_ohlcv_csv,
    load_rows_from_code,
)

__all__ = [
    "EastMoneyConfig",
    "fetch_ohlcv_eastmoney",
    "fetch_ohlcv_tencent",
    "load_ohlcv_csv",
    "load_rows_from_code",
]
