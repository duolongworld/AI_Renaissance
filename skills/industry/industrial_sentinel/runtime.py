#!/usr/bin/env python3
"""
Industrial Sentinel — Agent 调用入口
供 AI_Renaissance Agent 通过 SkillRegistry 加载调用

用法:
    result = run_industrial_sentinel("002916.SZ")
"""

import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 确保 skill 根目录在 sys.path
SKILL_DIR = Path(__file__).parent.resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

# ── 拐点中文状态名 → 内部 code 映射 ──
# 必须与 core/system_a.py 中 STATE_META 的 "name" 字段完全一致
STATE_NAME_TO_CODE = {
    "拐点确认": "inflection_confirmed",
    "拐点初期": "early_inflection",
    "拐点前/潜伏": "pre_inflection",
    "拐点晚期": "late_inflection",
    "拐点后/衰退": "post_inflection_decline",
}

DIRECTION_MAP = {
    "inflection_point": "bullish",
    "inflection_confirmed": "bullish",
    "pre_inflection": "neutral",
    "early_inflection": "bullish",
    "late_inflection": "bearish",
    "post_inflection_decline": "bearish",
}


# ──────────────────────────────────────────────────────────────
# Stage name mapping: Chinese → English (for System B weights)
# ──────────────────────────────────────────────────────────────
STAGE_MAP = {
    "导入期": "valuation_switch",
    "成长期": "performance_period",
    "成长期(稳健)": "performance_period",
    "成熟期": "default",
    "衰退期": "emotion_driven",
    "退潮期": "emotion_driven",
    "结构转型": "valuation_switch",
    "结构转型·拐点确认": "valuation_switch",
    "结构转型·拐点初期": "valuation_switch",
    "结构转型·拐点早期": "valuation_switch",
}


def run_industrial_sentinel(
    stock_code: str,
    industry_result: Optional[dict] = None,
    financial_data: Optional[dict] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Industrial Sentinel 产业链景气度分析入口。

    Args:
    stock_code: 股票代码，如 "002916.SZ" 或 "深南电路"
    industry_result: 行业情绪数据源返回的原始 dict（由调用方提供）
    financial_data: 财务数据源返回的原始 dict（由调用方提供）
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
        get_stock_info,
        determine_inflection_from_real_data, determine_lifecycle_from_real_data,
        )
        from core.system_b import identify_stock_type, get_asset_lightness_benchmark, get_adaptive_weights

        # ── Step 1: 构建 real_data（由调用方传入的原始数据） ──
        real_data = _build_real_data(
    stock_code, industry_result, financial_data)
        stock_info = get_stock_info(stock_code, real_data)

        # 自动检测 preset（如果未配置）
        if not stock_info.get("preset") or stock_info.get("preset") == "generic":
            try:
                from core.auto_detect_preset import auto_detect_preset
                detected_preset = auto_detect_preset(
                    stock_code,
                    Path(__file__).parent / "data",
                    allow_provider_lookup=False,
                )
                if detected_preset:
                    stock_info["preset"] = detected_preset
                    real_data["preset"] = detected_preset
                    logger.info("[runtime] 自动检测到 preset: %s", detected_preset)
            except Exception as e:
                logger.debug("runtime 中 auto_detect_preset 失败: %s", e)

        # 如果行业名称缺失，从 preset YAML 补充
        if stock_info.get("industry") in ("数据缺失", "", None):
            preset_name = stock_info.get("preset", "")
            if preset_name and preset_name != "generic":
                try:
                    from core.pipeline import load_preset_yaml
                    yaml_data = load_preset_yaml(preset_name)
                    if yaml_data:
                        industry_name = yaml_data.get("industry_name", preset_name)
                        stock_info["industry"] = industry_name
                        real_data["industry"] = industry_name
                        logger.info("[runtime] 从YAML补充行业名称: %s", industry_name)
                except Exception as e:
                    logger.debug("runtime 中加载 preset YAML 失败: %s", e)

        # ── Step 2: 运行核心分析（生命周期 + 拐点） ──
        lifecycle = determine_lifecycle_from_real_data(real_data)
        inflection = determine_inflection_from_real_data(real_data)

        # ── Step 3: System B 个股类型判定 ──
        # identify_stock_type 签名为 (industry, revenue_growth, rd_ratio,
        # asset_lightness, profit_stability) → 5 个独立参数
        stock_type_result = "未判定"
        if real_data:
            rs = real_data.get("company_signals") or real_data.get("real_signals", {})
            industry_name = real_data.get(
            "industry", stock_info.get("industry", "")
            )
            revenue_growth = float(rs.get("revenue_growth", 0) or 0)
            rd_ratio = float(
    rs.get(
        "rd_ratio",
        rs.get(
            "research_expense_ratio",
             0)) or 0)
            # 轻资产程度：优先用行业基准值，有固定资产数据则计算
            preset_for_benchmark = stock_info.get("preset", "generic")
            asset_lightness = get_asset_lightness_benchmark(
            preset_name=preset_for_benchmark,
            industry_name=industry_name
            )
            fixed_asset = rs.get("fixed_asset")
            total_asset = rs.get("total_asset")
            if fixed_asset is not None and total_asset is not None and total_asset > 0:
                asset_lightness = max(
    0.0, min(
        1.0, 1.0 - float(fixed_asset) / float(total_asset)))
                # 利润稳定性：有利润数据则计算波动
            profit_stability = 0.50
            net_profit = rs.get("net_profit_parent")
            if net_profit is not None and float(net_profit) > 0:
                profit_stability = 0.70  # 盈利状态中等稳定

            # System B 个股类型判定（不依赖 net_profit，只要有 real_data 就尝试）
            try:
                stock_type_result = identify_stock_type(
                    industry_name,
                    revenue_growth,
                    rd_ratio,
                    asset_lightness,
                    profit_stability,
                )
            except Exception as e:
                logger.warning("stock_type 判定失败: %s", e)
                stock_type_result = "未判定"

        # ── Step 4: 方向与置信度映射 ──
        # Agent 模式只返回结构化 Signal 数据，不生成 HTML 报告。
        # 🔴 关键修复: pipeline 返回的是 state_name（中文），不是 state code
        state_name = inflection.get("state_name", "")
        stage = lifecycle.get("stage", "")

        state_code = STATE_NAME_TO_CODE.get(state_name, "")
        direction = DIRECTION_MAP.get(state_code, "neutral")
        # 优化4: 多维置信度替代固定映射
        try:
            from core.system_a import calculate_confidence
            confidence = calculate_confidence(
            state_code=state_code,
            matched_signals=inflection.get(
    "matched_signals_list", []) or inflection.get(
        "matched_signals", []),
            real_data=real_data or {},
            )
        except Exception:
            confidence = 0.25  # 降级: 使用默认置信度
        # 防御性 clamp: 确保 confidence 始终在有效范围内
        confidence = max(0.0, min(1.0, float(confidence)))

        # ── Step 5: 构建信号列表 ──
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

        # ── Step 6: 权重 ──
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
        elif stage == "数据缺失":
            weight = 0.2
        elif weight == 0.0:
            weight = 0.2

        # 数据缺失时降低行业信号在仲裁层的影响力。
        if not real_data or real_data.get("_missing_count", 0) >= 2:
            weight = min(weight, 0.2)
        elif real_data.get("_missing_count", 0) == 1:
            weight = min(weight, 0.4)

        # ── Step 7: 数据质量 ──
        data_quality = "complete"
        if not real_data:
            data_quality = "missing"
        elif real_data.get("_missing_count", 0) >= 2:
            data_quality = "missing"  # 两个主要数据源都缺失
        elif real_data.get("_missing_count", 0) >= 1:
            data_quality = "incomplete"  # 至少一个主要数据源缺失
        else:
            # 两个主要数据源都存在，但检查 real_signals 字段缺失
            rs = real_data.get("company_signals") or real_data.get("real_signals", {})
            if rs:
                # 统计 real_signals 中缺失的字段数量
                missing_fields = sum(1 for v in rs.values() if v is None or v == "")
                if missing_fields >= 8:
                    data_quality = "missing"
                elif missing_fields >= 5:
                    data_quality = "incomplete"
            else:
                data_quality = "missing"
        confidence_cap_reason = ""
        matched_signal_count = len(
            inflection.get("matched_signals_list", [])
            or inflection.get("matched_signals", [])
            or []
        )
        industry_signal_count = _count_meaningful_industry_signals(real_data)
        if real_data and real_data.get("_missing_count", 0) >= 2:
            confidence = min(confidence, 0.25)
            confidence_cap_reason = "industry_and_financial_data_missing"
        elif real_data and real_data.get("_missing_count", 0) == 1:
            confidence = min(confidence, 0.55)
            confidence_cap_reason = "partial_data_missing"
        if real_data and real_data.get("_preset_only"):
            data_quality = "missing"
            confidence = min(confidence, 0.35)
            weight = min(weight, 0.2)
            confidence_cap_reason = "framework_only_preset"
        elif (
            not confidence_cap_reason
            and (matched_signal_count < 2 or industry_signal_count < 2)
        ):
            if data_quality == "complete":
                data_quality = "incomplete"
            confidence = min(confidence, 0.45)
            weight = min(weight, 0.3)
            confidence_cap_reason = "insufficient_industry_signals"

        # ── Step 7.5: 降级原因提示（从 Agent config 透传） ──
        degradation_reasons = (config or {}).get("_degradation_reasons", [])
        degradation_hint = ""
        if degradation_reasons:
            degradation_hint = " | ⚠️ 数据获取降级：" + "；".join(degradation_reasons)
        elif data_quality != "complete":
            degradation_hint = f" | ⚠️ 数据{data_quality}，建议回填核心指标后重新分析"

        # 构建 collection_hint：区分降级原因和一般数据缺失
        collection_hint = ""
        data_collection_tasks = []
        if degradation_reasons or data_quality != "complete":
            collection_hint = (
                "数据获取降级。建议通过 data_sources 补充行业景气、拐点、"
                "财务报表和经营质量字段后重新分析。"
            )
            # 生成结构化采集任务（只要有降级或缺失就生成）
            data_collection_tasks = _build_collection_tasks(
                stock_code, stock_info.get("stock_name", stock_code), real_data
            )

        # ── Step 8: 构建完整 System B 输出 ──
        system_b_output = _build_system_b_output(
            stock_type_result,
            stock_info.get("stock_name", stock_code),
            stock_info.get("preset", "generic"),
            real_data,
        )

        degradation_level = "none"
        if data_quality == "missing":
            degradation_level = "framework_only" if real_data.get("_preset_only") else "missing"
        elif data_quality == "incomplete" or degradation_reasons:
            degradation_level = "partial"

        return {
            "direction": direction,
            "source": "industrial_sentinel",
            "signal_type": "industry",
            "confidence": confidence,
            "reasoning": (
                inflection.get(
                    "inflection_logic",
                    f"{stock_info.get('stock_name', '')}: {state_name} | {stage}",
                ) + degradation_hint
            ),
            "signals": signals,
            "weight": weight,
            "meta": {
                "skill_name": "industrial_sentinel",
                "owner_group": "专家5组（行业）",
                "stock_name": stock_info.get("stock_name", stock_code),
                "stock_code": stock_code,
                "industry": stock_info.get("industry", "未知"),
                "preset": stock_info.get("preset", "generic"),
                "data_quality": data_quality,
                "degradation_level": degradation_level,
                "confidence_cap_reason": confidence_cap_reason,
                "industry_signal_count": industry_signal_count,
                "system_a_matched_signal_count": matched_signal_count,
                "stock_type": stock_type_result,
                "adaptive_weights": get_adaptive_weights(stock_type_result, STAGE_MAP.get(stage, "default")),
                "needs_data": data_quality != "complete" or bool(degradation_reasons),
                "degradation_reasons": degradation_reasons,
                "collection_hint": collection_hint,
                "data_collection_tasks": data_collection_tasks,
                "system_b": {
                    "core_contradiction": system_b_output["core_contradiction"],
                    "tracking_metrics": system_b_output["tracking_metrics"],
                    "risks": system_b_output["risks"],
                },
            },
        }

    except ImportError as e:
        return {
            "direction": "neutral",
            "confidence": 0.25,
            "reasoning": f"Skill 核心模块加载失败: {e}",
            "signals": [],
            "weight": 0.0,
            "meta": {"error": str(e)},
        }
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error("分析执行异常: %s\n%s", e, tb)
        return {
            "direction": "neutral",
            "confidence": 0.25,
            "reasoning": f"分析执行异常: {e}",
            "signals": [],
            "weight": 0.0,
            "meta": {"error": str(e), "traceback": tb},
        }


def _build_real_data(
    stock_code: str,
    industry_result: Optional[dict] = None,
    financial_data: Optional[dict] = None,
) -> dict:
    """将外部数据源返回的原始 dict 转换为 industrial_sentinel 内部 real_data 格式。"""
    real_data: Dict[str, Any] = {"stock_code": stock_code}
    missing_count = 0

    # ── 行业情绪数据 ──
    if industry_result:
        stage = industry_result.get("stage") or {}
        real_data["industry"] = (
            industry_result.get("industry")
            or industry_result.get("industry_name")
            or ""
        )
        real_data["industry_sentiment"] = (
            industry_result.get("sentiment")
            or stage.get("name")
            or industry_result.get("direction")
            or ""
        )
        real_data["industry_sentiment_score"] = (
            industry_result.get("sentiment_score")
            if industry_result.get("sentiment_score") is not None
            else industry_result.get("score", 0)
        )
        real_data["industry_sentiment_direction"] = industry_result.get("direction", "")
        real_data["industry_sentiment_confidence"] = industry_result.get("confidence", 0)
        for key in ("preset", "input_type", "stock_name"):
            if industry_result.get(key):
                real_data[key] = industry_result[key]
        if industry_result.get("status") == "preset_only":
            real_data["_preset_only"] = True
        # 若数据源提供了更细粒度的信号，也一并透传为 System A 行业级信号
        signals = industry_result.get("signals")
        if signals is None:
            signals = industry_result.get("special_signals")
        if signals is not None:
            real_data["industry_signals"] = _normalize_industry_signals(
                signals,
                industry_result=industry_result,
            )
        elif any(k in industry_result for k in ("score", "stage", "direction", "confidence")):
            real_data["industry_signals"] = _normalize_industry_signals(
                None,
                industry_result=industry_result,
            )
        peer_signals = industry_result.get("peer_basket_signals")
        if isinstance(peer_signals, dict):
            real_data["peer_basket_signals"] = peer_signals
    else:
        missing_count += 1

    # ── 财务数据 ──
    if financial_data:
        # 优先尝试从原始三张表（balance/income/cashflow）提取关键指标
        extracted = _extract_metrics_from_statements(financial_data)
        # 若提取失败，fallback 到扁平化字段
        company_signals = {
            "revenue_growth": extracted.get("revenue_growth") if extracted.get("revenue_growth") is not None else financial_data.get("revenue_growth"),
            "rd_ratio": extracted.get("rd_ratio") if extracted.get("rd_ratio") is not None else financial_data.get("rd_ratio"),
            "research_expense_ratio": extracted.get("research_expense_ratio") if extracted.get("research_expense_ratio") is not None else financial_data.get("research_expense_ratio"),
            "fixed_asset": extracted.get("fixed_asset") if extracted.get("fixed_asset") is not None else financial_data.get("fixed_asset"),
            "total_asset": extracted.get("total_asset") if extracted.get("total_asset") is not None else financial_data.get("total_asset"),
            "net_profit_parent": extracted.get("net_profit_parent") if extracted.get("net_profit_parent") is not None else financial_data.get("net_profit_parent"),
            "gross_margin": extracted.get("gross_margin") if extracted.get("gross_margin") is not None else financial_data.get("gross_margin"),
            "roe": extracted.get("roe") if extracted.get("roe") is not None else financial_data.get("roe"),
            "debt_ratio": extracted.get("debt_ratio") if extracted.get("debt_ratio") is not None else financial_data.get("debt_ratio"),
        }
        real_data["company_signals"] = company_signals
        # System B 兼容读取 real_signals；System A 应优先读取 industry_signals。
        real_data["real_signals"] = company_signals
        if isinstance(financial_data.get("peer_basket_signals"), dict):
            real_data["peer_basket_signals"] = financial_data["peer_basket_signals"]
        # 透传其他可能有用的字段（不计入 missing_count，这些是可选补充）
        for key in ["stock_name", "market_cap", "pe_ttm", "pb", "sector"]:
            if key in financial_data:
                real_data[key] = financial_data[key]
    else:
        missing_count += 1

    real_data["_missing_count"] = missing_count
    return real_data


def _normalize_industry_signals(signals: Any, industry_result: Optional[dict] = None) -> dict:
    """Normalize provider industry output into the System A signal contract."""
    industry_result = industry_result or {}
    normalized: Dict[str, Any] = {}

    if isinstance(signals, dict):
        normalized.update(signals)
    elif isinstance(signals, list):
        normalized["qualitative_signals"] = [str(s) for s in signals if s]
        normalized["inflection_signals"] = normalized["qualitative_signals"]
        normalized["lifecycle_signals"] = normalized["qualitative_signals"]
    elif isinstance(signals, str) and signals.strip():
        normalized["qualitative_signals"] = [signals.strip()]
        normalized["inflection_signals"] = normalized["qualitative_signals"]

    stage = industry_result.get("stage") or {}
    stage_name = stage.get("name") if isinstance(stage, dict) else stage
    direction = industry_result.get("direction") or (
        stage.get("direction") if isinstance(stage, dict) else None
    )
    if stage_name:
        normalized.setdefault("industry_lifecycle_stage", stage_name)
    if direction:
        normalized.setdefault("industry_sentiment_direction", direction)
    if industry_result.get("score") is not None:
        normalized.setdefault("industry_heat_score", industry_result.get("score"))
    if industry_result.get("confidence") is not None:
        normalized.setdefault("industry_signal_confidence", industry_result.get("confidence"))

    return normalized


def _count_meaningful_industry_signals(real_data: Optional[Dict[str, Any]]) -> int:
    """Count industry-level signals that can support System A.

    Company financial fields are intentionally excluded: System A needs
    industry/peer evidence, not just one company's statements.
    """
    if not real_data:
        return 0
    industry_signals = real_data.get("industry_signals")
    if not isinstance(industry_signals, dict):
        return 0

    meaningful_keys = {
        "industry_revenue_growth",
        "industry_market_growth",
        "industry_demand_growth",
        "industry_order_growth",
        "industry_order_backlog",
        "industry_capacity_utilization",
        "industry_capacity_util",
        "industry_price_yoy",
        "industry_price_trend",
        "industry_inventory_days",
        "industry_inventory_cycle",
        "industry_capex_plan",
        "industry_capacity_expansion",
        "industry_policy_count",
        "industry_policy_score",
        "industry_penetration_rate",
        "industry_competition_score",
        "inflection_signals",
        "lifecycle_signals",
        "qualitative_signals",
    }

    count = 0
    for key, value in industry_signals.items():
        if key not in meaningful_keys:
            continue
        if value in (None, "", [], {}, "数据缺失", "待补充"):
            continue
        if isinstance(value, list):
            count += len([item for item in value if item])
        else:
            count += 1
    return count


def _extract_metrics_from_statements(financial_data: dict) -> dict:
    balance = financial_data.get("balance") or {}
    income = financial_data.get("income") or {}

    # 提取最新一期数据行（兼容 EastMoney API 的多种返回格式）
    def _latest_row(statement: Any) -> dict:
        """从财务报表 JSON 中提取最新一行数据。

        兼容三种格式：
        1. list: 直接是行列表，取第一个元素
        2. dict 含 "data" 键: {"data": [...]}，取 data[0]
        3. dict 不含 "data" 键: 直接是行数据，原样返回
        """
        if isinstance(statement, list) and statement and isinstance(
            statement[0], dict):
            return statement[0]
        if isinstance(statement, dict):
            rows = statement.get("data")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                return rows[0]
            if "data" not in statement:
                return statement
        return {}

    b_row = _latest_row(balance)
    i_row = _latest_row(income)

    result: Dict[str, Any] = {}

    # ── income 指标 ──
    revenue = _safe_float(i_row.get("OPERATE_INCOME"))
    operating_cost = _safe_float(i_row.get("OPERATE_COST"))
    net_profit_parent = _safe_float(i_row.get("PARENT_NETPROFIT"))
    research_expense = _safe_float(i_row.get("RESEARCH_EXPENSE"))
    revenue_growth_yoy = _safe_float(i_row.get("OPERATE_INCOME_YOY"))

    if revenue_growth_yoy is not None:
        result["revenue_growth"] = revenue_growth_yoy * 0.01  # 百分比 → 小数

    if revenue is not None and operating_cost is not None and revenue > 0:
        result["gross_margin"] = (revenue - operating_cost) / revenue

    if research_expense is not None and revenue is not None and revenue > 0:
        result["rd_ratio"] = research_expense / revenue
        result["research_expense_ratio"] = research_expense / revenue

    if net_profit_parent is not None:
        result["net_profit_parent"] = net_profit_parent

    # ── balance 指标 ──
    fixed_asset = _safe_float(b_row.get("FIXED_ASSET")) or _safe_float(b_row.get("FIXED_ASSETS"))
    if fixed_asset is not None:
        result["fixed_asset"] = fixed_asset

    # 总资产：尝试多个可能的字段名
    total_asset = (
        _safe_float(b_row.get("TOTAL_ASSETS"))
        or _safe_float(b_row.get("TOTAL_LIAB_EQUITY"))
        or _safe_float(b_row.get("TOTAL_ASSETS_END"))
        or _safe_float(b_row.get("ASSETS_TOTAL"))
    )
    if total_asset is not None:
        result["total_asset"] = total_asset

    # 归母权益
    equity_parent = _safe_float(b_row.get("TOTAL_PARENT_EQUITY"))
    if equity_parent is not None and equity_parent > 0:
        if net_profit_parent is not None:
            result["roe"] = net_profit_parent / equity_parent

    # 资产负债率：总负债 / 总资产
    total_liab = (
        _safe_float(b_row.get("TOTAL_LIABILITIES"))
        or _safe_float(b_row.get("TOTAL_LIAB"))
        or _safe_float(b_row.get("LIABILITIES_TOTAL"))
    )
    if total_liab is not None and total_asset is not None and total_asset > 0:
        result["debt_ratio"] = total_liab / total_asset

    return result


def _safe_float(value: Any) -> Optional[float]:
    """安全地将值转为 float，失败时返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_collection_tasks(
    stock_code: str,
    stock_name: str,
    real_data: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """根据缺失字段生成结构化 AI 数据采集任务清单。

    返回可直接消费的 task 列表，每个 task 告诉使用者的 AI：
    - 缺什么字段（field / label）
    - 搜什么关键词（search_queries）
    - 填到 JSON 的哪个路径（fill_path）
    - 单位是什么（unit）
    - 优先级来源（source_priority）
    """
    if not real_data:
        # 完全无数据：生成全部核心字段任务
        real_signals = {}
    else:
        real_signals = real_data.get("company_signals") or real_data.get("real_signals", {})

    # 字段元数据：label / unit / required / 搜索关键词模板
    FIELD_META = {
        "revenue_growth": {
            "label": "营收增速",
            "unit": "小数（如 0.15 表示同比增长 15%）",
            "required": True,
            "templates": [
                "{code} {name} 年报 营收增速 同比增长",
                "{name} 营业收入 同比变化 最新财报",
            ],
        },
        "gross_margin": {
            "label": "毛利率",
            "unit": "小数（如 0.35 表示 35%）",
            "required": True,
            "templates": [
                "{code} {name} 毛利率 最新财报",
                "{name} 营业成本 毛利率 年报",
            ],
        },
        "rd_ratio": {
            "label": "研发费用率",
            "unit": "小数（研发费用 / 营业收入）",
            "required": False,
            "templates": [
                "{code} {name} 研发费用率 研发投入占比",
                "{name} 研发费用 占营收比例",
            ],
        },
        "fixed_asset": {
            "label": "固定资产",
            "unit": "元（绝对金额，如 1500000000）",
            "required": False,
            "templates": [
                "{code} {name} 固定资产 资产负债表",
                "{name} 固定资产原值 最新财报",
            ],
        },
        "total_asset": {
            "label": "总资产",
            "unit": "元（绝对金额）",
            "required": False,
            "templates": [
                "{code} {name} 总资产 资产负债表",
                "{name} 资产总计 最新财报",
            ],
        },
        "net_profit_parent": {
            "label": "归母净利润",
            "unit": "元（绝对金额）",
            "required": False,
            "templates": [
                "{code} {name} 归母净利润 利润表",
                "{name} 净利润 归属于上市公司股东",
            ],
        },
        "roe": {
            "label": "净资产收益率 ROE",
            "unit": "小数（如 0.12 表示 12%）",
            "required": False,
            "templates": [
                "{code} {name} ROE 净资产收益率",
                "{name} 加权平均净资产收益率",
            ],
        },
        "debt_ratio": {
            "label": "资产负债率",
            "unit": "小数（如 0.45 表示 45%）",
            "required": False,
            "templates": [
                "{code} {name} 资产负债率",
                "{name} 负债合计 总资产 资产负债率",
            ],
        },
        "order_backlog": {
            "label": "订单 backlog / 合同负债",
            "unit": "元（绝对金额）或描述性文字",
            "required": False,
            "templates": [
                "{code} {name} 合同负债 订单 backlog",
                "{name} 在手订单 未交付订单金额",
            ],
        },
        "capacity_utilization": {
            "label": "产能利用率",
            "unit": "小数（如 0.85 表示 85%）",
            "required": False,
            "templates": [
                "{code} {name} 产能利用率",
                "{name} 产能 开工率 产线利用率",
            ],
        },
        "price_yoy": {
            "label": "产品价格同比变化",
            "unit": "小数（如 -0.05 表示下降 5%）",
            "required": False,
            "templates": [
                "{name} 产品售价 价格同比 最新",
                "{name} 行业价格走势 同比变化",
            ],
        },
        "inventory_days": {
            "label": "库存天数",
            "unit": "天（整数或小数）",
            "required": False,
            "templates": [
                "{code} {name} 库存周转天数",
                "{name} 存货周转天数 库存天数",
            ],
        },
    }

    tasks = []
    for field, meta in FIELD_META.items():
        # 检查字段是否缺失
        val = real_signals.get(field)
        if val is not None and val != "":
            continue  # 已有数据，跳过

        # 生成搜索关键词
        search_queries = [
            t.format(code=stock_code, name=stock_name)
            for t in meta["templates"]
        ]

        # 根据字段类型确定数据来源层级（L1-L4）
        financial_fields = {"revenue_growth", "gross_margin", "rd_ratio", "fixed_asset",
                           "total_asset", "net_profit_parent", "roe", "debt_ratio"}
        if field in financial_fields:
            source_level = "L1"  # 官方/财报
            source_priority = [
                "L1 公司年报/季报（交易所公告，置信度90%）",
                "L1 公司公告/投资者关系活动记录",
                "L2 券商研报（有明确财报引用标注，置信度70%）",
            ]
        else:
            source_level = "L2/L3"  # 行业数据
            source_priority = [
                "L2 券商研报/行业调研（置信度70%）",
                "L3 行业协会/咨询机构报告（置信度50%）",
                "L3 产业新闻/公司公告（需交叉验证，置信度50%）",
            ]

        tasks.append(
            {
                "field": field,
                "label": meta["label"],
                "search_queries": search_queries,
                "fill_path": f"real_signals.{field}",
                "unit": meta["unit"],
                "required": meta["required"],
                "source_level": source_level,
                "source_priority": source_priority,
                "source_url": "搜索后填入具体URL",
                "date": "搜索后填入数据日期（YYYY-MM-DD）",
                "validation_rule": "必须标注数据来源和日期；超过90天的数据标注'数据老化'；无法确认来源的标注'待验证'",
            }
        )

    # 如果行业数据也缺失，追加行业情绪任务
    if not real_data or not real_data.get("industry"):
        tasks.append(
            {
                "field": "industry",
                "label": "所属行业及板块",
                "search_queries": [
                    f"{stock_code} {stock_name} 所属行业 板块分类",
                    f"{stock_name} 申万行业分类 证监会行业",
                ],
                "fill_path": "industry",
                "unit": "字符串（如'半导体'、'光通信'）",
                "required": True,
                "source_level": "L1",
                "source_priority": [
                    "L1 交易所官方行业分类（置信度90%）",
                    "L1 公司年报/招股书（置信度90%）",
                    "L3 同花顺/东方财富板块数据（需交叉验证，置信度50%）",
                ],
                "source_url": "搜索后填入具体URL",
                "date": "搜索后填入数据日期（YYYY-MM-DD）",
                "validation_rule": "优先使用交易所官方分类；不同平台分类不一致时以交易所为准",
            }
        )

    return tasks


def _build_system_b_output(
    stock_type: str,
    stock_name: str,
    preset: str,
    real_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """根据个股类型生成完整的 System B 输出。

    返回:
        {
            "core_contradiction": str,   # 核心矛盾（一句话）
            "tracking_metrics": List[str], # 跟踪指标（5个）
            "risks": List[str],           # 风险清单（5个）
        }
    """
    # 基础模板，按 stock_type 分类
    TEMPLATES = {
        "growth": {
            "core_contradiction": (
                "高估值与高增速的匹配度：若增速放缓但估值仍按成长股定价，"
                "则存在估值回归风险。"
            ),
            "tracking_metrics": [
                "营收增速是否维持≥25%（季报跟踪）",
                "研发费用率是否维持≥5%（年报跟踪）",
                "PEG 是否<1（估值锚定）",
                "新订单/新客户拓展进度",
                "竞争对手技术迭代是否构成替代威胁",
            ],
            "risks": [
                "增速不及预期导致估值下杀",
                "技术路线被颠覆（如硅光替代EML）",
                "大客户集中度过高",
                "行业产能过剩引发价格战",
                "海外政策限制（出口管制/关税）",
            ],
        },
        "cyclical": {
            "core_contradiction": (
                "周期位置与定价的错配：若当前处于周期高点但市场按常态估值，"
                "则存在周期下行时的戴维斯双杀风险。"
            ),
            "tracking_metrics": [
                "产品价格环比变化（月度跟踪）",
                "产能利用率是否>80%（季度跟踪）",
                "库存周转天数趋势",
                "行业资本开支计划（扩产/收缩信号）",
                "下游需求订单能见度",
            ],
            "risks": [
                "周期下行导致利润大幅波动",
                "重资产折旧摊销侵蚀利润",
                "原材料价格暴涨压缩毛利",
                "环保/能耗政策限制产能",
                "下游需求突然萎缩",
            ],
        },
        "value": {
            "core_contradiction": (
                "低增长与高股息的平衡：若股息率下降或ROE恶化，"
                "则价值型投资逻辑被破坏。"
            ),
            "tracking_metrics": [
                "ROE 是否稳定≥10%（年报跟踪）",
                "股息率是否≥3%（分红公告跟踪）",
                "PE 历史分位是否<30%",
                "经营现金流/净利润是否>1",
                "负债率是否可控（<60%）",
            ],
            "risks": [
                "股息率下降导致吸引力丧失",
                "ROE 持续下滑",
                "行业监管政策突变",
                "利率上行压制高股息资产估值",
                "资产减值风险",
            ],
        },
        "theme": {
            "core_contradiction": (
                "概念热度与基本面兑现的时差：若情绪退潮但业绩仍未兑现，"
                "则存在股价大幅回调风险。"
            ),
            "tracking_metrics": [
                "情绪热度指标（搜索指数/研报覆盖频次）",
                "催化事件密度（政策/订单/合作公告）",
                "资金流向（北向/机构持仓变化）",
                "营收增速是否开始兑现预期",
                "估值与同类概念股的相对位置",
            ],
            "risks": [
                "概念退潮导致资金撤离",
                "基本面长期无法兑现",
                "监管政策打压概念炒作",
                "同质化竞争导致故事失效",
                "大股东减持/解禁抛压",
            ],
        },
        "mixed": {
            "core_contradiction": (
                "多维度特征矛盾导致难以归类：需持续观察哪一维度信号强化，"
                "从而向单一类型收敛。"
            ),
            "tracking_metrics": [
                "营收增速趋势（是否向成长型或价值型收敛）",
                "利润稳定性变化（周期属性是否强化）",
                "研发投入产出比",
                "行业地位变化（市占率/议价权）",
                "政策/事件催化频率",
            ],
            "risks": [
                "类型模糊导致估值锚定困难",
                "多业务板块相互拖累",
                "转型失败导致两头落空",
                "市场关注度低导致流动性不足",
                "任一维度恶化都可能触发重估",
            ],
        },
    }

    template = TEMPLATES.get(stock_type, TEMPLATES["mixed"])

    # 根据 preset 做行业特化调整
    preset_adjustments = {
        "optical-module": {
            "growth": {
                "tracking_metrics": [
                    "800G/1.6T 光模块出货量（季度跟踪）",
                    "DSP/EML 芯片供应瓶颈是否缓解",
                    "北美云厂商 Capex 指引（年度/季度）",
                    "硅光技术渗透率变化",
                    "新进入者（如设备商自研）威胁",
                ],
                "risks": [
                    "800G 需求不及预期",
                    "硅光技术颠覆传统可插拔方案",
                    "Lumentum/Coherent 产能释放导致价格竞争",
                    "中美科技脱钩影响北美客户订单",
                    "汇率波动影响出口毛利",
                ],
            },
            "cyclical": {
                "tracking_metrics": [
                    "磷化铟衬底价格走势（月度）",
                    "光模块 ASP（平均售价）环比变化",
                    "云厂商库存水位（季度）",
                    "行业产能扩张计划",
                    "下游数据中心建设进度",
                ],
                "risks": [
                    "云厂商资本开支收缩",
                    "产能过剩引发价格战",
                    "上游材料（InP、DSP）供应瓶颈",
                    "技术迭代导致库存减值",
                    "地缘政治影响海外订单",
                ],
            },
        },
        "robotics": {
            "theme": {
                "tracking_metrics": [
                    "人形机器人政策催化频率",
                    "特斯拉/华为等巨头进展",
                    "减速器/执行器订单能见度",
                    "零部件国产化率提升进度",
                    "相关概念指数资金流向",
                ],
                "risks": [
                    "人形机器人量产进度不及预期",
                    "核心零部件（谐波减速器）仍依赖进口",
                    "估值过高导致情绪退潮",
                    "同质化竞争导致毛利率下滑",
                    "下游应用场景落地缓慢",
                ],
            },
        },
    }

    # 应用 preset 特化
    if preset in preset_adjustments and stock_type in preset_adjustments[preset]:
        adj = preset_adjustments[preset][stock_type]
        if "tracking_metrics" in adj:
            template = dict(template)
            template["tracking_metrics"] = adj["tracking_metrics"]
        if "risks" in adj:
            template = dict(template)
            template["risks"] = adj["risks"]

    return {
        "core_contradiction": template["core_contradiction"],
        "tracking_metrics": template["tracking_metrics"],
        "risks": template["risks"],
    }
