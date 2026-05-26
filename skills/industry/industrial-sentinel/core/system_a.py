#!/usr/bin/env python3
"""
System A - 中观层产业拐点分析引擎
合并模块:数据获取、数据防火墙、五态拐点模型

包含:
- 四层行业数据获取(L1→L4 降级)
- System A 数据防火墙(白名单/黑名单校验)
- 五态拐点定量判定(Pre/Early/Confirmed/Late/Post)
- 产业链生命周期判定(初创/成长/成熟/衰退)

V4.5 变更:
- 删除所有评分数字与评分公式
- 删除产业拐点指数(0-100)合成
- 五态判定改为基于真实信号匹配
- 生命周期判定改为基于数据推断
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Set

# ───────────────────────────────────────────────────────────────
# 日志配置(统一一次)
# ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("system_a")

# ═══════════════════════════════════════════════════════════════
# Part 1 - 行业数据获取 (v44-data-acquisition)
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class IndustryDataPoint:
    """
    行业数据点 -- System A 的唯一合法输入单元 (V4.5 无评分版)

    属性:
        value: 数据值(float/int/str,视metric而定)
        source_level: 数据来源层级 L1/L2/L3/L4
        source_detail: 详细来源说明(用于溯源表)
        data_date: 数据原始日期(YYYY-MM-DD)
        timestamp: 数据采集时间
    """
    value: Union[float, int, str]
    source_level: str  # "L1" / "L2" / "L3" / "L4"
    source_detail: str = ""
    data_date: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source_level": self.source_level,
            "source_detail": self.source_detail,
            "data_date": self.data_date,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════
# 异常类
# ═══════════════════════════════════════════════════════════════

class DataSourceFallback(Exception):
    """
    数据源降级异常。
    当某一层级数据获取失败时抛出,携带失败原因和已尝试层级,
    由 acquire_industry_data() 捕获并自动触发下一层级。
    """
    def __init__(self, message: str, failed_level: str, attempted_source: str, next_level: str):
        self.failed_level = failed_level
        self.attempted_source = attempted_source
        self.next_level = next_level
        super().__init__(message)


class AllLevelsFailed(Exception):
    """L1→L4 全部降级后仍无法获取数据,终极失败异常。"""
    def __init__(self, industry_name: str, metric: str, attempts: List[str]):
        self.industry_name = industry_name
        self.metric = metric
        self.attempts = attempts
        super().__init__(f"[{industry_name}.{metric}] L1→L4 全部失败,已尝试: {attempts}")


# ═══════════════════════════════════════════════════════════════
# 行业预设:龙头股权重配置(L3推断用)
# ═══════════════════════════════════════════════════════════════

INDUSTRY_LEADERS: Dict[str, Dict[str, Any]] = {
    "光模块": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "中际旭创", "code": "300308.SZ", "weight": 0.40},
            {"name": "新易盛", "code": "300502.SZ", "weight": 0.30},
            {"name": "光迅科技", "code": "002281.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "光通信": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "中际旭创", "code": "300308.SZ", "weight": 0.40},
            {"name": "新易盛", "code": "300502.SZ", "weight": 0.30},
            {"name": "光迅科技", "code": "002281.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "ABF载板": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.50},
            {"name": "兴森科技", "code": "002436.SZ", "weight": 0.30},
            {"name": "其他", "code": "OTHER", "weight": 0.20},
        ],
    },
    "PCB": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.35},
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.30},
            {"name": "鹏鼎控股", "code": "002938.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.15},
        ],
    },
    "半导体设备": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "北方华创", "code": "002371.SZ", "weight": 0.40},
            {"name": "中微公司", "code": "688012.SH", "weight": 0.30},
            {"name": "拓荆科技", "code": "688072.SH", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "存储": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "兆易创新", "code": "603986.SH", "weight": 0.35},
            {"name": "江波龙", "code": "301308.SZ", "weight": 0.30},
            {"name": "佰维存储", "code": "688525.SH", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.15},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
# V4.4 运行模式控制(P0-3: prod|demo 启动开关)
# ═══════════════════════════════════════════════════════════════
RUN_MODE: str = "demo"  # 默认演示模式,pipeline通过set_mode()切换

def set_mode(mode: str) -> None:
    """
    设置运行模式。prod模式下,纯MOCK数据将触发报错。
    由 pipeline.py 在启动时调用。
    """
    global RUN_MODE
    if mode in ("prod", "demo"):
        RUN_MODE = mode
        logger.info("[V4.4] 运行模式已设置: %s", mode)
    else:
        raise ValueError(f"无效的运行模式: {mode},必须是 'prod' 或 'demo'")

def _check_mock_in_prod(level: str) -> None:
    """
    生产模式下检查:若即将返回纯MOCK数据且未合并外部真实数据,则报错。
    """
    if RUN_MODE == "prod":
        logger.error("❌ [PROD模式] %s 数据为纯MOCK,未接入真实数据源。请预取真实数据后通过 --input-data 传入,或切换至 demo 模式。", level)
        raise RuntimeError(
            f"[PROD模式] {level} 数据获取失败: 纯MOCK数据在生产环境中被禁止。\n"
            f"解决方案:\n"
            f"  1. 预取真实数据: python3 fetch_real_data.py <行业>\n"
            f"  2. 通过 --input-data 传入 JSON\n"
            f"  3. 或切换至 demo 模式: ./run.sh <代码> --mode demo"
        )

# ═══════════════════════════════════════════════════════════════
# Mock 数据库(演示用,生产环境替换为真实API/搜索)
# ═══════════════════════════════════════════════════════════════

# L1: 官方/行业协会模拟数据
MOCK_L1_DATABASE: Dict[str, Dict[str, Any]] = {
    "光模块": {
        "订单增速": {"value": 25.0, "source": "中国光通信产业联盟 2026Q1报告", "date": "2026-04-15"},
        "产能利用率": {"value": 88.0, "source": "工信部电子信息司产能监测", "date": "2026-03-31"},
    },
    "光通信": {
        "订单增速": {"value": 22.0, "source": "中国通信工业协会 2026Q1统计", "date": "2026-04-10"},
    },
    "ABF载板": {
        "产能利用率": {"value": 85.0, "source": "CPCA印制电路行业协会 2026Q1", "date": "2026-04-01"},
    },
}

# L2: 券商研报聚合模拟数据
MOCK_L2_DATABASE: Dict[str, Dict[str, Any]] = {
    "光模块": {
        "订单增速": {
            "reports": [
                {"broker": "申万宏源", "value": 28.0, "date": "2026-04-20"},
                {"broker": "中信证券", "value": 24.0, "date": "2026-04-18"},
                {"broker": "高盛", "value": 26.5, "date": "2026-04-15"},
            ],
            "avg": 26.17,
        },
        "产能利用率": {
            "reports": [
                {"broker": "中金公司", "value": 90.0, "date": "2026-04-12"},
                {"broker": "华泰证券", "value": 87.0, "date": "2026-04-10"},
            ],
            "avg": 88.5,
        },
        "毛利率": {
            "reports": [
                {"broker": "申万宏源", "value": 32.5, "date": "2026-04-20"},
                {"broker": "天风证券", "value": 31.0, "date": "2026-04-15"},
                {"broker": "中信证券", "value": 31.5, "date": "2026-04-10"},
            ],
            "avg": 31.67,
        },
    },
    "光通信": {
        "订单增速": {
            "reports": [
                {"broker": "中信证券", "value": 20.0, "date": "2026-04-18"},
                {"broker": "招商证券", "value": 23.0, "date": "2026-04-15"},
            ],
            "avg": 21.5,
        },
    },
    "ABF载板": {
        "订单增速": {
            "reports": [
                {"broker": "申万宏源", "value": 18.0, "date": "2026-04-12"},
                {"broker": "中金公司", "value": 20.0, "date": "2026-04-10"},
                {"broker": "华泰证券", "value": 16.5, "date": "2026-04-08"},
            ],
            "avg": 18.17,
        },
        "产能利用率": {
            "reports": [
                {"broker": "高盛", "value": 86.0, "date": "2026-04-05"},
                {"broker": "天风证券", "value": 84.0, "date": "2026-04-02"},
            ],
            "avg": 85.0,
        },
    },
    "PCB": {
        "订单增速": {
            "reports": [
                {"broker": "申万宏源", "value": 15.0, "date": "2026-04-15"},
                {"broker": "中信证券", "value": 17.0, "date": "2026-04-12"},
            ],
            "avg": 16.0,
        },
    },
}

# L3: 个股数据模拟(用于加权推断)
MOCK_L3_STOCK_DATA: Dict[str, Dict[str, Any]] = {
    "300308.SZ": {
        "name": "中际旭创",
        "order_growth": 30.0,
        "capacity_util": 92.0,
        "inventory_days": 45,
        "price_trend": 12.0,
        "gross_margin": 33.5,
        "report_date": "2026-03-31",
    },
    "300502.SZ": {
        "name": "新易盛",
        "order_growth": 28.0,
        "capacity_util": 89.0,
        "inventory_days": 52,
        "price_trend": 10.0,
        "gross_margin": 32.0,
        "report_date": "2026-03-31",
    },
    "002281.SZ": {
        "name": "光迅科技",
        "order_growth": 22.0,
        "capacity_util": 85.0,
        "inventory_days": 58,
        "price_trend": 8.0,
        "gross_margin": 28.5,
        "report_date": "2026-03-31",
    },
    "002916.SZ": {
        "name": "深南电路",
        "order_growth": 20.0,
        "capacity_util": 88.0,
        "inventory_days": 65,
        "price_trend": 5.0,
        "gross_margin": 26.0,
        "report_date": "2026-03-31",
    },
    "002436.SZ": {
        "name": "兴森科技",
        "order_growth": 16.0,
        "capacity_util": 82.0,
        "inventory_days": 72,
        "price_trend": 4.0,
        "gross_margin": 22.5,
        "report_date": "2026-03-31",
    },
    "002463.SZ": {
        "name": "深南电路",
        "order_growth": 18.0,
        "capacity_util": 86.0,
        "inventory_days": 60,
        "price_trend": 6.0,
        "gross_margin": 27.0,
        "report_date": "2026-03-31",
    },
    "002938.SZ": {
        "name": "鹏鼎控股",
        "order_growth": 14.0,
        "capacity_util": 80.0,
        "inventory_days": 55,
        "price_trend": 3.0,
        "gross_margin": 24.0,
        "report_date": "2026-03-31",
    },
    "OTHER": {
        "name": "行业其他公司平均",
        "order_growth": 15.0,
        "capacity_util": 78.0,
        "inventory_days": 70,
        "price_trend": 5.0,
        "gross_margin": 25.0,
        "report_date": "2026-03-31",
    },
}

# L4: 知识库历史数据
MOCK_L4_KNOWLEDGE_BASE: Dict[str, Dict[str, Any]] = {
    "光模块": {
        "订单增速": {"value": 20.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
        "产能利用率": {"value": 80.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
        "毛利率": {"value": 30.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
    },
    "光通信": {
        "订单增速": {"value": 18.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
    },
    "ABF载板": {
        "订单增速": {"value": 12.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
        "产能利用率": {"value": 78.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
    },
    "PCB": {
        "订单增速": {"value": 10.0, "period": "2025年均值", "source": "industrial-sentinel V4.2 历史分析"},
    },
}


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# 预取数据提取(V4.4 真实数据层)
# ───────────────────────────────────────────────────────────────

def _extract_l1_prefetched(prefetched: Dict[str, Any], industry_name: str, metric: str) -> Optional[IndustryDataPoint]:
    """从预取 JSON 的 l1_official 段提取 L1 数据。"""
    if not prefetched:
        return None
    l1 = prefetched.get("l1_official", {})
    metric_data = l1.get(metric)
    if metric_data is None:
        return None
    value = metric_data.get("value")
    if value is None:
        return None
    source_detail = f"L1官方(真实): {source_url[:60]}..." if len(source_url) > 60 else f"L1官方(真实): {source_url}"
    return IndustryDataPoint(
        value=value,
        source_level="L1",
        data_date=fetched_at[:10] if isinstance(fetched_at, str) else datetime.now().strftime("%Y-%m-%d"),
        source_detail=source_detail,
    )


def _extract_l2_prefetched(prefetched: Dict[str, Any], industry_name: str, metric: str) -> Optional[IndustryDataPoint]:
    """从预取 JSON 的 l2_broker 段提取 L2 数据。"""
    if not prefetched:
        return None
    l2 = prefetched.get("l2_broker", {})
    metric_data = l2.get(metric)
    if metric_data is None:
        return None
    value = metric_data.get("value")
    if value is None:
        return None
    source_urls = metric_data.get("source_urls", [])
    report_count = metric_data.get("report_count", len(source_urls))
    fetched_at = metric_data.get("fetched_at", datetime.now().strftime("%Y-%m-%d"))
    source_detail = f"L2研报(真实): {report_count}篇研报聚合 | 来源: {', '.join(source_urls[:2])[:80]}"
    return IndustryDataPoint(
        value=value,
        source_level="L2",
        data_date=fetched_at[:10] if isinstance(fetched_at, str) else datetime.now().strftime("%Y-%m-%d"),
        source_detail=source_detail,
    )


def _extract_l3_prefetched(prefetched: Dict[str, Any], industry_name: str, metric: str) -> Optional[IndustryDataPoint]:
    """从预取 JSON 的 l3_stock 段提取 L3 推断数据。"""
    if not prefetched:
        return None
    l3 = prefetched.get("l3_stock", {})
    if not l3:
        return None
    # 使用预存推断值(如果存在)
    inferred = prefetched.get("l3_inferred", {})
    if metric in inferred:
        value = inferred[metric]
        tickers = list(l3.keys())[:5]
        fetched_at = datetime.now().strftime("%Y-%m-%d")
        # 取各股 fetched_at 中的最新日期
        dates = [d.get("fetched_at", fetched_at)[:10] for d in l3.values() if isinstance(d, dict)]
        if dates:
            fetched_at = max(dates)
        source_detail = f"L3个股推断(真实): 基于 {', '.join(tickers[:3])} 等 {len(l3)} 只个股收盘数据"
        return IndustryDataPoint(
            value=round(value, 2) if isinstance(value, (int, float)) else value,
            source_level="L3",
            data_date=fetched_at[:10] if isinstance(fetched_at, str) else datetime.now().strftime("%Y-%m-%d"),
            source_detail=source_detail,
        )
    return None


def _extract_l4_prefetched(prefetched: Dict[str, Any], industry_name: str, metric: str) -> Optional[IndustryDataPoint]:
    """从预取 JSON 的 l4_kb 段提取 L4 数据,并检查 staleness。"""
    if not prefetched:
        return None
    l4 = prefetched.get("l4_kb", {})
    value = l4.get(metric)
    if value is None:
        return None
    # 检查 knowledge base 数据是否 >30 天
    kb_fetched_at = prefetched.get("meta", {}).get("fetched_at", datetime.now().strftime("%Y-%m-%d"))
    kb_date = kb_fetched_at[:10] if isinstance(kb_fetched_at, str) else datetime.now().strftime("%Y-%m-%d")
    source_detail = f"L4知识库(预存): 历史参考数据"
    return IndustryDataPoint(
        value=value,
        source_level="L4",
        data_date=kb_date,
        source_detail=source_detail,
    )


# ───────────────────────────────────────────────────────────────
# 预取数据聚合:将 agent 真实数据合并到 MOCK 结构
# ───────────────────────────────────────────────────────────────

def _merge_prefetched_into_mock(prefetched: Dict[str, Any]) -> None:
    """
    将预取的真实数据注入到 MOCK 数据库,使现有查询函数无需改动即可使用真实数据。
    这是一种兼容性策略:当 pipeline 传入真实 JSON 时,先将其合并到 MOCK_L1/L2/L3/L4,
    后续 acquire_industry_data 的查询函数会优先命中这些真实数据。
    """
    global MOCK_L1_DATABASE, MOCK_L2_DATABASE, MOCK_L3_STOCK_DATA, MOCK_L4_KNOWLEDGE_BASE
    if not prefetched:
        return
    # V4.4 schema: industry 可能在顶层,旧版在 meta.industry
    industry = prefetched.get("industry", "")
    if not industry:
        industry = prefetched.get("meta", {}).get("industry", "")

    # 合并 L1
    l1 = prefetched.get("l1_official", {})
    if l1:
        if industry not in MOCK_L1_DATABASE:
            MOCK_L1_DATABASE[industry] = {}
        for metric, data in l1.items():
            MOCK_L1_DATABASE[industry][metric] = {
                "value": data.get("value"),
                "source": data.get("source", "L1预取数据"),
                "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
                "source_url": data.get("source_url", ""),
                "fetched_at": data.get("fetched_at", ""),
            }

    # 合并 L2
    l2 = prefetched.get("l2_broker", {})
    if l2:
        if industry not in MOCK_L2_DATABASE:
            MOCK_L2_DATABASE[industry] = {}
        for metric, data in l2.items():
            MOCK_L2_DATABASE[industry][metric] = {
                "reports": [{"broker": "研报聚合", "value": data.get("value"), "date": data.get("date", "2026-05-01")}],
                "avg": data.get("value"),
                "source_url": data.get("source_url", ""),
                "fetched_at": data.get("fetched_at", ""),
            }

    # 合并 L3 个股数据
    l3 = prefetched.get("l3_stock", {})
    if l3:
        # V4.4 schema: l3_stock 可以是 {metric: {value, source, date}} 或 {ticker: {...}}
        # 检查是否为按metric组织的格式
        metric_like = any(k in {"value", "source", "date", "fetched_at"} for k in next(iter(l3.values()), {}).keys())
        if metric_like:
            # 按metric组织的L3推断数据
            for metric, data in l3.items():
                # 存入一个特殊标记,让acquire_industry_data直接命中
                pass  # 由 acquire_industry_data 的 V4.4 直接命中逻辑处理
        else:
            # 按ticker组织的旧格式
            for ticker, tdata in l3.items():
                if ticker not in MOCK_L3_STOCK_DATA:
                    MOCK_L3_STOCK_DATA[ticker] = {}
                MOCK_L3_STOCK_DATA[ticker].update({
                    "name": tdata.get("name", ticker),
                    "order_growth": tdata.get("order_growth"),
                    "capacity_util": tdata.get("capacity_util"),
                    "inventory_days": tdata.get("inventory_days"),
                    "price_trend": tdata.get("price_trend"),
                    "gross_margin": tdata.get("gross_margin"),
                    "report_date": tdata.get("fetched_at", datetime.now().strftime("%Y-%m-%d"))[:10],
                })

    # 合并 L4
    l4 = prefetched.get("l4_kb", {})
    if l4:
        if industry not in MOCK_L4_KNOWLEDGE_BASE:
            MOCK_L4_KNOWLEDGE_BASE[industry] = {}
        for metric, value in l4.items():
            MOCK_L4_KNOWLEDGE_BASE[industry][metric] = {
                "value": value,
                "period": "知识库预存",
                "source": "industrial-sentinel KB",
            }

    logger.info("[V4.4] 预取真实数据已合并到 MOCK 数据库: industry=%s, L1=%d, L2=%d, L3=%d, L4=%d",
                industry, len(l1), len(l2), len(l3), len(l4))


def get_metric_key(industry_name: str, metric: str) -> str:
    """将中文metric映射到内部英文key(用于L3个股数据查找)。"""
    industry_config = INDUSTRY_LEADERS.get(industry_name, {})
    metric_map = industry_config.get("metric_map", {})
    return metric_map.get(metric, metric)


# ═══════════════════════════════════════════════════════════════
# L1: 官方/行业协会数据
# ═══════════════════════════════════════════════════════════════

def search_official_data(industry_name: str, metric: str) -> IndustryDataPoint:
    """
    L1 数据获取:官方/行业协会数据

    生产环境应替换为:
      - 国家统计局 API
      - 行业协会定期报告(如CPCA、中国光通信产业联盟)
      - 工信部产能监测平台
    """
    logger.info(f"[L1] 尝试获取官方数据: {industry_name}.{metric}")

    industry_data = MOCK_L1_DATABASE.get(industry_name, {})
    metric_data = industry_data.get(metric)

    # V4.4 P0-3: prod模式检查--纯MOCK数据报错
    if metric_data is not None and RUN_MODE == "prod":
        # 检查是否是外部注入的真实数据(有source_url/fetched_at标记)
        is_external = isinstance(metric_data, dict) and (
            "source_url" in metric_data or "fetched_at" in metric_data
            or str(metric_data.get("source", "")).startswith("外部")
        )
        if not is_external:
            _check_mock_in_prod("L1")

    if metric_data is None:
        raise DataSourceFallback(
            f"L1无数据: {industry_name}.{metric} 未命中官方数据库",
            failed_level="L1",
            attempted_source="official/industry_association",
            next_level="L2"
        )

    source_detail = f"L1官方: {metric_data['source']} ({metric_data.get('date', 'N/A')})"

    # L1 置信度基准:官方数据通常最可靠,但取决于发布机构的权威性

    return IndustryDataPoint(
        value=metric_data["value"],
        source_level="L1",
        source_detail=source_detail,
    )


# ═══════════════════════════════════════════════════════════════
# L2: 券商研报聚合
# ═══════════════════════════════════════════════════════════════

def search_broker_reports(industry_name: str, metric: str, num_reports: int = 3) -> IndustryDataPoint:
    """
    L2 数据获取:券商研报聚合(取平均 + 离散度校验)

    生产环境应替换为:
      - Wind/iFinD 研报API
      - 使用任意搜索工具（web_search/kimi_search/serpapi等）搜索 "{industry} {metric} 研报"
      - 东方财富研报库

    质量控制:
      - 至少 num_reports 篇研报才聚合
      - 离散度 >30% 时降低置信度(研报分歧大)
    """
    logger.info(f"[L2] 尝试获取研报数据: {industry_name}.{metric} (至少{num_reports}篇)")

    industry_data = MOCK_L2_DATABASE.get(industry_name, {})
    metric_data = industry_data.get(metric)

    # V4.4 P0-3: prod模式检查--纯MOCK数据报错
    if metric_data is not None and RUN_MODE == "prod":
        is_external = isinstance(metric_data, dict) and (
            "source_url" in metric_data or "fetched_at" in metric_data
            or str(metric_data.get("source", "")).startswith("外部")
        )
        if not is_external:
            _check_mock_in_prod("L2")

    if metric_data is None:
        raise DataSourceFallback(
            f"L2无数据: {industry_name}.{metric} 未命中研报数据库",
            failed_level="L2",
            attempted_source=f"broker_reports(num={num_reports})",
            next_level="L3"
        )

    reports = metric_data.get("reports", [])
    if len(reports) < num_reports:
        raise DataSourceFallback(
            f"L2数据不足: 仅找到{len(reports)}篇研报,要求{num_reports}篇",
            failed_level="L2",
            attempted_source=f"broker_reports(found={len(reports)}, required={num_reports})",
            next_level="L3"
        )

    # 计算平均值和离散度
    values = [r["value"] for r in reports]
    avg_value = sum(values) / len(values)
    max_val, min_val = max(values), min(values)
    dispersion = (max_val - min_val) / avg_value * 100 if avg_value != 0 else 0

    # 新鲜度取最新研报日期
    latest_date = max(r.get("date", "2026-01-01") for r in reports)

    # 置信度:基础80,研报数量加成,离散度惩罚
    confidence = 80
    if dispersion > 30:
        confidence -= 15  # 离散度大,分歧严重
    elif dispersion > 15:
        confidence -= 5

    broker_names = ", ".join([r["broker"] for r in reports])
    source_detail = f"L2研报: {broker_names} 共{len(reports)}篇,均值{avg_value:.2f},离散度{dispersion:.1f}% ({latest_date})"

    return IndustryDataPoint(
        value=round(avg_value, 2),
        source_level="L2",
        source_detail=source_detail,
    )


# ═══════════════════════════════════════════════════════════════
# L3: 龙头个股加权推断
# ═══════════════════════════════════════════════════════════════

def infer_from_stocks(
    industry_name: str,
    metric: str,
    stock_list: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[List[float]] = None,
) -> IndustryDataPoint:
    """
    L3 数据获取:龙头个股加权推断

    核心逻辑:行业指标 = Σ(个股指标 × 权重)

    权重设计原则(以光模块为例):
      - 中际旭创 40%:全球光模块龙头,份额最大,代表性最强
      - 新易盛 30%:800G/1.6T核心供应商,成长性代表
      - 光迅科技 20%:国资背景,运营商市场代表
      - 其他 10%:长尾公司平均,防止龙头偏差

    以ABF载板为例:
      - 深南电路 50%:国内ABF载板绝对龙头
      - 兴森科技 30%:IC载板重要玩家
      - 其他 20%:海外厂商(Ibiden/Shinko)国内映射

    生产环境应替换为:
      - 同花顺API获取个股财务数据
      - 东方财富个股研报提取
    """
    logger.info(f"[L3] 尝试个股推断: {industry_name}.{metric}")

    # V4.4 P0-3: prod模式检查--若所有龙头个股数据均为纯MOCK,则报错
    if RUN_MODE == "prod":
        industry_config = INDUSTRY_LEADERS.get(industry_name)
        if industry_config is not None:
            all_mock = True
            for leader in industry_config["leaders"]:
                code = leader["code"]
                stock_data = MOCK_L3_STOCK_DATA.get(code)
                if stock_data is not None:
                    # 检查是否有外部数据标记
                    if "source_url" in stock_data or "fetched_at" in stock_data or str(stock_data.get("source", "")).startswith("外部"):
                        all_mock = False
                        break
            if all_mock:
                _check_mock_in_prod("L3")

    # 获取行业预设配置
    industry_config = INDUSTRY_LEADERS.get(industry_name)
    if industry_config is None:
        raise DataSourceFallback(
            f"L3无配置: {industry_name} 未在INDUSTRY_LEADERS中定义",
            failed_level="L3",
            attempted_source="stock_inference",
            next_level="L4"
        )

    # 使用预设的龙头列表,或外部传入
    leaders = stock_list or industry_config["leaders"]
    if weights is None:
        weights = [l["weight"] for l in leaders]

    # 权重复核
    total_weight = sum(weights)
    if abs(total_weight - 1.0) > 0.01:
        weights = [w / total_weight for w in weights]  # 归一化

    # 映射metric到个股数据key
    metric_key = get_metric_key(industry_name, metric)

    # 加权计算
    weighted_sum = 0.0
    valid_sources = []
    missing_stocks = []
    latest_date = "2025-01-01"

    for leader, weight in zip(leaders, weights):
        code = leader["code"]
        stock_data = MOCK_L3_STOCK_DATA.get(code)

        if stock_data is None:
            missing_stocks.append(code)
            continue

        value = stock_data.get(metric_key)
        if value is None:
            missing_stocks.append(f"{code}.{metric_key}")
            continue

        weighted_sum += value * weight
        valid_sources.append(f"{stock_data['name']}({code}): {value} × {weight:.0%}")

        # 跟踪最新数据日期
        report_date = stock_data.get("report_date", "2025-01-01")
        if report_date > latest_date:
            latest_date = report_date

    # 如果缺失过多(>50%权重),降级到L4
    missing_weight = sum(l["weight"] for l, w in zip(leaders, weights)
                         if l["code"] in [m.split(".")[0] for m in missing_stocks] or l["code"] in missing_stocks)
    if missing_weight > 0.5:
        raise DataSourceFallback(
            f"L3数据缺失过多: 缺失权重{missing_weight:.0%},无法可靠推断",
            failed_level="L3",
            attempted_source=f"stock_inference(missing_weight={missing_weight:.2f})",
            next_level="L4"
        )

    # 如果只有部分数据,按实际权重重新归一化
    actual_weight = sum(w for l, w in zip(leaders, weights) if l["code"] not in missing_stocks)
    if actual_weight < 1.0 and actual_weight > 0:
        weighted_sum = weighted_sum / actual_weight


    # L3 置信度基准:个股推断,天然低于L1/L2
    # 权重集中度越高置信度越高(龙头代表性强),反之越低
    max_weight = max(weights)

    source_detail = f"L3个股推断: {'; '.join(valid_sources)} | 最新财报日期:{latest_date}"

    return IndustryDataPoint(
        value=round(weighted_sum, 2),
        source_level="L3",
        source_detail=source_detail,
    )


# ═══════════════════════════════════════════════════════════════
# L4: 知识库历史数据
# ═══════════════════════════════════════════════════════════════

def query_knowledge_base(industry_name: str, metric: str) -> IndustryDataPoint:
    """
    L4 数据获取:知识库历史数据

    最后防线:当 L1→L3 全部失败时,使用历史分析数据作为参考。
    明确标注为"历史参考",置信度强制压低。

    生产环境应替换为:
      - 读取 /raw 目录下的历史分析报告
      - 查询 industrial-sentinel 过往评分记录
      - 读取用户上传的产业链分析笔记
    """
    logger.info(f"[L4] 尝试知识库查询: {industry_name}.{metric}")

    industry_data = MOCK_L4_KNOWLEDGE_BASE.get(industry_name, {})
    metric_data = industry_data.get(metric)

    # V4.4 P0-3: prod模式检查--纯MOCK知识库数据报错
    if metric_data is not None and RUN_MODE == "prod":
        is_external = isinstance(metric_data, dict) and (
            "source_url" in metric_data or "fetched_at" in metric_data
            or str(metric_data.get("source", "")).startswith("外部")
        )
        if not is_external:
            _check_mock_in_prod("L4")

    if metric_data is None:
        raise AllLevelsFailed(
            industry_name=industry_name,
            metric=metric,
            attempts=["L1", "L2", "L3", "L4"]
        )

    source_detail = f"L4知识库: {metric_data['source']} ({metric_data['period']})"

    # L4 置信度强制压低:历史数据仅供参考

    return IndustryDataPoint(
        value=metric_data["value"],
        source_level="L4",
        source_detail=source_detail,
    )


# ═══════════════════════════════════════════════════════════════
# 主控函数:四层降级获取
# ═══════════════════════════════════════════════════════════════

def acquire_industry_data(
    industry_name: str,
    metrics_list: List[str],
    max_attempts: int = 3,
    external_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, IndustryDataPoint]:
    """
    行业数据获取主控函数 -- System A 的数据入口

    自动执行 L1→L2→L3→L4 降级路径,为每个metric返回最优可用的数据点。

    参数:
        industry_name: 行业名称(如"光模块"、"ABF载板")
        metrics_list: 需要获取的指标列表(如["订单增速", "产能利用率", "毛利率"])
        max_attempts: 每层最大尝试次数(默认3,用于网络重试)

    返回:
        Dict[metric, IndustryDataPoint] -- 每个metric对应一个数据点

    异常:
        AllLevelsFailed: 当某个metric在L1→L4全部失败时抛出

    使用示例:
        >>> result = acquire_industry_data("光模块", ["订单增速", "产能利用率"])
        >>> result["订单增速"].value
        25.0
        >>> result["订单增速"].source_level
        'L1'
    """
    result: Dict[str, IndustryDataPoint] = {}

    # 四层获取函数队列
    level_functions = [
        ("L1", search_official_data),
        ("L2", search_broker_reports),
        ("L3", infer_from_stocks),
        ("L4", query_knowledge_base),
    ]

    # 若提供了预取真实数据(V4.4 JSON 结构),先合并到 MOCK 数据库
    if external_data and isinstance(external_data, dict):
        # 检测是否为 V4.4 预取 JSON(含 l1_official / l2_broker 等字段)
        if any(k in external_data for k in ("l1_official", "l2_broker", "l3_stock", "l4_kb")):
            logger.info("[V4.4] 检测到预取真实数据 JSON,开始合并到 MOCK 数据库...")
            _merge_prefetched_into_mock(external_data)
            logger.info("[V4.4] 预取数据合并完成,后续 L1→L4 查询将优先命中真实数据")
        # 否则保持原有 external_data 逻辑(向后兼容)
        elif "metrics" in external_data:
            logger.info(f"📥 收到外部数据: {len(external_data.get('metrics', {}))} 个指标")

    for metric in metrics_list:
        data_point: Optional[IndustryDataPoint] = None
        attempted_levels = []

        # ===== V4.4 格式: 四层分离直接命中 =====
        if external_data and any(k in external_data for k in ("l1_official", "l2_broker", "l3_stock", "l4_kb")):
            # 按优先级 L1 > L2 > L3 > L4 查找
            for level_key, level_name in [("l1_official", "L1"), ("l2_broker", "L2"), ("l3_stock", "L3"), ("l4_kb", "L4")]:
                level_data = external_data.get(level_key, {})
                if metric in level_data:
                    ext_metric = level_data[metric]
                    # 计算数据新鲜度
                    try:
                        date_str = ext_metric.get("date", ext_metric.get("fetched_at", datetime.now().strftime("%Y-%m-%d")))[:10]
                        data_date = datetime.strptime(date_str, "%Y-%m-%d")
                        days_old = (datetime.now() - data_date).days
                    except (ValueError, TypeError):
                        pass

                    source_detail = f"{level_name}预取: {ext_metric.get('source', '外部数据')}"

                    data_point = IndustryDataPoint(
                        value=ext_metric["value"],
                        source_level=level_name,
                        source_detail=source_detail,
                    )
                    attempted_levels.append(f"{level_name}(预取直接命中)")
                    logger.info(f"✅ [V4.4预取] {level_name}直接命中 {metric}: {data_point.value}")
                    break  # 找到就退出

        # ===== 旧版格式: metrics 字典直接命中 =====
        if data_point is None and external_data and "metrics" in external_data and metric in external_data.get("metrics", {}):
            ext_metric = external_data["metrics"][metric]
            source_level = "L2" if "研报" in ext_metric.get("source", "") else "L3"

            # 计算数据新鲜度
            try:
                data_date = datetime.strptime(ext_metric.get("date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d")
                days_old = (datetime.now() - data_date).days
            except (ValueError, TypeError):
                pass

            data_point = IndustryDataPoint(
                value=ext_metric["value"],
                source_level=source_level,
                source_detail=f"{source_level}真实: {ext_metric.get('source', '外部数据')}",
            )
            attempted_levels.append(f"{source_level}(外部真实数据)")
            logger.info(f"✅ [外部数据] 直接命中 {metric}: {data_point.value}")

        # ===== 若外部数据未命中,走L1→L4降级 =====

        for level_name, level_func in level_functions:
            if data_point is not None:
                break

            # 尝试当前层级(可重试max_attempts次)
            for attempt in range(max_attempts):
                try:
                    logger.info(f"[{level_name}] 尝试 {metric} (第{attempt+1}/{max_attempts}次)")

                    if level_name == "L2":
                        data_point = level_func(industry_name, metric, num_reports=3)
                    elif level_name == "L3":
                        data_point = level_func(industry_name, metric, stock_list=None, weights=None)
                    else:
                        data_point = level_func(industry_name, metric)

                    attempted_levels.append(level_name)
                    logger.info(f"✅ [{level_name}] 成功获取 {metric}: {data_point.value}")
                    break

                except DataSourceFallback as e:
                    attempted_levels.append(f"{level_name}(失败: {e.attempted_source})")
                    logger.warning(f"⚠️ [{level_name}] 失败: {str(e)},降级到 {e.next_level}")
                    break  # 降级到下一层级,不在同一层重试

                except Exception as e:
                    attempted_levels.append(f"{level_name}(异常: {str(e)})")
                    logger.error(f"❌ [{level_name}] 异常: {e}")
                    if attempt == max_attempts - 1:
                        break  # 重试用尽,降级

        if data_point is None:
            raise AllLevelsFailed(industry_name, metric, attempted_levels)

        result[metric] = data_point

    return result


# ═══════════════════════════════════════════════════════════════
# 批量获取 + 报告生成
# ═══════════════════════════════════════════════════════════════

def acquire_industry_data_batch(
    industry_name: str,
    metrics_list: List[str],
    external_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, IndustryDataPoint], Dict[str, Any]]:
    """
    批量获取 + 生成溯源报告

    返回:
        (data_dict, report_dict)
        report_dict 包含每个metric的来源层级、置信度、新鲜度、降级路径
    """
    data_dict = acquire_industry_data(industry_name, metrics_list, external_data=external_data)

    report = {
        "industry": industry_name,
        "metrics_count": len(metrics_list),
        "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": {},
        "source_distribution": {"L1": 0, "L2": 0, "L3": 0, "L4": 0},
        "lowest_confidence_metric": "",
    }


    for metric, dp in data_dict.items():
        report["metrics"][metric] = dp.to_dict()
        report["source_distribution"][dp.source_level] += 1

    n = len(data_dict)

    return data_dict, report


def print_acquisition_report(report: Dict[str, Any]):
    """打印数据获取报告(中文,供System A集成使用)。"""
    print(f"\n{'='*60}")
    print(f"📊 行业数据获取报告 -- {report['industry']}")
    print(f"{'='*60}")
    print(f"获取时间: {report['acquired_at']}")
    print(f"指标数量: {report['metrics_count']}")
    print(f"\n📈 来源层级分布:")
    for level, count in report["source_distribution"].items():
        bar = "█" * count + "░" * (report["metrics_count"] - count)
        print(f"  {level}: {bar} ({count}/{report['metrics_count']})")

    if report["lowest_confidence_metric"]:
        print(f"⚠️  最低置信度指标: {report['lowest_confidence_metric']}")

    print(f"\n📋 明细:")
    for metric, data in report["metrics"].items():
        level_icon = {"L1": "🏛️", "L2": "📑", "L3": "📊", "L4": "📚"}.get(data["source_level"], "❓")
        print(f"      来源: {data['source_detail']}")

    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# 演示与验证
# ═══════════════════════════════════════════════════════════════

def demo_optical_module_da():
    """演示:光模块行业 -- L1命中,无需降级"""
    print("\n" + "🔷"*30)
    print("【演示1】光模块行业 -- L1/L2 均命中,L1优先")
    print("🔷"*30)

    metrics = ["订单增速", "产能利用率", "毛利率"]
    data, report = acquire_industry_data_batch("光模块", metrics)
    print_acquisition_report(report)

    # 验证
    assert data["订单增速"].source_level == "L1", "订单增速应从L1获取"
    assert data["产能利用率"].source_level == "L1", "产能利用率应从L1获取"
    assert data["毛利率"].source_level == "L2", "毛利率L1无数据,应从L2降级获取"
    print("✅ 光模块演示通过\n")
    return data, report


def demo_abf_substrate_da():
    """演示:ABF载板 -- L1部分命中,L2补充,L3兜底"""
    print("\n" + "🔶"*30)
    print("【演示2】ABF载板行业 -- L1部分命中,L2补充,L3兜底")
    print("🔶"*30)

    metrics = ["订单增速", "产能利用率", "库存天数"]
    data, report = acquire_industry_data_batch("ABF载板", metrics)
    print_acquisition_report(report)

    # 验证
    # ABF载板的"订单增速"在L1无数据,应降级到L2
    assert data["订单增速"].source_level == "L2", f"订单增速应从L2获取,实际为{data['订单增速'].source_level}"
    # "产能利用率"在L1有数据
    assert data["产能利用率"].source_level == "L1", f"产能利用率应从L1获取,实际为{data['产能利用率'].source_level}"
    # "库存天数"在L1/L2均无数据,应降级到L3
    assert data["库存天数"].source_level == "L3", f"库存天数应从L3获取,实际为{data['库存天数'].source_level}"
    print("✅ ABF载板演示通过\n")
    return data, report


def demo_fallback_chain():
    """演示:强制降级链验证 -- 模拟L1/L2失败,验证L3兜底"""
    print("\n" + "🔺"*30)
    print("【演示3】强制降级链 -- 模拟L1/L2失败,验证L3→L4降级")
    print("🔺"*30)

    # 测试一个L1/L2/L4都无数据的行业,看L3能否兜底
    # 先用PCB测试:L1无数据,L2有订单增速,L3有完整数据
    metrics = ["订单增速"]

    # 正常路径:PCB的订单增速--L1无数据,L2仅2篇不足3篇,正确降级到L3
    data_normal, _ = acquire_industry_data_batch("PCB", metrics)
    print(f"PCB订单增速正常路径: {data_normal['订单增速'].source_level} = {data_normal['订单增速'].value}")
    assert data_normal["订单增速"].source_level == "L3", "PCB订单增速L1无、L2不足3篇,应降级到L3"

    # 验证L3推断的数值合理性:光模块龙头加权
    l3_data = infer_from_stocks("光模块", "订单增速")
    print(f"\n光模块L3推断详情:")
    print(f"  计算过程: 中际旭创(30.0×40%) + 新易盛(28.0×30%) + 光迅科技(22.0×20%) + 其他(15.0×10%)")
    expected = 30.0*0.40 + 28.0*0.30 + 22.0*0.20 + 15.0*0.10
    print(f"  预期值: {expected:.2f}")
    print(f"  实际值: {l3_data.value}")
    assert abs(l3_data.value - expected) < 0.01, f"L3加权计算错误: {l3_data.value} != {expected}"

    # 验证ABF载板L3推断
    l3_abf = infer_from_stocks("ABF载板", "订单增速")
    print(f"\nABF载板L3推断详情:")
    print(f"  计算过程: 深南电路(20.0×50%) + 兴森科技(16.0×30%) + 其他(15.0×20%)")
    expected_abf = 20.0*0.50 + 16.0*0.30 + 15.0*0.20
    print(f"  预期值: {expected_abf:.2f}")
    print(f"  实际值: {l3_abf.value}")
    assert abs(l3_abf.value - expected_abf) < 0.01, f"ABF L3加权计算错误: {l3_abf.value} != {expected_abf}"

    print("\n✅ 降级链演示通过\n")


def demo_freshness_scoring():
    """演示:数据新鲜度评分验证"""
    print("\n" + "💧"*30)
    print("【演示4】数据新鲜度评分验证")
    print("💧"*30)

    test_cases = [
        ("2026-05-12", 100.0, "当日"),      # 今天
        ("2026-05-11", 90.0, "1天前"),      # 1天内
        ("2026-05-05", 82.0, "1周前"),      # 1周内
        ("2026-04-12", 49.3, "1月前"),      # 1月内
        ("2026-01-15", 29.5, "4月前"),      # 1季度+
        ("2025-06-01", 4.0, "近1年"),       # 近1年
        ("2024-01-01", 0.0, ">1年"),        # >1年
    ]

    for date_str, expected_approx, desc in test_cases:
        ok = abs(score - expected_approx) < 5  # 允许±5误差
        status = "✅" if ok else "❌"
        print(f"  {status} {desc} ({date_str}): 新鲜度={score:.1f} (预期≈{expected_approx})")

    print("\n✅ 新鲜度评分演示通过\n")


def demo_all_da():
    """运行全部演示"""
    print("\n" + "="*70)
    print("  V4.4 行业数据获取路径 -- 全量演示")
    print("="*70)

    demo_optical_module_da()
    demo_abf_substrate_da()
    demo_fallback_chain()
    # demo_freshness_scoring()  # V4.5 已禁用

    print("="*70)
    print("  ✅ 全部演示通过")
    print("="*70)


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Part 2 - 数据防火墙 (v44-data-firewall)
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# 异常类
# ═══════════════════════════════════════════════════════════════
class DataFirewallViolation(Exception):
    """
    数据防火墙违规异常。
    当 System A 输入数据包含公司特定字段时抛出。
    """
    def __init__(self, message: str, violations: List[str] = None):
        self.violations = violations or []
        super().__init__(message)


# ═══════════════════════════════════════════════════════════════
# 白名单:System A 允许使用的行业级字段
# ═══════════════════════════════════════════════════════════════
SYSTEM_A_ALLOWED_FIELDS: Set[str] = {
    "industry_order_growth",
    "industry_capacity_util",
    "industry_inventory_days",
    "industry_price_trend",
    "industry_policy_score",
    "industry_lifecycle_stage",
    "industry_penetration_rate",
    "industry_competition_score",
}

# 允许的前缀模式(用于动态匹配 industry_ 开头的字段)
ALLOWED_PREFIX = "industry_"


# ═══════════════════════════════════════════════════════════════
# 黑名单:System A 严禁使用的公司特定字段
# ═══════════════════════════════════════════════════════════════
SYSTEM_A_BLOCKED_FIELDS: Set[str] = {
    # 订单与营收
    "company_order_growth",
    "company_revenue_growth",
    "company_revenue",
    "company_backlog",
    # 现金流
    "company_cash_flow",
    "company_operating_cash_flow",
    "company_free_cash_flow",
    "company_cash_flow_ratio",
    # 市场份额
    "company_market_share",
    "company_share_change",
    "company_market_position",
    # 管理层
    "company_mgmt_score",
    "company_mgmt_change",
    "company_ceo_tenure",
    # 估值
    "company_valuation_pe",
    "company_valuation_pb",
    "company_valuation_ps",
    "company_valuation_peg",
    "company_dividend_yield",
    # 技术面
    "company_technical_ma",
    "company_technical_rsi",
    "company_technical_macd",
    "company_technical_volume",
    "company_support_level",
    "company_resistance_level",
    # 基本面
    "company_roe",
    "company_roic",
    "company_gross_margin",
    "company_net_margin",
    "company_debt_ratio",
    "company_patent_count",
    "company_rd_ratio",
    # 财务排雷
    "company_receivable_growth",
    "company_contract_liability",
    "company_capital_expenditure",
    "company_goodwill",
    "company_inventory_turnover",
    # 情绪/消息
    "company_news_sentiment",
    "company_analyst_coverage",
    "company_institutional_holding",
    "company_short_interest",
}

# 黑名单前缀模式
BLOCKED_PREFIXES: tuple = (
    "company_",
    "stock_",
    "firm_",
    "corp_",
    "enterprise_",
)


# ═══════════════════════════════════════════════════════════════
# 启发式检测模式
# ═══════════════════════════════════════════════════════════════

# A股股票代码正则:6位数字 + .SH/.SZ/.BJ
STOCK_CODE_PATTERN = re.compile(
    r"\b\d{6}\.(?:SH|SZ|BJ)\b",
    re.IGNORECASE
)

# 公司名称后缀启发式(常见A股公司名称后缀)
COMPANY_NAME_SUFFIXES: tuple = (
    # 通用公司后缀
    "公司",  # 捕获 "某公司"、"XX公司"、"行业公司" 等
    "股份", "科技", "电子", "通信", "光学", "半导体",
    "精密", "智能", "微", "新材", "生态", "集团",
    "控股", "实业", "制造", "软件", "网络", "仪器",
    "设备", "材料", "化学", "生物", "医药", "医疗",
    "能源", "环保", "传媒", "文化", "旅游", "航空",
    "航天", "汽车", "机械", "电气", "电力", "建设",
    "工程", "交通", "物流", "农业", "食品", "饮料",
    "纺织", "服装", "商业", "贸易", "金融", "保险",
    "银行", "证券", "地产", "置业", "矿业", "冶炼",
    "化工", "化肥", "农药", "橡胶", "塑料", "造纸",
    "印刷", "包装", "家具", "建材", "水泥", "钢铁",
    "有色", "金属", "煤炭", "石油", "燃气", "水务",
    # 行业特定后缀(覆盖用户关注标的)
    "锗业", "硅业", "光子", "芯", "创", "立",
    "光迅", "华芯", "景科技", "特光学", "光科技",
    "孚通信", "晶科技", "田微", "润光学", "绿生态",
    "通股份", "鼎股份", "天股份",
)

# 公司名称后缀正则(用于检测字段值中嵌入的公司名)
COMPANY_SUFFIX_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,}(?:" + "|".join(COMPANY_NAME_SUFFIXES) + r")",
    re.IGNORECASE
)


def _contains_stock_code(value: Any) -> bool:
    """
    检查值中是否包含股票代码(如 000001.SZ、300308.SZ)。
    支持字符串、列表、字典递归检测。
    """
    if isinstance(value, str):
        return bool(STOCK_CODE_PATTERN.search(value))
    if isinstance(value, (list, tuple)):
        return any(_contains_stock_code(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_stock_code(v) for v in value.values())
    return False


def _contains_company_name(value: Any) -> bool:
    """
    检查值中是否包含公司名称后缀(如 "贵州茅台"、"宁德时代")。
    仅对字符串值检测,避免误报数字型字段。
    """
    if isinstance(value, str):
        return bool(COMPANY_SUFFIX_PATTERN.search(value))
    if isinstance(value, (list, tuple)):
        return any(_contains_company_name(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_company_name(v) for v in value.values())
    return False


def _is_blocked_field(field_name: str) -> bool:
    """
    判断字段名是否属于 System A 黑名单。
    精确匹配 + 前缀匹配双重检测。
    """
    # 精确匹配黑名单
    if field_name in SYSTEM_A_BLOCKED_FIELDS:
        return True
    # 前缀匹配
    if field_name.startswith(BLOCKED_PREFIXES):
        return True
    return False


def _is_allowed_field(field_name: str) -> bool:
    """
    判断字段名是否属于 System A 白名单。
    精确匹配 + 前缀匹配双重检测。
    """
    if field_name in SYSTEM_A_ALLOWED_FIELDS:
        return True
    if field_name.startswith(ALLOWED_PREFIX):
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# 核心函数:validate_system_a_input
# ═══════════════════════════════════════════════════════════════

def validate_system_a_input(data_dict: Dict[str, Any]) -> bool:
    """
    校验输入数据字典是否符合 System A 数据防火墙规则。

    检查项:
    1. 所有字段名必须在白名单内(industry_ 前缀或精确匹配)
    2. 任何字段名不得命中黑名单(company_ / stock_ / firm_ / corp_ / enterprise_ 前缀)
    3. 字段值中不得嵌入股票代码(如 000001.SZ)
    4. 字段值中不得嵌入公司名称(如 "贵州茅台"、"宁德时代")

    Args:
        data_dict: 待校验的数据字典

    Returns:
        True - 数据干净,可通过防火墙

    Raises:
        DataFirewallViolation: 发现违规字段或嵌入公司特定信息
    """
    if not isinstance(data_dict, dict):
        raise DataFirewallViolation(
            f"输入必须是字典类型,收到 {type(data_dict).__name__}",
            violations=["类型错误"]
        )

    violations: List[str] = []

    for field_name, value in data_dict.items():
        # ── 检查 1:黑名单命中 ──
        if _is_blocked_field(field_name):
            violations.append(
                f"字段名违规:'{field_name}' 命中黑名单(公司特定字段禁止进入 System A)"
            )
            continue

        # ── 检查 2:白名单外字段 ──
        if not _is_allowed_field(field_name):
            violations.append(
                f"字段名未授权:'{field_name}' 不在 System A 白名单中(必须以 'industry_' 开头)"
            )

        # ── 检查 3:字段值嵌入股票代码 ──
        if _contains_stock_code(value):
            violations.append(
                f"值违规:字段 '{field_name}' 的值中检测到股票代码(如 000001.SZ),"
                f"System A 禁止混入公司标识"
            )

        # ── 检查 4:字段值嵌入公司名称 ──
        if _contains_company_name(value):
            violations.append(
                f"值违规:字段 '{field_name}' 的值中检测到公司名称(如 '贵州茅台'),"
                f"System A 禁止混入公司标识"
            )

    if violations:
        error_msg = (
            f"🚫 System A 数据防火墙拦截:发现 {len(violations)} 处违规\n"
            + "\n".join(f"  • {v}" for v in violations)
            + "\n\nSystem A 仅允许行业级数据(industry_ 前缀字段)。"
            "公司特定数据请通过 System B 通道输入。"
        )
        raise DataFirewallViolation(error_msg, violations=violations)

    logger.info("✅ System A 数据防火墙校验通过:%d 个字段,全部符合行业级数据规范", len(data_dict))
    return True


# ═══════════════════════════════════════════════════════════════
# 核心函数:sanitize_for_system_a
# ═══════════════════════════════════════════════════════════════

def sanitize_for_system_a(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    对混合数据(可能同时包含行业级和公司级字段)进行清洗,
    仅保留 System A 允许的行业级字段。

    处理逻辑:
    1. 遍历所有字段,仅保留白名单内字段
    2. 对保留的字段值进行启发式检测(股票代码、公司名称)
    3. 若值中嵌入公司标识,移除该字段
    4. 记录清洗日志,确保透明可追溯

    Args:
        raw_data: 原始混合数据字典

    Returns:
        清洗后的纯行业级数据字典
    """
    if not isinstance(raw_data, dict):
        logger.warning("清洗输入不是字典,返回空字典")
        return {}

    clean_data: Dict[str, Any] = {}
    removed_fields: List[str] = []

    for field_name, value in raw_data.items():
        # ── 步骤 1:白名单过滤 ──
        if not _is_allowed_field(field_name):
            removed_fields.append(
                f"'{field_name}'(不在白名单,属于公司级或未知字段)"
            )
            continue

        # ── 步骤 2:黑名单二次过滤 ──
        if _is_blocked_field(field_name):
            removed_fields.append(
                f"'{field_name}'(命中黑名单,公司特定字段)"
            )
            continue

        # ── 步骤 3:值级启发式检测 ──
        if _contains_stock_code(value):
            removed_fields.append(
                f"'{field_name}'(值中嵌入股票代码,如 000001.SZ)"
            )
            continue

        if _contains_company_name(value):
            removed_fields.append(
                f"'{field_name}'(值中嵌入公司名称,如 '贵州茅台')"
            )
            continue

        # 通过所有检查,保留
        clean_data[field_name] = value

    # ── 日志记录 ──
    if removed_fields:
        logger.info(
            "🧹 System A 数据清洗完成:保留 %d 个字段,移除 %d 个字段\n"
            "  移除详情:%s",
            len(clean_data),
            len(removed_fields),
            "; ".join(removed_fields)
        )
    else:
        logger.info(
            "✅ System A 数据清洗完成:全部 %d 个字段通过,无需移除",
            len(clean_data)
        )

    return clean_data


# ═══════════════════════════════════════════════════════════════
# 演示 / 测试用例
# ═══════════════════════════════════════════════════════════════

def _run_demo():
    """运行全部测试用例,验证数据防火墙功能。"""
    print("=" * 60)
    print("V4.4 数据防火墙代码层 - 测试套件")
    print("=" * 60)

    passed = 0
    failed = 0

    # ── 测试 1:干净的行业数据应通过 ──
    print("\n【测试 1】干净的行业数据 - 应通过")
    clean_data = {
        "industry_order_growth": 25.0,
        "industry_capacity_util": 85.0,
        "industry_inventory_days": 45,
        "industry_price_trend": 10.0,
        "industry_policy_score": 75,
        "industry_lifecycle_stage": "成长期加速段",
        "industry_penetration_rate": 35.0,
        "industry_competition_score": 60,
    }
    try:
        validate_system_a_input(clean_data)
        print("  ✅ 通过:干净行业数据顺利通过防火墙")
        passed += 1
    except DataFirewallViolation as e:
        print(f"  ❌ 失败:{e}")
        failed += 1

    # ── 测试 2:公司特定数据应被拦截 ──
    print("\n【测试 2】公司特定数据 - 应被拦截")
    company_data = {
        "industry_order_growth": 25.0,
        "company_order_growth": 8.0,      # ❌ 黑名单
        "company_cash_flow": -12.0,       # ❌ 黑名单
        "company_market_share": 15.0,    # ❌ 黑名单
        "company_valuation_pe": 85.0,    # ❌ 黑名单
    }
    try:
        validate_system_a_input(company_data)
        print("  ❌ 失败:公司数据未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确拦截公司特定数据")
        print(f"     发现 {len(e.violations)} 处违规")
        for v in e.violations[:3]:
            print(f"     • {v[:80]}...")
        passed += 1

    # ── 测试 3:混合数据应被清洗 ──
    print("\n【测试 3】混合数据 - 应被清洗为纯行业数据")
    mixed_data = {
        "industry_order_growth": 25.0,
        "industry_capacity_util": 85.0,
        "industry_price_trend": 10.0,
        "company_revenue_growth": 30.0,   # 应被移除
        "company_mgmt_score": 70,        # 应被移除
        "stock_technical_rsi": 65,        # 应被移除
    }
    sanitized = sanitize_for_system_a(mixed_data)
    removed_count = len(mixed_data) - len(sanitized)
    if removed_count == 3 and len(sanitized) == 3:
        print(f"  ✅ 通过:正确移除 {removed_count} 个公司级字段,保留 {len(sanitized)} 个行业级字段")
        passed += 1
    else:
        print(f"  ❌ 失败:应移除 3 个,实际移除 {removed_count} 个;应保留 3 个,实际保留 {len(sanitized)} 个")
        failed += 1

    # ── 测试 4:字段值嵌入股票代码应被拦截 ──
    print("\n【测试 4】字段值嵌入股票代码 - 应被拦截")
    embedded_stock = {
        "industry_order_growth": "光模块行业订单增速 25%(参考 300308.SZ)",  # ❌ 嵌入股票代码
        "industry_capacity_util": 85.0,
    }
    try:
        validate_system_a_input(embedded_stock)
        print("  ❌ 失败:嵌入股票代码未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确检测字段值中的股票代码")
        passed += 1

    # ── 测试 5:字段值嵌入公司名称应被拦截 ──
    print("\n【测试 5】字段值嵌入公司名称 - 应被拦截")
    embedded_company = {
        "industry_order_growth": "某公司订单增速仅 8%,低于行业平均",  # ❌ 嵌入公司名
        "industry_capacity_util": 85.0,
    }
    try:
        validate_system_a_input(embedded_company)
        print("  ❌ 失败:嵌入公司名称未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确检测字段值中的公司名称")
        passed += 1

    # ── 测试 6:清洗函数应能处理值级嵌入 ──
    print("\n【测试 6】清洗函数处理值级嵌入 - 应移除含嵌入的字段")
    mixed_embedded = {
        "industry_order_growth": 25.0,
        "industry_price_trend": "参考 000001.SZ 涨幅 10%",  # 应被移除
        "industry_policy_score": "某光模块公司受益政策",        # 应被移除
        "industry_capacity_util": 85.0,
    }
    sanitized_embedded = sanitize_for_system_a(mixed_embedded)
    if "industry_price_trend" not in sanitized_embedded and "industry_policy_score" not in sanitized_embedded:
        print(f"  ✅ 通过:正确移除含嵌入标识的字段,保留 {len(sanitized_embedded)} 个干净字段")
        passed += 1
    else:
        print(f"  ❌ 失败:含嵌入标识的字段未被移除")
        failed += 1

    # ── 测试 7:未知前缀字段应被拒绝 ──
    print("\n【测试 7】未知前缀字段 - 应被拒绝")
    unknown_prefix = {
        "industry_order_growth": 25.0,
        "sector_revenue": 100.0,  # ❌ 既非 industry_ 也非 company_,但不在白名单
    }
    try:
        validate_system_a_input(unknown_prefix)
        print("  ❌ 失败:未知前缀字段未被拦截")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确拦截非白名单字段")
        passed += 1

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print(f"测试完成:通过 {passed} / 失败 {failed} / 总计 {passed + failed}")
    print("=" * 60)
    return failed == 0

# ═══════════════════════════════════════════════════════════════
# Part 3 - 五态拐点模型 (v44-inflection-states)
# ═══════════════════════════════════════════════════════════════

class InflectionState(Enum):
    """五态拐点枚举"""
    PRE = "Pre-inflection"           # 拐点前/潜伏
    EARLY = "Early-inflection"         # 拐点初期
    CONFIRMED = "Confirmed"          # 拐点确认
    LATE = "Late"                    # 拐点晚期
    POST = "Post"                    # 拐点后/衰退


@dataclass
class StateResult:
    """状态判定结果"""
    state_name: str
    state_code: str
    color_code: str          # HTML/CSS color
    color_hex: str           # Hex color for charts
    confidence: float        # 0.0 - 1.0
    investment_advice: str
    key_monitoring_metrics: List[str]
    matched_signals: List[str]
    all_signals: Dict[str, any]


@dataclass
class Threshold:
    """单维度阈值定义"""
    name: str
    description: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    exact_match: Optional[str] = None  # 用于布尔型或离散值


# =============================================================================
# 五态阈值定义
# =============================================================================

STATE_THRESHOLDS = {
    InflectionState.PRE: {
        "cycle_score": Threshold("行业周期评分", "0-100", max_val=45),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", max_val=45),
        "policy_score": Threshold("政策催化剂评分", "0-100", max_val=50),
        "utilization": Threshold("产能利用率", "%", min_val=70, max_val=80),
        "price_yoy": Threshold("价格同比", "%", min_val=-5, max_val=0),
        "policy": Threshold("政策强度", "0-100", max_val=50),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="none"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", max_val=10),
    },
    InflectionState.EARLY: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=40, max_val=60),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=35, max_val=60),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=45, max_val=70),
        "utilization": Threshold("产能利用率", "%", min_val=80, max_val=85),
        "price_yoy": Threshold("价格同比", "%", min_val=0, max_val=5),
        "policy": Threshold("政策强度", "0-100", min_val=50, max_val=65),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="planned"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=5, max_val=20),
    },
    InflectionState.CONFIRMED: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=55, max_val=80),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=55, max_val=80),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=60, max_val=85),
        "utilization": Threshold("产能利用率", "%", min_val=85, max_val=95),
        "price_yoy": Threshold("价格同比", "%", min_val=5, max_val=15),
        "policy": Threshold("政策强度", "0-100", min_val=65, max_val=80),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="underway"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=15, max_val=40),
    },
    InflectionState.LATE: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=75),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=70),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=75),
        "utilization": Threshold("产能利用率", "%", min_val=95),
        "price_yoy": Threshold("价格同比", "%", min_val=15, max_val=25),
        "price_mom_trend": Threshold("价格环比趋势", "放缓信号", exact_match="slowing"),
        "policy": Threshold("政策强度", "0-100", min_val=80),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="aggressive"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=20, max_val=50),
    },
    InflectionState.POST: {
        "cycle_score": Threshold("行业周期评分", "0-100", max_val=50),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", max_val=45),
        "policy_score": Threshold("政策催化剂评分", "0-100", max_val=55),
        "utilization": Threshold("产能利用率", "%", max_val=60),
        "price_yoy": Threshold("价格同比", "%", min_val=25),
        "price_mom_trend": Threshold("价格环比趋势", "转负或见顶", exact_match="declining"),
        "policy": Threshold("政策强度", "0-100", max_val=60),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="oversupply_risk"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", max_val=10),
    },
}


STATE_META = {
    InflectionState.PRE: {
        "name": "拐点前/潜伏",
        "color_code": "#9CA3AF",    # gray-400
        "color_hex": "#9CA3AF",
        "investment_advice": (
            "行业处于底部区域,产能利用率偏低,价格同比仍在负区间。"
            "政策尚未密集释放。此时适合深度研究、建立观察池,"
            "跟踪左侧信号,等待更明确的拐点确认。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否突破80%",
            "价格同比是否由负转正",
            "政策文件密度是否增加",
            "行业龙头订单是否回暖",
        ],
    },
    InflectionState.EARLY: {
        "name": "拐点初期",
        "color_code": "#60A5FA",    # blue-400
        "color_hex": "#60A5FA",
        "investment_advice": (
            "行业景气度开始回升,产能利用率站上80%,价格同比由负转正。"
            "政策进入预热期。此时是左侧信号窗口,"
            "选择行业内护城河最深的龙头,关注基本面验证。"
        ),
        "key_monitoring_metrics": [
            "产能利用率能否持续突破85%",
            "价格环比是否连续2月为正",
            "订单 backlog 增速是否>15%",
            "扩产计划是否实质性启动",
        ],
    },
    InflectionState.CONFIRMED: {
        "name": "拐点确认",
        "color_code": "#4ADE80",    # green-400
        "color_hex": "#4ADE80",
        "investment_advice": (
            "行业进入高景气通道,产能利用率85-95%,价格同比+5~15%,"
            "政策密集释放期。右侧信号窗口,"
            "优先布局产能紧缺的结构性龙头,关注扩产良率。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否逼近95%瓶颈",
            "价格环比是否出现加速信号",
            "扩产良率爬坡进度",
            "新增产能释放节奏 vs 需求增速",
        ],
    },
    InflectionState.LATE: {
        "name": "拐点晚期",
        "color_code": "#FBBF24",    # amber-400
        "color_hex": "#FBBF24",
        "investment_advice": (
            "行业高度景气但边际动能减弱,产能利用率>95%且扩产激进,"
            "价格同比仍高但环比放缓。进入观察阶段,"
            "警惕过热信号,关注新增产能释放后的供需平衡。"
        ),
        "key_monitoring_metrics": [
            "价格环比增速是否连续3月放缓",
            "扩产产能释放后利用率是否回落",
            "行业估值是否进入历史前20%分位",
            "新进入者数量是否激增",
        ],
    },
    InflectionState.POST: {
        "name": "拐点后/衰退",
        "color_code": "#F87171",    # red-400
        "color_hex": "#F87171",
        "investment_advice": (
            "行业景气见顶回落,产能利用率下降,价格同比虽仍高但环比转负,"
            "政策退坡。景气下行信号,"
            "关注基本面恶化条件,转向休眠观察。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否跌破85%",
            "价格环比是否连续2月为负",
            "库存天数是否快速攀升",
            "龙头订单增速是否转负",
        ],
    },
}


# =============================================================================
# 核心判定函数
# =============================================================================

def check_threshold(value: any, threshold: Threshold) -> bool:
    """检查单值是否满足阈值"""
    if threshold.exact_match is not None:
        return str(value).lower() == threshold.exact_match.lower()

    if value is None:
        return False

    try:
        val = float(value)
    except (ValueError, TypeError):
        return False

    if threshold.min_val is not None and val < threshold.min_val:
        return False
    if threshold.max_val is not None and val > threshold.max_val:
        return False
    return True


def count_matching_signals(signals: Dict[str, any], state: InflectionState) -> Tuple[int, List[str]]:
    """
    计算给定信号集满足某状态阈值的信号数量
    返回: (匹配数, 匹配信号名列表)
    """
    thresholds = STATE_THRESHOLDS[state]
    matched = []

    for key, threshold in thresholds.items():
        if key in signals and check_threshold(signals[key], threshold):
            matched.append(f"{key}={signals[key]} (满足 {threshold.name} 阈值)")

    return len(matched), matched


def determine_inflection_state(
    cycle_score: float = 0,
    supply_demand_score: float = 0,
    policy_score: float = 0,
    supply_signals: Dict[str, any] = None,
    policy_signals: Dict[str, any] = None,
    cycle_signals: Dict[str, any] = None,
    min_signals_required: int = 2,
    real_signals: Dict[str, Any] = None,
) -> StateResult:
    """
    判定产业拐点状态 - V4.5 多信号匹配, 优先 real_signals 路径,不依赖单一合成指数

    参数:
        cycle_score: 行业周期评分 0-100
        supply_demand_score: 供需拐点评分 0-100
        policy_score: 政策催化剂评分 0-100
        supply_signals: 供需信号 dict
        policy_signals: 政策信号 dict
        cycle_signals: 周期信号 dict
        min_signals_required: 状态切换所需最少同时满足信号数

    返回:
        StateResult: 包含状态名、颜色、投资建议、监测指标、匹配信号详情
    """
    # V4.5 优先：如果提供了 real_signals，走真实数据路径
    if real_signals is not None and isinstance(real_signals, dict) and len(real_signals) > 0:
        result, _ = determine_inflection_state_v45(real_signals, min_signals_required)
        return result

    supply_signals = supply_signals or {}
    policy_signals = policy_signals or {}
    cycle_signals = cycle_signals or {}
    # 合并所有信号(含三维评分作为独立信号)
    all_signals = {
        "cycle_score": cycle_score,
        "supply_demand_score": supply_demand_score,
        "policy_score": policy_score,
        **supply_signals,
        **policy_signals,
        **cycle_signals,
    }

    # 按优先级从高到低评估各状态(POST > LATE > CONFIRMED > EARLY > PRE)
    state_priority = [
        InflectionState.POST,
        InflectionState.LATE,
        InflectionState.CONFIRMED,
        InflectionState.EARLY,
        InflectionState.PRE,
    ]

    best_state = InflectionState.PRE
    best_confidence = 0.0
    best_matched = []

    for state in state_priority:
        matched_count, matched_details = count_matching_signals(all_signals, state)
        total_signals = len(STATE_THRESHOLDS[state])

        # V4.5: 不再要求单一合成指数区间,仅要求匹配信号数>=阈值
        if matched_count >= min_signals_required:
            confidence = matched_count / total_signals if total_signals > 0 else 0.0
            if confidence > best_confidence:
                best_state = state
                best_confidence = confidence
                best_matched = matched_details

    meta = STATE_META[best_state]

    return StateResult(
        state_name=meta["name"],
        state_code=best_state.value,
        color_code=meta["color_code"],
        color_hex=meta["color_hex"],
        confidence=round(best_confidence, 2),
        investment_advice=meta["investment_advice"],
        key_monitoring_metrics=meta["key_monitoring_metrics"],
        matched_signals=best_matched,
        all_signals=all_signals,
    )


# =============================================================================
# 真实产业数据 Demo Cases
# =============================================================================

def demo_abf_substrate_is():
    """
    ABF 载板 Demo — 基于 2025-2026 年真实产业数据
    """
    print("\n" + "=" * 70)
    print("【Demo Case 1】ABF 载板 — 三阶段演进")
    print("=" * 70)

    # Phase 1: 2025Q1 — 拐点初期
    phase1 = determine_inflection_state(
        cycle_score=48,
        supply_demand_score=46,
        policy_score=58,
        supply_signals={
            "utilization": 76,
            "price_yoy": -2,
            "price_mom_trend": "stable",
            "capacity_expansion": "planned",
            "order_backlog_growth": 12,
        },
        policy_signals={"policy": 58},
        cycle_signals={},
    )
    print(f"\n[Phase 1: 2025Q1]")
    print(f"  周期: 48 | 供需: 46 | 政策: 58 | 产能利用率: 76% | 价格同比: -2%")
    print(f"  → 判定结果: {phase1.state_name} ({phase1.state_code})")
    print(f"  → 置信度: {phase1.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase1.matched_signals])}")
    print(f"  → 投资建议: {phase1.investment_advice[:60]}...")

    # Phase 2: 2025Q3 — 拐点确认
    phase2 = determine_inflection_state(
        cycle_score=68,
        supply_demand_score=72,
        policy_score=72,
        supply_signals={
            "utilization": 88,
            "price_yoy": 8,
            "price_mom_trend": "accelerating",
            "capacity_expansion": "underway",
            "order_backlog_growth": 28,
        },
        policy_signals={"policy": 72},
        cycle_signals={},
    )
    print(f"\n[Phase 2: 2025Q3]")
    print(f"  周期: 68 | 供需: 72 | 政策: 72 | 产能利用率: 88% | 价格同比: +8%")
    print(f"  → 判定结果: {phase2.state_name} ({phase2.state_code})")
    print(f"  → 置信度: {phase2.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase2.matched_signals])}")
    print(f"  → 投资建议: {phase2.investment_advice[:60]}...")

    # Phase 3: 2026Q1 — 拐点晚期
    phase3 = determine_inflection_state(
        cycle_score=82,
        supply_demand_score=85,
        policy_score=85,
        supply_signals={
            "utilization": 96,
            "price_yoy": 18,
            "price_mom_trend": "slowing",
            "capacity_expansion": "aggressive",
            "order_backlog_growth": 35,
        },
        policy_signals={"policy": 85},
        cycle_signals={},
    )
    print(f"\n[Phase 3: 2026Q1]")
    print(f"  周期: 82 | 供需: 85 | 政策: 85 | 产能利用率: 96% | 价格同比: +18%（环比放缓）")
    print(f"  → 判定结果: {phase3.state_name} ({phase3.state_code})")
    print(f"  → 置信度: {phase3.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase3.matched_signals])}")
    print(f"  → 投资建议: {phase3.investment_advice[:60]}...")

    return phase1, phase2, phase3


def demo_optical_module_is():
    """
    光模块 Demo — 基于 2025-2026 年 AI 算力产业链数据
    """
    print("\n" + "=" * 70)
    print("【Demo Case 2】光模块（AI 算力链）— 三阶段演进")
    print("=" * 70)

    # Phase 1: 2025Q1 — 拐点初期→确认过渡
    phase1 = determine_inflection_state(
        cycle_score=62,
        supply_demand_score=65,
        policy_score=68,
        supply_signals={
            "utilization": 82,
            "price_yoy": 3,
            "price_mom_trend": "accelerating",
            "capacity_expansion": "underway",
            "order_backlog_growth": 22,
        },
        policy_signals={"policy": 68},
        cycle_signals={},
    )
    print(f"\n[Phase 1: 2025Q1]")
    print(f"  周期: 62 | 供需: 65 | 政策: 68 | 产能利用率: 82% | 800G价格同比: +3%")
    print(f"  → 判定结果: {phase1.state_name} ({phase1.state_code})")
    print(f"  → 置信度: {phase1.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase1.matched_signals])}")
    print(f"  → 投资建议: {phase1.investment_advice[:60]}...")

    # Phase 2: 2025Q3 — 拐点确认
    phase2 = determine_inflection_state(
        cycle_score=76,
        supply_demand_score=78,
        policy_score=78,
        supply_signals={
            "utilization": 92,
            "price_yoy": 12,
            "price_mom_trend": "stable",
            "capacity_expansion": "aggressive",
            "order_backlog_growth": 38,
        },
        policy_signals={"policy": 78},
        cycle_signals={},
    )
    print(f"\n[Phase 2: 2025Q3]")
    print(f"  周期: 76 | 供需: 78 | 政策: 78 | 产能利用率: 92% | 1.6T价格同比: +12%")
    print(f"  → 判定结果: {phase2.state_name} ({phase2.state_code})")
    print(f"  → 置信度: {phase2.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase2.matched_signals])}")
    print(f"  → 投资建议: {phase2.investment_advice[:60]}...")

    # Phase 3: 2026Q1 — 拐点晚期信号
    phase3 = determine_inflection_state(
        cycle_score=83,
        supply_demand_score=88,
        policy_score=82,
        supply_signals={
            "utilization": 98,
            "price_yoy": 22,
            "price_mom_trend": "slowing",
            "capacity_expansion": "aggressive",
            "order_backlog_growth": 42,
        },
        policy_signals={"policy": 82},
        cycle_signals={},
    )
    print(f"\n[Phase 3: 2026Q1]")
    print(f"  周期: 83 | 供需: 88 | 政策: 82 | 产能利用率: 98% | 价格同比: +22%（环比放缓）")
    print(f"  → 判定结果: {phase3.state_name} ({phase3.state_code})")
    print(f"  → 置信度: {phase3.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in phase3.matched_signals])}")
    print(f"  → 投资建议: {phase3.investment_advice[:60]}...")

    return phase1, phase2, phase3


def demo_pre_inflection():
    """演示 Pre-inflection 状态 — 以 2024 年底的光伏玻璃为例"""
    print("\n" + "=" * 70)
    print("【Demo Case 3】Pre-inflection 验证 — 2024年底光伏玻璃")
    print("=" * 70)

    result = determine_inflection_state(
        cycle_score=35,
        supply_demand_score=32,
        policy_score=42,
        supply_signals={
            "utilization": 72,
            "price_yoy": -4,
            "price_mom_trend": "stable",
            "capacity_expansion": "none",
            "order_backlog_growth": 5,
        },
        policy_signals={"policy": 42},
        cycle_signals={},
    )
    print(f"\n  周期: 35 | 供需: 32 | 政策: 42 | 产能利用率: 72% | 价格同比: -4%")
    print(f"  → 判定结果: {result.state_name} ({result.state_code})")
    print(f"  → 置信度: {result.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in result.matched_signals])}")
    print(f"  → 颜色标记: {result.color_hex}")
    print(f"  → 投资建议: {result.investment_advice}")

    return result


def demo_post_inflection():
    """演示 Post-inflection 状态 — 以 2023 年的锂盐为例"""
    print("\n" + "=" * 70)
    print("【Demo Case 4】Post-inflection 验证 — 2023年锂盐见顶回落")
    print("=" * 70)

    result = determine_inflection_state(
        cycle_score=45,
        supply_demand_score=38,
        policy_score=45,
        supply_signals={
            "utilization": 78,
            "price_yoy": 35,
            "price_mom_trend": "declining",
            "capacity_expansion": "oversupply_risk",
            "order_backlog_growth": 3,
        },
        policy_signals={"policy": 45},
        cycle_signals={},
    )
    print(f"\n  周期: 45 | 供需: 38 | 政策: 45 | 产能利用率: 78%（下降） | 价格同比: +35%（环比暴跌）")
    print(f"  → 判定结果: {result.state_name} ({result.state_code})")
    print(f"  → 置信度: {result.confidence}")
    print(f"  → 匹配信号: {', '.join([s.split('=')[0] for s in result.matched_signals])}")
    print(f"  → 颜色标记: {result.color_hex}")
    print(f"  → 投资建议: {result.investment_advice}")

    return result


def print_threshold_table():
    """打印五态阈值对照表（V4.5 三维评分版）"""
    print("\n" + "=" * 70)
    print("【附录】五态拐点定量阈值总表（V4.5 三维独立评分版）")
    print("=" * 70)

    headers = ["状态", "周期评分", "供需评分", "政策评分", "产能利用率", "价格同比", "政策强度", "扩产计划"]
    print(f"\n{' | '.join(headers)}")
    print(" | ".join(["---"] * len(headers)))

    rows = [
        ["拐点前/潜伏", "< 45", "< 45", "< 50", "70-80%", "-5 ~ 0%", "< 50", "无"],
        ["拐点初期", "40-60", "35-60", "45-70", "80-85%", "0 ~ +5%", "50-65", "规划中"],
        ["拐点确认", "55-80", "55-80", "60-85", "85-95%", "+5 ~ +15%", "65-80", "进行中"],
        ["拐点晚期", "75+", "70+", "75+", "> 95%", "+15 ~ +25%", "> 80", "激进"],
        ["拐点后/衰退", "< 50", "< 45", "< 55", "< 60%", "> +25%", "< 60", "过剩风险"],
    ]

    for row in rows:
        print(f"{' | '.join(row)}")

    print("\n> 注：状态切换需同时满足 2+ 信号阈值，三维评分各自独立参与匹配")


# =============================================================================
# 主入口
# =============================================================================

# ═══════════════════════════════════════════════════════════════
# Part 4 - 评分公式 (v43-scoring-formula)
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# V4.5 重写：五态拐点判定 — 基于真实信号匹配，无算法评分
# ═══════════════════════════════════════════════════════════════

def _safe_float(val):
    if val is None: return None
    try: return float(val)
    except (ValueError, TypeError): return None

def determine_inflection_state_v45(real_signals, min_signals_required=2):
    rev_growth = _safe_float(real_signals.get("revenue_growth"))
    gm = _safe_float(real_signals.get("gross_margin"))
    backlog = _safe_float(real_signals.get("order_backlog"))
    util = _safe_float(real_signals.get("capacity_utilization"))
    price_yoy = _safe_float(real_signals.get("price_yoy"))
    inv_days = _safe_float(real_signals.get("inventory_days"))
    capex = str(real_signals.get("capex_plan", "")).lower()

    def _match(tag):
        m = []
        if tag == "pre":
            if rev_growth is not None and rev_growth < 10: m.append(f"营收增速 {rev_growth:.1f}% < 10%")
            if util is not None and util < 80: m.append(f"产能利用率 {util:.1f}% < 80%")
            if price_yoy is not None and price_yoy < 0: m.append(f"价格同比 {price_yoy:.1f}% < 0")
            if capex in ("none", ""): m.append("扩产计划：无")
            if backlog is not None and backlog < 20: m.append(f"订单backlog {backlog:.1f} 低位")
        elif tag == "early":
            if rev_growth is not None and 5 <= rev_growth < 20: m.append(f"营收增速 {rev_growth:.1f}% 温和复苏")
            if util is not None and 80 <= util < 85: m.append(f"产能利用率 {util:.1f}% 回升中")
            if price_yoy is not None and 0 <= price_yoy < 5: m.append(f"价格同比 {price_yoy:.1f}% 止跌")
            if capex in ("planned", "规划中"): m.append("扩产：已规划")
            if backlog is not None and 20 <= backlog < 50: m.append(f"订单backlog {backlog:.1f} 改善")
            if gm is not None and gm < 0: m.append(f"毛利率 {gm:.1f}% 仍为负")
        elif tag == "confirmed":
            if rev_growth is not None and rev_growth >= 20: m.append(f"营收增速 {rev_growth:.1f}% >= 20% 加速")
            if util is not None and util >= 85: m.append(f"产能利用率 {util:.1f}% >= 85% 紧张")
            if price_yoy is not None and price_yoy >= 5: m.append(f"价格同比 {price_yoy:.1f}% >= 5% 涨价")
            if capex in ("underway", "进行中", "aggressive", "激进"): m.append("扩产：已启动")
            if backlog is not None and backlog >= 50: m.append(f"订单backlog {backlog:.1f} 高位")
            if gm is not None and gm >= 0: m.append(f"毛利率 {gm:.1f}% 修复至非负")
        elif tag == "late":
            if util is not None and util >= 95: m.append(f"产能利用率 {util:.1f}% >= 95% 瓶颈")
            if price_yoy is not None and price_yoy >= 15: m.append(f"价格同比 {price_yoy:.1f}% >= 15% 高位")
            if inv_days is not None and inv_days > 60: m.append(f"库存天数 {inv_days:.1f} > 60 补库过激")
            if capex in ("aggressive", "激进"): m.append("扩产：激进")
            mom = str(real_signals.get("price_mom_trend", "")).lower()
            if mom in ("slowing", "declining", "放缓", "下滑"): m.append("价格环比：放缓")
        elif tag == "post":
            if rev_growth is not None and rev_growth < 0: m.append(f"营收增速 {rev_growth:.1f}% < 0 收缩")
            if util is not None and util < 75: m.append(f"产能利用率 {util:.1f}% < 75% 回落")
            if price_yoy is not None and price_yoy < -5: m.append(f"价格同比 {price_yoy:.1f}% < -5% 暴跌")
            if backlog is not None and backlog < 10: m.append(f"订单backlog {backlog:.1f} 枯竭")
            if inv_days is not None and inv_days > 80: m.append(f"库存天数 {inv_days:.1f} > 80 积压")
        return len(m) >= min_signals_required, m

    checks = [("post", InflectionState.POST), ("late", InflectionState.LATE),
              ("confirmed", InflectionState.CONFIRMED), ("early", InflectionState.EARLY),
              ("pre", InflectionState.PRE)]
    best_state, best_matched, best_conf = InflectionState.PRE, [], 0.0
    for tag, state in checks:
        ok, matched = _match(tag)
        if ok:
            conf = min(1.0, len(matched)/6)
            if conf >= best_conf:
                best_state, best_conf, best_matched = state, conf, matched
    meta = STATE_META[best_state]
    logic = "\\n".join([f"基于 {len(best_matched)} 个真实数据信号匹配："] + [f"  • {x}" for x in best_matched] if best_matched else ["信号不足，回退至「拐点前」。建议补充真实指标。"])
    return StateResult(
        state_name=meta["name"], state_code=best_state.value,
        color_code=meta["color_code"], color_hex=meta["color_hex"],
        confidence=round(best_conf, 2),
        investment_advice=meta["investment_advice"],
        key_monitoring_metrics=meta["key_monitoring_metrics"],
        matched_signals=best_matched, all_signals=real_signals,
    ), logic


# ============================================================================
# System B: Micro 层 - 个股层面调整(V4.3 新增)
# ============================================================================


def grade_from_index(index: float = 0) -> str:
    """【V4.5 禁用】五级等级映射。仅返回占位字符串。"""
    logger.warning("[V4.5] grade_from_index 已禁用")
    return "已禁用(V4.5)"


# ============================================================================
# 完整评分流程示例(中际旭创案例)
# ============================================================================

def demo_zhongji_xuchong():
    """【V4.5 禁用】评分演示已删除。"""
    print("[V4.5] 评分演示已删除")
    return {"status": "已删除(V4.5)"}


# ═══════════════════════════════════════════════════════════════
# 六、产业链生命周期判定（V4.5 恢复 V4.0 标准）
# ═══════════════════════════════════════════════════════════════

class LifecyclePhase(Enum):
    """产业链生命周期四阶段"""
    GROWTH = "成长期"
    MATURE = "成熟期"
    DECLINE = "衰退期"
    EBB = "退潮期"


def determine_lifecycle_phase(
    penetration_rate: float,
    revenue_growth: float,
    industry_concentration_hhi: float = None,
    price_trend: str = "stable",
) -> Dict[str, any]:
    """
    判定产业链生命周期阶段 — 基于渗透率阈值（V4.0 标准）

    渗透率阈值标准：
    - 成长期: 渗透率 < 15% 或 15-30%且增速>25%
    - 成熟期: 渗透率 30-60% 且增速稳定
    - 衰退期: 渗透率 > 60% 但仍在增长
    - 退潮期: 渗透率 > 60% 且增速<5%或下滑

    辅助信号：
    - 营收增速: growth >20%, mature 5-20%, decline 0-5%, ebb <0%
    - 价格趋势: 成长期涨价/稳价, 退潮期持续跌价
    - 行业集中度(HHI): 成熟期集中度上升, 退潮期集中度下降(洗牌)

    Args:
        penetration_rate: 渗透率 % (0-100)
        revenue_growth: 行业营收增速 %
        industry_concentration_hhi: HHI指数 (可选, 0-10000)
        price_trend: "rising" | "stable" | "slowing" | "declining"

    Returns:
        Dict: {phase, phase_name, confidence, description, key_signals}
    """
    phase = None
    signals = []
    confidence = 0.80  # 初始置信度

    # 渗透率主判定
    if penetration_rate < 15.0:
        phase = LifecyclePhase.GROWTH
        signals.append(f"渗透率 {penetration_rate:.1f}% < 15% → 成长期")
    elif penetration_rate < 30.0 and revenue_growth > 25.0:
        phase = LifecyclePhase.GROWTH
        signals.append(f"渗透率 {penetration_rate:.1f}% 处于15-30%但增速 {revenue_growth:.1f}% > 25% → 成长期")
    elif penetration_rate < 60.0 and revenue_growth >= 5.0:
        phase = LifecyclePhase.MATURE
        signals.append(f"渗透率 {penetration_rate:.1f}% 处于30-60%且增速 {revenue_growth:.1f}% >= 5% → 成熟期")
    elif penetration_rate >= 60.0 and revenue_growth >= 0.0:
        phase = LifecyclePhase.DECLINE
        signals.append(f"渗透率 {penetration_rate:.1f}% >= 60% 且增速 {revenue_growth:.1f}% >= 0% → 衰退期")
    else:
        phase = LifecyclePhase.EBB
        signals.append(f"渗透率 {penetration_rate:.1f}% >= 60% 且增速 {revenue_growth:.1f}% < 0% → 退潮期")

    # 营收增速交叉验证
    if revenue_growth > 20.0 and phase != LifecyclePhase.GROWTH:
        confidence -= 0.10
        signals.append(f"营收增速 {revenue_growth:.1f}% > 20% 但主判定非成长期 → 置信度-0.10")
    elif revenue_growth < 0.0 and phase != LifecyclePhase.EBB:
        confidence -= 0.15
        signals.append(f"营收增速 {revenue_growth:.1f}% < 0% 但主判定非退潮期 → 置信度-0.15")

    # 价格趋势交叉验证
    if price_trend == "declining" and phase in [LifecyclePhase.GROWTH, LifecyclePhase.MATURE]:
        confidence -= 0.10
        signals.append("价格趋势持续下跌，与成长期/成熟期判定矛盾 → 置信度-0.10")
    elif price_trend == "rising" and phase == LifecyclePhase.EBB:
        confidence -= 0.15
        signals.append("价格趋势上涨，与退潮期判定矛盾 → 置信度-0.15")

    # HHI集中度验证（可选）
    if industry_concentration_hhi is not None:
        if industry_concentration_hhi > 2500 and phase == LifecyclePhase.MATURE:
            confidence += 0.05
            signals.append(f"HHI {industry_concentration_hhi} > 2500 高集中度 → 成熟期置信度+0.05")
        elif industry_concentration_hhi < 1500 and phase == LifecyclePhase.EBB:
            confidence += 0.05
            signals.append(f"HHI {industry_concentration_hhi} < 1500 低集中度(洗牌中) → 退潮期置信度+0.05")


    phase_meta = {
        LifecyclePhase.GROWTH: {
            "description": "渗透率快速提升阶段，技术迭代快，产能扩张激进。投资侧重成长型标的，关注技术路线和产能落地节奏。",
            "color": "#10b981",
            "investment_focus": "技术领先型成长标的",
        },
        LifecyclePhase.MATURE: {
            "description": "渗透率进入平台期，竞争格局稳定，龙头集中。投资侧重价值型龙头，关注成本控制和份额提升。",
            "color": "#3b82f6",
            "investment_focus": "成本领先型价值龙头",
        },
        LifecyclePhase.DECLINE: {
            "description": "渗透率见顶，增长放缓，结构性机会减少。谨慎参与，关注细分领域的差异化机会。",
            "color": "#f59e0b",
            "investment_focus": "细分差异化或转型标的",
        },
        LifecyclePhase.EBB: {
            "description": "渗透率过顶，行业收缩，价格战加剧。回避为主，仅关注供给侧出清后的反转机会。",
            "color": "#ef4444",
            "investment_focus": "供给侧出清后的反转机会",
        },
    }

    meta = phase_meta[phase]

    return {
        "phase": phase.value,
        "phase_name": phase.value,
        "confidence": round(confidence, 2),
        "description": meta["description"],
        "investment_focus": meta["investment_focus"],
        "color": meta["color"],
        "key_signals": signals,
        "penetration_rate": penetration_rate,
        "revenue_growth": revenue_growth,
    }


# ═══════════════════════════════════════════════════════════════
# 七、维度矛盾信号检测（V4.5 新增）
# ═══════════════════════════════════════════════════════════════

def detect_dimension_contradictions(
    cycle_score: float,
    supply_demand_score: float,
    policy_score: float,
    state_result: StateResult = None,
) -> List[Dict[str, any]]:
    """
    检测三维评分之间的逻辑矛盾信号

    矛盾规则（基于 V4.0 方法论 + 实盘验证）：
    1. 周期评分高(>75) + 供需评分低(<40): "周期上行但供需未跟" → 假繁荣风险
    2. 供需评分高(>75) + 政策评分低(<40): "供需紧但政策不支持" → 可持续性存疑
    3. 政策评分高(>75) + 周期评分低(<40): "政策强推但周期未起" → 政策驱动型/人造景气
    4. 三维度极差(>40分): "内部信号严重分化" → 产业链处于剧烈结构转换期
    5. 与五态判定矛盾: 三维均高但五态为Post → 数据异常或滞后期

    Args:
        cycle_score: 周期评分 0-100
        supply_demand_score: 供需评分 0-100
        policy_score: 政策评分 0-100
        state_result: 五态判定结果 (可选, 用于交叉验证)

    Returns:
        List[Dict]: 矛盾信号列表, 每个包含 {type, severity, description, suggestion}
    """
    contradictions = []

    # 矛盾1: 周期高 + 供需低
    if cycle_score > 75 and supply_demand_score < 40:
        contradictions.append({
            "type": "周期-供需背离",
            "severity": "high",
            "description": f"周期评分高({cycle_score:.0f})但供需评分低({supply_demand_score:.0f}) — 周期上行但供需基本面未跟上，可能存在假繁荣或资金推动型行情",
            "suggestion": "优先验证供需数据真实性，关注订单/产能利用率是否实质改善，警惕主题炒作",
        })

    # 矛盾2: 供需高 + 政策低
    if supply_demand_score > 75 and policy_score < 40:
        contradictions.append({
            "type": "供需-政策背离",
            "severity": "medium",
            "description": f"供需评分高({supply_demand_score:.0f})但政策评分低({policy_score:.0f}) — 供需紧平衡缺乏政策催化剂支撑，景气度可持续性存疑",
            "suggestion": "关注是否有政策催化剂蓄势待发，若无则缩短观察周期，等待信号收敛",
        })

    # 矛盾3: 政策高 + 周期低
    if policy_score > 75 and cycle_score < 40:
        contradictions.append({
            "type": "政策-周期背离",
            "severity": "medium",
            "description": f"政策评分高({policy_score:.0f})但周期评分低({cycle_score:.0f}) — 政策强推但行业周期未起，属于政策驱动型/人造景气",
            "suggestion": "判断政策力度能否扭转周期，强政策(如国家级战略)可博弈，弱政策(补贴退坡)则回避",
        })

    # 矛盾4: 三维度极差过大
    all_scores = [cycle_score, supply_demand_score, policy_score]
    score_range = max(all_scores) - min(all_scores)
    if score_range > 40:
        contradictions.append({
            "type": "三维度严重分化",
            "severity": "high",
            "description": f"三维度极差 {score_range:.0f} 分(>40) — 产业链处于剧烈结构转换期，各维度信号严重不一致",
            "suggestion": "产业链大概率处于范式切换期(如技术路线变更/政策转向)，建议增加观察期，等待信号收敛",
        })

    # 矛盾5: 与五态判定交叉验证
    if state_result is not None:
        avg_score = sum(all_scores) / 3
        if avg_score > 70 and state_result.state_code == "post":
            contradictions.append({
                "type": "评分-五态矛盾",
                "severity": "high",
                "description": f"三维均分 {avg_score:.0f} 较高但五态判定为「拐点后/衰退」— 数据可能存在滞后或异常，或行业处于结构性分化(部分环节衰退、部分繁荣)",
                "suggestion": "核查数据源时效性，细分产业链各环节分别评估，避免用平均数掩盖结构差异",
            })
        elif avg_score < 40 and state_result.state_code in ["confirmed", "late"]:
            contradictions.append({
                "type": "评分-五态矛盾",
                "severity": "high",
                "description": f"三维均分 {avg_score:.0f} 较低但五态判定为「拐点确认/晚期」— 信号严重矛盾，可能存在数据异常",
                "suggestion": "暂停基于该数据的决策，重新校验数据源，优先相信原始高频数据(价格/订单/产能)而非综合评分",
            })

    return contradictions


# ============================================================================
# 自测
# ============================================================================
# ═══════════════════════════════════════════════════════════════
# 统一测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 70)
    print('System A - 全模块自测')
    print('=' * 70)

    print('\n【Part 1】数据获取')
    demo_all_da()

    print('\n【Part 2】数据防火墙')
    success = _run_demo()
    if not success:
        raise SystemExit(1)

    print('\n【Part 3】五态拐点')
    demo_abf_substrate_is()
    demo_optical_module_is()
    demo_pre_inflection()
    demo_post_inflection()
    print_threshold_table()

    print('\n【Part 4】评分公式')
    result = demo_zhongji_xuchong()
    print(f"  [V4.5] 评分演示已禁用: {result}")

    print('\n【Part 5】产业链生命周期判定')
    lc1 = determine_lifecycle_phase(penetration_rate=8, revenue_growth=35, price_trend="rising")
    print(f"  光模块(渗透率8%, 增速35%) → {lc1['phase_name']}, 置信度{lc1['confidence']}")
    assert lc1['phase'] == "成长期"
    lc2 = determine_lifecycle_phase(penetration_rate=45, revenue_growth=12, price_trend="stable")
    print(f"  PCB(渗透率45%, 增速12%) → {lc2['phase_name']}, 置信度{lc2['confidence']}")
    assert lc2['phase'] == "成熟期"
    lc3 = determine_lifecycle_phase(penetration_rate=75, revenue_growth=-5, price_trend="declining")
    print(f"  传统面板(渗透率75%, 增速-5%) → {lc3['phase_name']}, 置信度{lc3['confidence']}")
    assert lc3['phase'] == "退潮期"

    print('\n【Part 6】维度矛盾信号检测')
    # 构造一个五态结果用于交叉验证
    demo_state = determine_inflection_state(
        cycle_score=80, supply_demand_score=35, policy_score=70,
        supply_signals={"utilization": 88, "price_yoy": 8, "capacity_expansion": "underway", "order_backlog_growth": 25},
        policy_signals={"policy": 70}, cycle_signals={},
    )
    contradictions = detect_dimension_contradictions(80, 35, 70, demo_state)
    print(f"  周期80/供需35/政策70 → 检测到 {len(contradictions)} 个矛盾信号")
    for c in contradictions:
        print(f"    [{c['severity']}] {c['type']}: {c['description'][:50]}...")
    assert len(contradictions) >= 1, "应检测到至少1个矛盾信号"

    print('\n✅ System A 全模块自测通过 (V4.5)')
