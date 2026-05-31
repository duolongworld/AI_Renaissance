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

# ── 拐点中文状态名 → 内部 code 映射 ──
STATE_NAME_TO_CODE = {
    "拐点确认": "inflection_confirmed",
    "拐点处": "inflection_point",
    "拐点前": "pre_inflection",
    "拐点早期": "early_inflection",
    "拐点后期": "late_inflection",
    "拐点后衰退": "post_inflection_decline",
}

DIRECTION_MAP = {
    "inflection_point": "bullish",
    "inflection_confirmed": "bullish",
    "pre_inflection": "neutral",
    "early_inflection": "bullish",
    "late_inflection": "bearish",
    "post_inflection_decline": "bearish",
}

CONFIDENCE_MAP = {
    "inflection_point": 0.70,
    "inflection_confirmed": 0.85,
    "pre_inflection": 0.25,
    "early_inflection": 0.55,
    "late_inflection": 0.40,
    "post_inflection_decline": 0.15,
}


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
            "confidence": 0.0-1.0,
            "reasoning": "判定理由",
            "signals": [...],
            "weight": 0.0-1.0,
            "meta": {...},
        }
    """
    config = config or {}

    try:
        from core.pipeline import (
            run_pipeline, load_real_data, get_stock_info,
            determine_inflection_from_real_data, determine_lifecycle_from_real_data,
        )
        from core.system_b import identify_stock_type

        # ── Step 1: 加载数据 ──
        real_data = load_real_data(stock_code)
        stock_info = get_stock_info(stock_code, real_data)

        # ── Step 2: 运行核心分析（生命周期 + 拐点） ──
        lifecycle = determine_lifecycle_from_real_data(real_data)
        inflection = determine_inflection_from_real_data(real_data)

        # ── Step 3: System B 个股类型判定 ──
        # identify_stock_type 签名为 (industry, revenue_growth, rd_ratio,
        # asset_lightness, profit_stability) → 5 个独立参数
        stock_type_result = "未判定"
        if real_data:
            rs = real_data.get("real_signals", {})
            industry_name = real_data.get(
                "industry", stock_info.get("industry", "")
            )
            revenue_growth = float(rs.get("revenue_growth", 0) or 0)
            rd_ratio = float(rs.get("rd_ratio", rs.get("research_expense_ratio", 0)) or 0)
            # 轻资产程度：科技股默认偏高，有固定资产数据则计算
            asset_lightness = 0.70
            fixed_asset = rs.get("fixed_asset")
            total_asset = rs.get("total_asset")
            if fixed_asset is not None and total_asset is not None and total_asset > 0:
                asset_lightness = max(0.0, min(1.0, 1.0 - float(fixed_asset) / float(total_asset)))
            # 利润稳定性：有利润数据则计算波动
            profit_stability = 0.50
            net_profit = rs.get("net_profit_parent")
            if net_profit is not None and float(net_profit) > 0:
                profit_stability = 0.70  # 盈利状态中等稳定
            try:
                stock_type_result = identify_stock_type(
                    industry_name,
                    revenue_growth,
                    rd_ratio,
                    asset_lightness,
                    profit_stability,
                )
            except Exception:
                stock_type_result = "未判定"

        # ── Step 4: 生成 HTML 报告 ──
        html_path = ""
        try:
            html_path = run_pipeline(stock_code)
        except Exception:
            html_path = ""

        # ── Step 5: preset/industry 回传 ──
        # run_pipeline 内部会更新 stock_info 的 preset/industry，
        # 但 runtime.py 用的是初始 stock_info，需重新检测
        try:
            from core.auto_detect_preset import auto_detect_preset
            DATA_DIR = SKILL_DIR / "data"
            detected = auto_detect_preset(stock_code, DATA_DIR)
            if detected:
                stock_info["preset"] = detected
                from core.pipeline import load_preset_yaml
                yaml_data = load_preset_yaml(detected)
                if yaml_data:
                    stock_info["industry"] = yaml_data.get("industry_name", detected)
        except Exception:
            pass

        # ── Step 6: 方向与置信度映射 ──
        # 🔴 关键修复: pipeline 返回的是 state_name（中文），不是 state code
        state_name = inflection.get("state_name", "")
        stage = lifecycle.get("stage", "")

        state_code = STATE_NAME_TO_CODE.get(state_name, "")
        direction = DIRECTION_MAP.get(state_code, "neutral")
        confidence = CONFIDENCE_MAP.get(state_code, 0.30)

        # ── Step 7: 构建信号列表 ──
        signals = [
            f"拐点状态: {state_name or '未知'}",
            f"生命周期: {stage or '未知'}",
        ]
        stock_type_str = (
            stock_type_result
            if isinstance(stock_type_result, str)
            else stock_type_result.get("type", "未判定")
        )
        if stock_type_str and stock_type_str != "未判定":
            signals.append(f"个股类型: {stock_type_str}")

        # ── Step 8: 权重 ──
        weight = 0.0
        if stage == "成长期" and state_code in (
            "early_inflection", "inflection_point", "inflection_confirmed"
        ):
            weight = 0.7
        elif stage == "成长期" and state_code == "pre_inflection":
            weight = 0.4
        elif stage == "导入期":
            weight = 0.3
        elif stage == "成熟期" and state_code == "inflection_confirmed":
            weight = 0.5
        elif state_code == "post_inflection_decline":
            weight = 0.1

        # ── Step 9: 数据质量 ──
        data_quality = "complete"
        if not real_data:
            data_quality = "missing"
        elif real_data.get("_missing_count", 0) >= 3:
            data_quality = "incomplete"

        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": inflection.get(
                "reasoning",
                f"{stock_info.get('stock_name', '')}: {state_name} | {stage}",
            ),
            "signals": signals,
            "weight": weight,
            "meta": {
                "html_report": html_path,
                "stock_name": stock_info.get("stock_name", stock_code),
                "stock_code": stock_code,
                "industry": stock_info.get("industry", "未知"),
                "preset": stock_info.get("preset", "generic"),
                "data_quality": data_quality,
                "supply_demand": inflection.get("signals", {}),
                "policy_catalyst": inflection.get("policy_catalyst", {}),
            },
        }

    except ImportError as e:
        return {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": f"Skill 核心模块加载失败: {e}",
            "signals": [],
            "weight": 0.0,
            "meta": {"error": str(e), "html_report": ""},
        }
    except Exception as e:
        return {
            "direction": "neutral",
            "confidence": 0,
            "reasoning": f"分析执行异常: {e}",
            "signals": [],
            "weight": 0.0,
            "meta": {"error": str(e), "html_report": ""},
        }
