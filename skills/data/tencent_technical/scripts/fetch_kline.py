#!/usr/bin/env python3
from __future__ import annotations

"""腾讯财经 K 线 Data Skill 薄包装。

真实数据获取、解析和指标计算已迁移到 `data_sources.tencent_technical`。
本脚本仅保留原 Skill 调用路径和 CLI 兼容性。
"""

from data_sources.tencent_technical import (  # noqa: F401
    DEFAULT_INDICATORS,
    DEFAULT_K_TYPE,
    DEFAULT_NUM,
    TencentTechnicalDataSource,
    calc_boll,
    calc_ma,
    calc_rsi,
    fetch_kline,
    fetch_kline_with_indicators,
    main,
    normalize_code,
)


if __name__ == "__main__":
    main()
