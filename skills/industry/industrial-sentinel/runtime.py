#!/usr/bin/env python3
"""
Industrial Sentinel — Agent 调用入口
供 AI_Renaissance Agent 通过 SkillRegistry 加载调用

用法:
    from runtime import run_industrial_sentinel
    result = run_industrial_sentinel("002916.SZ")
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# 确保 skill 根目录在 sys.path
SKILL_DIR = Path(__file__).parent.resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


def run_industrial_sentinel(
    stock_code: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Industrial Sentinel 产业链景气度分析入口。

    Args:
        stock_code: 股票代码，如 "002916.SZ" 或 "深南电路"
        config: 可选配置字典

    Returns:
        {
            "direction": "bullish" | "bearish" | "neutral",
            "confidence": 0-100,
            "reasoning": "判定理由",
            "signals": {
                "inflection_state": "拐点前/拐点初期/拐点确认/拐点晚期/拐点后衰退",
                "lifecycle": "导入期/成长期/成熟期/衰退期",
                "stock_type": "成长型/周期型/价值型/主题型/混合型",
                "supply_demand": {...},
                "policy_catalyst": {...},
            },
            "weight": 0.0-1.0,
            "meta": {
                "html_report": "path/to/report.html",
                "stock_name": "...",
                "industry": "...",
                "preset": "...",
                "data_quality": "complete/incomplete/missing",
            },
        }
    """
    config = config or {}

    try:
        from core.pipeline import run_pipeline, load_real_data, get_stock_info
        from core.system_a import determine_inflection_from_real_data, determine_lifecycle_from_real_data
        from core.system_b import identify_stock_type

        # 加载数据
        real_data = load_real_data(stock_code)
        stock_info = get_stock_info(stock_code, real_data)

        # 运行核心分析
        lifecycle = determine_lifecycle_from_real_data(real_data)
        inflection = determine_inflection_from_real_data(real_data)

        # System B: 个股类型判定
        stock_type_result = "未判定"
        if real_data:
            financial = real_data.get("real_signals", {})
            stock_type_result = identify_stock_type(stock_info, financial)

        # 生成 HTML 报告
        html_path = ""
        try:
            html_path = run_pipeline(stock_code)
        except Exception:
            html_path = ""

        # ── 方向与置信度映射 ──
        state = inflection.get("state", "")
        stage = lifecycle.get("stage", "")

        direction_map = {
            "inflection_point": "bullish",
            "inflection_confirmed": "bullish",
            "pre_inflection": "neutral",
            "early_inflection": "bullish",
            "late_inflection": "bearish",
            "post_inflection_decline": "bearish",
        }
        direction = direction_map.get(state, "neutral")

        confidence_map = {
            "inflection_point": 70,
            "inflection_confirmed": 85,
            "pre_inflection": 25,
            "early_inflection": 55,
            "late_inflection": 40,
            "post_inflection_decline": 15,
        }
        confidence = confidence_map.get(state, 30)

        signals = {
            "inflection_state": inflection.get("state_name", "未知"),
            "lifecycle": stage or "未知",
            "stock_type": stock_type_result if isinstance(stock_type_result, str) else stock_type_result.get("type", "未判定"),
            "supply_demand": inflection.get("signals", {}),
            "policy_catalyst": inflection.get("policy_catalyst", {}),
        }

        # 权重：根据生命周期和拐点状态综合
        weight = 0.0
        if stage == "成长期" and state in ("early_inflection", "inflection_point", "inflection_confirmed"):
            weight = 0.7
        elif stage == "成长期" and state == "pre_inflection":
            weight = 0.4
        elif stage == "导入期":
            weight = 0.3
        elif stage == "成熟期" and state == "inflection_confirmed":
            weight = 0.5
        elif state == "post_inflection_decline":
            weight = 0.1

        data_quality = "complete"
        if not real_data:
            data_quality = "missing"
        elif real_data.get("_missing_count", 0) >= 3:
            data_quality = "incomplete"

        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": inflection.get("reasoning", f"{stock_info.get('stock_name','')}: {inflection.get('state_name','')} | {stage}"),
            "signals": signals,
            "weight": weight,
            "meta": {
                "html_report": html_path,
                "stock_name": stock_info.get("stock_name", stock_code),
                "stock_code": stock_code,
                "industry": stock_info.get("industry", "未知"),
                "preset": stock_info.get("preset", "generic"),
                "data_quality": data_quality,
            },
        }

    except ImportError as e:
        return {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": f"Skill 核心模块加载失败: {e}",
            "signals": {},
            "weight": 0.0,
            "meta": {"error": str(e), "html_report": ""},
        }
    except Exception as e:
        return {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": f"分析执行异常: {e}",
            "signals": {},
            "weight": 0.0,
            "meta": {"error": str(e), "html_report": ""},
        }
