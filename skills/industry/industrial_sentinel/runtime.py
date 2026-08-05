#!/usr/bin/env python3
"""
Industrial Sentinel — Agent 调用入口
供 AI_Renaissance Agent 通过 SkillRegistry 加载调用

用法:
    result = run_industrial_sentinel("002916.SZ")
"""

import sys
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 确保 skill 根目录在 sys.path
SKILL_DIR = Path(__file__).parent.resolve()
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

try:
    from .contract import (
        PACKET_SCHEMA_VERSION,
        READINESS_CONFLICTED,
        READINESS_FRAMEWORK_ONLY,
        READINESS_INDUSTRY,
        READINESS_PEER_PROXY,
        READINESS_SYSTEM_B_ONLY,
        evaluate_packet_admission,
        normalize_industry_packet,
    )
except ImportError:  # pragma: no cover - standalone skill import fallback
    from contract import (  # type: ignore
        PACKET_SCHEMA_VERSION,
        READINESS_CONFLICTED,
        READINESS_FRAMEWORK_ONLY,
        READINESS_INDUSTRY,
        READINESS_PEER_PROXY,
        READINESS_SYSTEM_B_ONLY,
        evaluate_packet_admission,
        normalize_industry_packet,
    )

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


def prepare_industry_packet(
    target: str,
    packet: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Plan and normalize one packet without crossing the runtime seam."""
    from .planning import build_execution_plan

    planned_packet = dict(packet or {})
    execution_plan = build_execution_plan(target, planned_packet, context)
    planned_target = dict(planned_packet.get("target") or {})
    planned_target.update(execution_plan["target"])
    planned_packet["target"] = planned_target
    planned_packet["routing"] = execution_plan["route"]
    planned_packet["route_evidence"] = execution_plan.get("route_evidence") or []
    planned_packet["route_evidence_rejections"] = execution_plan.get("route_evidence_rejections") or []
    planned_packet["methodology_profile"] = execution_plan["methodology_profile"]
    planned_packet["collection_plan"] = execution_plan
    existing_needs = list(planned_packet.get("needs_data") or [])
    existing_paths = {
        item.get("field_path")
        for item in existing_needs
        if isinstance(item, dict)
    }
    for item in execution_plan.get("needs_data") or []:
        if item.get("field_path") not in existing_paths:
            existing_needs.append(item)
    planned_packet["needs_data"] = existing_needs
    if execution_plan["preflight"]["status"] != "passed":
        planned_packet["industry_signals"] = {}
        planned_packet["peer_basket_signals"] = {}
        planned_packet["peer_basket_meta"] = {}
        planned_packet["framework_only"] = True
    # ``normalize_industry_packet`` intentionally keeps the v0.2 core narrow,
    # but industry-unit facts are existing optional payload fields used by
    # the report contract. Preserve them at the runtime seam so a multi-
    # industry company can be evaluated unit-by-unit without adding a
    # provider or a second file format.
    unit_optional = (
        "industry_units",
        "industry_unit_signals",
        "industry_signals_by_unit",
        "system_a_by_industry_unit",
    )
    optional_values = {
        key: deepcopy(planned_packet[key])
        for key in unit_optional
        if key in planned_packet
    }
    normalized = normalize_industry_packet(target, planned_packet, context)
    normalized.update(optional_values)
    config = dict(context or {})
    config["_packet_mode"] = True
    return normalized, config


def analyze_industry(
    target: str,
    packet: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyze one normalized IndustryDataPacket v0.2.

    This is the primary packet interface. ``run_industrial_sentinel`` remains
    the stable execution seam used by the project Agent and legacy callers.
    """
    normalized, config = prepare_industry_packet(target, packet, context)
    return run_industrial_sentinel(
        target,
        industry_result=normalized,
        financial_data=None,
        config=config,
    )


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
        from core.system_b import identify_stock_type, get_adaptive_weights

        # ── Step 1: 构建 real_data（由调用方传入的原始数据） ──
        real_data = _build_real_data(stock_code, industry_result, financial_data)
        packet = real_data.get("_packet") or _packet_from_real_data(stock_code, real_data)
        reference_date = (
            config.get("reference_date")
            or config.get("analysis_reference_date")
            or packet.get("as_of_date")
        )
        admission = evaluate_packet_admission(packet, reference_date=reference_date)
        raw_industry_signals = dict(real_data.get("industry_signals") or {})
        raw_peer_signals = dict(real_data.get("peer_basket_signals") or {})
        real_data["industry_signals"] = dict(admission.admissible_industry_signals)
        real_data["peer_basket_signals"] = dict(admission.admissible_peer_signals)
        real_data["_admission"] = admission.to_dict()
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

        # ── Step 2: 运行核心分析（packet 模式以 Methodology Profile 为唯一权威） ──
        methodology_result = None
        if config.get("_packet_mode"):
            from .methodology import evaluate_meso_methodology

            methodology_result = evaluate_meso_methodology(packet, admission)
            structural = methodology_result["structural_lifecycle"]
            inflection_conclusion = methodology_result["inflection_state"]
            lifecycle = {
                "stage": structural["label"],
                "stage_short": structural["state"],
                "analysis": methodology_result["reasoning"],
                "indicators": [],
            }
            inflection = {
                "state_name": inflection_conclusion["label"],
                "matched_signals": list(methodology_result["matched_signals"]),
                "matched_signals_list": list(methodology_result["matched_signals"]),
                "inflection_logic": methodology_result["reasoning"],
            }
        elif admission.usable_for_system_a:
            lifecycle = determine_lifecycle_from_real_data(real_data)
            inflection = determine_inflection_from_real_data(real_data)
        else:
            lifecycle, inflection = _build_unavailable_system_a_results(
                admission.readiness,
                admission.uncertainties,
            )
        effective_readiness = (
            methodology_result["effective_readiness"]
            if methodology_result
            else admission.readiness
        )
        effective_usable_for_system_a = (
            methodology_result["usable_for_system_a"]
            if methodology_result
            else admission.usable_for_system_a
        )
        effective_analysis_basis = (
            methodology_result["profile_admission"]["analysis_basis"]
            if methodology_result
            else admission.analysis_basis
        )
        profile_uncertainties = (
            list(methodology_result["profile_admission"].get("reasons") or [])
            if methodology_result
            else []
        )

        # ── Step 3: System B 个股类型判定 ──
        # identify_stock_type 签名为 (industry, revenue_growth, rd_ratio,
        # asset_lightness, profit_stability) → 5 个独立参数
        stock_type_result = "未判定"
        if admission.system_b_ready:
            rs = real_data.get("company_signals") or real_data.get("real_signals", {})
            industry_name = real_data.get(
            "industry", stock_info.get("industry", "")
            )
            revenue_growth = float(rs["revenue_growth"])
            rd_ratio = float(rs.get("rd_ratio", rs.get("research_expense_ratio")))
            asset_lightness = rs.get("asset_lightness")
            fixed_asset = rs.get("fixed_asset")
            total_asset = rs.get("total_asset")
            if asset_lightness is None and fixed_asset is not None and total_asset is not None and total_asset > 0:
                asset_lightness = max(
                    0.0,
                    min(1.0, 1.0 - float(fixed_asset) / float(total_asset)),
                )
            profit_stability = float(rs["profit_stability"])

            try:
                stock_type_result = identify_stock_type(
                    industry_name,
                    revenue_growth,
                    rd_ratio,
                    float(asset_lightness),
                    profit_stability,
                )
            except Exception as e:
                logger.warning("stock_type 判定失败: %s", e)
                stock_type_result = "未判定"

        # ── Step 4: 方向与置信度映射 ──
        state_name = inflection.get("state_name", "")
        stage = lifecycle.get("stage", "")
        state_code = STATE_NAME_TO_CODE.get(state_name, "")
        if methodology_result is not None:
            direction = methodology_result["direction"]
            confidence = methodology_result["confidence"]
            signals = list(methodology_result["signals"])
            weight = methodology_result["weight"]
            analysis_reasoning = methodology_result["reasoning"]
        else:
            direction = DIRECTION_MAP.get(state_code, "neutral")
            if admission.usable_for_system_a:
                try:
                    from core.system_a import calculate_confidence
                    confidence = calculate_confidence(
                        state_code=state_code,
                        matched_signals=(
                            inflection.get("matched_signals_list", [])
                            or inflection.get("matched_signals", [])
                        ),
                        real_data=real_data or {},
                    )
                except Exception:
                    confidence = 0.25
            else:
                confidence = 0.2 if admission.readiness == READINESS_FRAMEWORK_ONLY else 0.25
            if admission.readiness == READINESS_CONFLICTED:
                signals = ["行业判断: 证据冲突", "行业拐点: 暂不判定", "行业生命周期: 暂不判定"]
            elif admission.usable_for_system_a:
                signals = [
                    f"拐点状态: {state_name or '未知'}",
                    f"生命周期: {stage or '未知'}",
                ]
            else:
                signals = ["行业拐点: 数据不足", "行业生命周期: 数据不足"]
            weight = _legacy_industry_weight(stage, state_code, admission.usable_for_system_a)
            if admission.usable_for_system_a:
                analysis_reasoning = inflection.get(
                    "inflection_logic",
                    f"{stock_info.get('stock_name', '')}: {state_name} | {stage}",
                )
            elif admission.readiness == READINESS_CONFLICTED:
                analysis_reasoning = "行业直接证据与同业代理方向冲突，暂不形成方向性行业结论。"
            else:
                analysis_reasoning = "System A 数据准入未通过，当前仅输出产业链框架或公司级 System B 信息。"
        confidence = max(0.0, min(1.0, float(confidence)))

        # ── Step 5: 构建信号列表 ──
        stock_type_str = (
            stock_type_result
            if isinstance(stock_type_result, str)
            else stock_type_result.get("type", "未判定")
        )
        if stock_type_str and stock_type_str != "未判定":
            signals.append(f"个股类型: {stock_type_str}")

        # ── Step 6: 数据质量 ──
        data_quality = {
            READINESS_FRAMEWORK_ONLY: "missing",
            READINESS_SYSTEM_B_ONLY: "incomplete",
            READINESS_PEER_PROXY: "incomplete",
            READINESS_INDUSTRY: "complete",
            READINESS_CONFLICTED: "incomplete",
        }[effective_readiness]
        matched_signal_count = len(
            inflection.get("matched_signals_list", [])
            or inflection.get("matched_signals", [])
            or []
        )
        industry_signal_count = _count_meaningful_industry_signals(real_data)
        peer_basket_signal_count = _count_meaningful_peer_basket_signals(real_data)
        system_a_support_signal_count = industry_signal_count + peer_basket_signal_count
        raw_industry_signal_count = _count_meaningful_industry_signals(
            {"industry_signals": raw_industry_signals}
        )
        raw_peer_basket_signal_count = _count_meaningful_peer_basket_signals(
            {"peer_basket_signals": raw_peer_signals}
        )
        evidence_count = _count_evidence_items(real_data)
        needs_data_items = _normalize_needs_data_items(real_data)
        if effective_readiness == READINESS_FRAMEWORK_ONLY:
            confidence = min(confidence, 0.25)
            weight = 0.0
            direction = "neutral"
            confidence_cap_reason = "framework_only"
        elif effective_readiness == READINESS_SYSTEM_B_ONLY:
            confidence = min(confidence, 0.25)
            weight = 0.0
            direction = "neutral"
            confidence_cap_reason = "system_b_only"
        elif effective_readiness == READINESS_PEER_PROXY:
            confidence = min(confidence, 0.65)
            weight = min(weight, 0.5)
            confidence_cap_reason = "controlled_peer_proxy_cap"
        elif effective_readiness == READINESS_INDUSTRY:
            confidence = min(confidence, 0.85)
            confidence_cap_reason = "direct_industry_cap"
        else:
            confidence = min(confidence, 0.4)
            weight = 0.0
            direction = "neutral"
            matched_signal_count = 0
            confidence_cap_reason = "industry_peer_conflict"

        # Keep the public legacy adapter's degradation vocabulary stable. The
        # packet path uses readiness states; direct callers historically
        # distinguish a preset-only framework, fully missing inputs, and a
        # sparse-but-partial industry payload.
        legacy_degradation_level = None
        if not config.get("_packet_mode"):
            missing_count = int(real_data.get("_missing_count", 0) or 0)
            if real_data.get("_preset_only"):
                data_quality = "missing"
                confidence = min(confidence, 0.35)
                weight = min(weight, 0.2)
                direction = "neutral"
                confidence_cap_reason = "framework_only_preset"
                legacy_degradation_level = "framework_only"
            elif missing_count >= 2:
                data_quality = "missing"
                confidence = min(confidence, 0.25)
                weight = min(weight, 0.2)
                direction = "neutral"
                confidence_cap_reason = "industry_and_financial_data_missing"
                legacy_degradation_level = "missing"
            elif matched_signal_count < 2 or industry_signal_count < 2:
                data_quality = "incomplete"
                confidence = min(confidence, 0.45)
                weight = min(weight, 0.3)
                confidence_cap_reason = "insufficient_industry_signals"
                legacy_degradation_level = "partial"
            elif missing_count == 1:
                data_quality = "incomplete"
                confidence = min(confidence, 0.55)
                confidence_cap_reason = "partial_data_missing"
                legacy_degradation_level = "partial"

        # ── Step 6.5: 降级原因提示（从 Agent config 透传） ──
        degradation_reasons = (config or {}).get("_degradation_reasons", [])
        degradation_hint = ""
        if degradation_reasons:
            degradation_hint = " | ⚠️ 数据获取降级：" + "；".join(degradation_reasons)
        elif data_quality != "complete":
            quality_label = {"missing": "缺失", "incomplete": "不完整"}.get(data_quality, data_quality)
            degradation_hint = f" | ⚠️ 数据{quality_label}，建议回填核心指标后重新分析"

        # 构建 collection_hint：区分降级原因和一般数据缺失
        collection_hint = ""
        data_collection_tasks = []
        if degradation_reasons or data_quality != "complete" or needs_data_items:
            collection_hint = (
                "数据获取降级。建议通过 data_sources 补充行业景气、拐点、"
                "财务报表和经营质量字段后重新分析。"
            )
            # 生成结构化采集任务（只要有降级或缺失就生成）
            data_collection_tasks = _build_collection_tasks(
                stock_code, stock_info.get("stock_name", stock_code), real_data
            )

        # ── Step 7: 冻结 System A，再构建 System B 与 A×B ──
        methodology_meta = methodology_result or {}
        system_a_output = _build_system_a_output(
            methodology_meta=methodology_meta,
            lifecycle=lifecycle,
            inflection=inflection,
            readiness=effective_readiness,
            usable=effective_usable_for_system_a,
            business_exposure=_normalize_business_exposure(real_data),
            evidence=list(real_data.get("evidence") or []),
            routed_industry=stock_info.get("industry") or "",
        )
        input_type = str(packet.get("target", {}).get("input_type") or "unknown")
        company_branch = input_type == "stock_name"
        if input_type == "stock_code":
            try:
                from .core.auto_detect_preset import _is_stock_code, _resolve_input
            except ImportError:  # pragma: no cover - standalone skill import fallback
                from core.auto_detect_preset import _is_stock_code, _resolve_input  # type: ignore
            resolved_identity = _resolve_input(str(stock_code))
            company_branch = bool(
                _is_stock_code(str(stock_code))
                or _is_stock_code(resolved_identity)
                or real_data.get("company_signals")
                or real_data.get("product_industry_map")
            )
        if company_branch:
            system_b_output = _build_system_b_output(
                stock_type_result,
                stock_info.get("stock_name", stock_code),
                stock_info.get("preset", "generic"),
                real_data,
            )
            combined_conclusion = _build_combined_conclusion(
                system_a=system_a_output,
                system_b=system_b_output,
                system_a_ready=effective_usable_for_system_a,
                system_b_ready=admission.system_b_ready,
            )
        else:
            # System B and A×B are company-only contracts.  Industry/preset
            # inputs must remain empty in the structured output, not merely be
            # hidden later by the HTML renderer.
            system_b_output = {}
            combined_conclusion = {}

        degradation_level = legacy_degradation_level or {
            READINESS_FRAMEWORK_ONLY: "framework_only",
            READINESS_SYSTEM_B_ONLY: "system_b_only",
            READINESS_PEER_PROXY: "peer_proxy",
            READINESS_INDUSTRY: "none",
            READINESS_CONFLICTED: "conflicted",
        }[effective_readiness]
        evidence_items = list(real_data.get("evidence") or [])
        uncertainties = list(dict.fromkeys(list(admission.uncertainties) + profile_uncertainties))
        needs_data = (
            effective_readiness != READINESS_INDUSTRY
            or bool(degradation_reasons)
            or bool(needs_data_items)
        )
        reasoning = analysis_reasoning
        if combined_conclusion.get("summary"):
            reasoning += f" | A×B: {combined_conclusion['summary']}"

        return {
            "direction": direction,
            "source": "industrial_sentinel",
            "signal_type": "industry",
            "confidence": confidence,
            "reasoning": reasoning + degradation_hint,
            "signals": signals,
            "weight": weight,
            "meta": {
                "output_version": "0.3",
                "skill_name": "industrial_sentinel",
                "owner_group": "专家5组（行业）",
                "stock_name": stock_info.get("stock_name", stock_code),
                "stock_code": stock_code,
                "industry": stock_info.get("industry", "未知"),
                "preset": stock_info.get("preset", "generic"),
                "data_quality": data_quality,
                "degradation_level": degradation_level,
                "confidence_cap_reason": confidence_cap_reason,
                "readiness": effective_readiness,
                "analysis_basis": effective_analysis_basis,
                "industry_signal_count": (
                    raw_industry_signal_count
                    if not config.get("_packet_mode")
                    else industry_signal_count
                ),
                "peer_basket_signal_count": peer_basket_signal_count,
                "raw_industry_signal_count": raw_industry_signal_count,
                "raw_peer_basket_signal_count": raw_peer_basket_signal_count,
                "system_a_support_signal_count": system_a_support_signal_count,
                "system_a_matched_signal_count": matched_signal_count,
                "evidence_count": evidence_count,
                "needs_data_items": needs_data_items,
                "usable_for_system_a": effective_usable_for_system_a,
                "system_b_ready": bool(company_branch and admission.system_b_ready),
                "company_branch": company_branch,
                "stock_type": stock_type_result,
                "adaptive_weights": (
                    get_adaptive_weights(stock_type_result, STAGE_MAP.get(stage, "default"))
                    if company_branch and stock_type_str != "未判定"
                    else {}
                ),
                "evidence": evidence_items,
                "uncertainties": uncertainties,
                "needs_human_review": (
                    admission.needs_human_review
                    or effective_readiness == READINESS_CONFLICTED
                    or bool(
                        dict(methodology_meta.get("reasoning_trace") or {})
                        .get("summary", {})
                        .get("role_conflicts")
                    )
                    or bool(dict(packet.get("routing") or {}).get("needs_human_review"))
                ),
                "needs_data": needs_data,
                "degradation_reasons": degradation_reasons,
                "collection_hint": collection_hint,
                "data_collection_tasks": data_collection_tasks,
                "peer_basket_meta": real_data.get("peer_basket_meta", {}),
                "market_context": real_data.get("market_context", {}),
                "provider_status": packet.get("provider_status", {}),
                "source_mode": packet.get("source_mode", "project"),
                "as_of_date": packet.get("as_of_date", ""),
                "fetched_at": packet.get("fetched_at", ""),
                "data_hash": packet.get("data_hash", ""),
                "data_profile_version": packet.get("profile_version", ""),
                "cache_origin": packet.get("cache_origin", {}),
                "scope_provenance": packet.get("scope_provenance", {}),
                "routing": packet.get("routing", {}),
                "route_evidence": packet.get("route_evidence", []),
                "route_evidence_rejections": packet.get("route_evidence_rejections", []),
                "methodology_profile": packet.get("methodology_profile", {}),
                "collection_plan": packet.get("collection_plan", {}),
                "product_industry_map": system_b_output.get("business_exposure", []),
                "valuation_context": (
                    real_data.get("valuation_context", {}) if company_branch else {}
                ),
                "structural_lifecycle": methodology_meta.get("structural_lifecycle", {}),
                "cyclical_phase": methodology_meta.get("cyclical_phase", {}),
                "inflection_state": methodology_meta.get("inflection_state", {}),
                "profile_admission": methodology_meta.get("profile_admission", {}),
                "reasoning_trace": methodology_meta.get("reasoning_trace", {}),
                "system_a": system_a_output,
                "system_a_by_industry_unit": system_a_output.get("industry_units", {}),
                "system_b": system_b_output,
                "combined_conclusion": combined_conclusion,
                "report_quality": {
                    "content_map_checked": False,
                    "quality_check_attempts": 0,
                    "refinement_attempts": 0,
                    "max_refinement_attempts": 1,
                    "issues_before": [],
                    "issues_after": [],
                    "unresolved": [],
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
    if isinstance(industry_result, dict) and industry_result.get("schema_version") == PACKET_SCHEMA_VERSION:
        packet = normalize_industry_packet(stock_code, industry_result)
        target = packet["target"]
        company_signals = dict(packet["company_signals"])
        real_data = {
            "stock_code": target.get("stock_code") or stock_code,
            "stock_name": target.get("stock_name") or stock_code,
            "industry": target.get("industry") or "",
            "sub_sector": target.get("sub_sector") or "",
            "preset": target.get("preset") or "generic",
            "input_type": target.get("input_type") or "stock_code",
            "industry_signals": dict(packet["industry_signals"]),
            "peer_basket_signals": dict(packet["peer_basket_signals"]),
            "peer_basket_meta": dict(packet["peer_basket_meta"]),
            "company_signals": company_signals,
            "real_signals": company_signals,
            "product_industry_map": list(packet.get("product_industry_map") or []),
            "valuation_context": dict(packet.get("valuation_context") or {}),
            "market_context": dict(packet["market_context"]),
            "evidence": list(packet["evidence"]),
            "needs_data": list(packet["needs_data"]),
            "data_quality": packet.get("data_quality") or "",
            "as_of_date": packet.get("as_of_date") or "",
            "provider_status": dict(packet.get("provider_status") or {}),
            "routing": dict(packet.get("routing") or {}),
            "route_evidence": list(packet.get("route_evidence") or []),
            "route_evidence_rejections": list(packet.get("route_evidence_rejections") or []),
            "methodology_profile": dict(packet.get("methodology_profile") or {}),
            "collection_plan": dict(packet.get("collection_plan") or {}),
            "_packet": packet,
            "_missing_count": (
                int(not bool(packet["industry_signals"] or packet["peer_basket_signals"]))
                + int(not bool(company_signals))
            ),
        }
        for key in (
            "industry_units",
            "industry_unit_signals",
            "industry_signals_by_unit",
            "system_a_by_industry_unit",
        ):
            if isinstance(industry_result.get(key), (dict, list)):
                real_data[key] = deepcopy(industry_result[key])
        if packet.get("framework_only"):
            real_data["_preset_only"] = True
        return real_data

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
        for key in ("evidence", "needs_data", "data_quality", "as_of_date"):
            if key in industry_result:
                real_data[key] = industry_result[key]
        if industry_result.get("status") == "preset_only":
            real_data["_preset_only"] = True
        # 若数据源提供了更细粒度的信号，也一并透传为 System A 行业级信号
        signals = industry_result.get("industry_signals")
        if signals is None:
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
        if isinstance(industry_result.get("product_industry_map"), list):
            real_data["product_industry_map"] = list(industry_result["product_industry_map"])
        if isinstance(industry_result.get("valuation_context"), dict):
            real_data["valuation_context"] = dict(industry_result["valuation_context"])
        for key in ("peer_basket_meta", "market_context", "provider_status"):
            if isinstance(industry_result.get(key), dict):
                real_data[key] = dict(industry_result[key])
        for key in (
            "industry_units",
            "industry_unit_signals",
            "industry_signals_by_unit",
            "system_a_by_industry_unit",
        ):
            if isinstance(industry_result.get(key), (dict, list)):
                real_data[key] = deepcopy(industry_result[key])
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
            "asset_lightness": extracted.get("asset_lightness") if extracted.get("asset_lightness") is not None else financial_data.get("asset_lightness"),
            "profit_stability": extracted.get("profit_stability") if extracted.get("profit_stability") is not None else financial_data.get("profit_stability"),
            "operating_cash_flow_to_net_profit": extracted.get("operating_cash_flow_to_net_profit") if extracted.get("operating_cash_flow_to_net_profit") is not None else financial_data.get("operating_cash_flow_to_net_profit"),
            "contract_liability_growth": extracted.get("contract_liability_growth") if extracted.get("contract_liability_growth") is not None else financial_data.get("contract_liability_growth"),
        }
        real_data["company_signals"] = company_signals
        # System B 兼容读取 real_signals；System A 应优先读取 industry_signals。
        real_data["real_signals"] = company_signals
        if isinstance(financial_data.get("peer_basket_signals"), dict):
            real_data["peer_basket_signals"] = financial_data["peer_basket_signals"]
        if isinstance(financial_data.get("company_signals"), dict):
            real_data["company_signals"].update(
                {
                    key: value
                    for key, value in financial_data["company_signals"].items()
                    if value is not None
                }
            )
            real_data["real_signals"] = real_data["company_signals"]
        for key in ("evidence", "needs_data", "data_quality", "as_of_date"):
            if key in financial_data and key not in real_data:
                real_data[key] = financial_data[key]
        # 透传其他可能有用的字段（不计入 missing_count，这些是可选补充）
        for key in ["stock_name", "market_cap", "pe_ttm", "pb", "sector"]:
            if key in financial_data:
                real_data[key] = financial_data[key]
    else:
        missing_count += 1

    real_data["_missing_count"] = missing_count
    return real_data


def _packet_from_real_data(stock_code: str, real_data: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade the legacy runtime shape to the v0.2 packet for admission."""
    payload = {
        "target": {
            "stock_code": real_data.get("stock_code") or stock_code,
            "stock_name": real_data.get("stock_name") or stock_code,
            "industry": real_data.get("industry") or "",
            "sub_sector": real_data.get("sub_sector") or "",
            "preset": real_data.get("preset") or "generic",
            "input_type": real_data.get("input_type") or "stock_code",
        },
        "industry_signals": real_data.get("industry_signals") or {},
        "peer_basket_signals": real_data.get("peer_basket_signals") or {},
        "peer_basket_meta": real_data.get("peer_basket_meta") or {},
        "company_signals": real_data.get("company_signals") or {},
        "product_industry_map": real_data.get("product_industry_map") or [],
        "valuation_context": real_data.get("valuation_context") or {},
        "market_context": real_data.get("market_context") or {},
        "evidence": real_data.get("evidence") or [],
        "needs_data": real_data.get("needs_data") or [],
        "as_of_date": real_data.get("as_of_date") or "",
        "data_quality": real_data.get("data_quality") or "",
        "provider_status": real_data.get("provider_status") or {},
        "source_mode": "legacy_adapter",
        "_preset_only": bool(real_data.get("_preset_only")),
    }
    for key in (
        "industry_units",
        "industry_unit_signals",
        "industry_signals_by_unit",
        "system_a_by_industry_unit",
    ):
        if isinstance(real_data.get(key), (dict, list)):
            payload[key] = deepcopy(real_data[key])
    normalized = normalize_industry_packet(
        stock_code,
        payload,
    )
    for key in (
        "industry_units",
        "industry_unit_signals",
        "industry_signals_by_unit",
        "system_a_by_industry_unit",
    ):
        if key in payload:
            normalized[key] = deepcopy(payload[key])
    return normalized


def _build_unavailable_system_a_results(
    readiness: str,
    uncertainties: List[str],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    conflicted = readiness == READINESS_CONFLICTED
    state_name = "证据冲突" if conflicted else "数据不足"
    description = (
        "直接行业证据与同业代理方向冲突，暂不判定。"
        if conflicted
        else "缺少通过数据准入的行业证据或受控同业代理，暂不判定。"
    )
    if uncertainties:
        description += " " + uncertainties[0]
    lifecycle = {
        "stage": state_name,
        "stage_short": "?",
        "subtitle": state_name,
        "desc": description,
        "color": "#64748b",
        "color_bg": "rgba(100,116,139,0.12)",
        "indicators": [],
        "analysis": description,
    }
    inflection = {
        "state_name": state_name,
        "state_color": "#64748b",
        "state_color_bg": "rgba(100,116,139,0.12)",
        "matched_signals": [],
        "matched_signals_list": [],
        "inflection_data_cards": "",
        "inflection_logic": description,
    }
    return lifecycle, inflection


def _legacy_industry_weight(stage: str, state_code: str, usable_for_system_a: bool) -> float:
    """Preserve the legacy adapter's weight mapping outside packet mode."""
    if not usable_for_system_a:
        return 0.0
    if stage == "成长期" and state_code in (
        "early_inflection", "inflection_point", "inflection_confirmed"
    ):
        return 0.7
    if stage == "成长期" and state_code == "pre_inflection":
        return 0.4
    if stage == "导入期":
        return 0.3
    if stage == "成熟期" and state_code == "inflection_confirmed":
        return 0.5
    if state_code == "post_inflection_decline":
        return 0.1
    return 0.2


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


def _count_meaningful_peer_basket_signals(real_data: Optional[Dict[str, Any]]) -> int:
    """Count peer-basket proxy signals that can support System A.

    These fields are derived from multiple comparable companies, so they can
    act as industry proxies without letting a single company's statements
    contaminate System A.
    """
    if not real_data:
        return 0
    peer_signals = real_data.get("peer_basket_signals")
    if not isinstance(peer_signals, dict):
        return 0

    meaningful_keys = {
        "revenue_growth_median",
        "peer_revenue_growth_median",
        "gross_margin_median",
        "peer_gross_margin_median",
        "inventory_days_median",
        "peer_inventory_days_median",
        "inventory_days_change_median",
        "capex_trend",
        "capex_growth_median",
        "contract_liability_growth_median",
        "operating_cash_flow_to_net_profit_median",
        "construction_in_progress_growth_median",
        "gross_margin_change_median",
    }

    count = 0
    for key, value in peer_signals.items():
        if key not in meaningful_keys:
            continue
        if value in (None, "", [], {}, "数据缺失", "待补充"):
            continue
        count += 1
    return count


def _count_evidence_items(real_data: Optional[Dict[str, Any]]) -> int:
    if not real_data:
        return 0
    evidence = real_data.get("evidence")
    if isinstance(evidence, list):
        return len([item for item in evidence if item])
    if isinstance(evidence, dict):
        return 1
    return 0


def _normalize_needs_data_items(real_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not real_data:
        return []
    needs_data = real_data.get("needs_data")
    if not needs_data:
        return []
    if isinstance(needs_data, list):
        normalized = []
        for item in needs_data:
            if isinstance(item, dict):
                normalized.append(item)
            elif item:
                normalized.append({"field_path": str(item), "reason": "upstream_needs_data"})
        return normalized
    if isinstance(needs_data, dict):
        return [needs_data]
    return [{"field_path": str(needs_data), "reason": "upstream_needs_data"}]


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
    def get_path_value(path: str) -> Any:
        if not real_data:
            return None
        current: Any = real_data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    # 字段元数据：label / unit / required / 搜索关键词模板
    FIELD_META = {
        "revenue_growth": {
            "label": "营收增速",
            "unit": "小数（如 0.15 表示同比增长 15%）",
            "fill_path": "company_signals.revenue_growth",
            "required": True,
            "templates": [
                "{code} {name} 年报 营收增速 同比增长",
                "{name} 营业收入 同比变化 最新财报",
            ],
        },
        "gross_margin": {
            "label": "毛利率",
            "unit": "小数（如 0.35 表示 35%）",
            "fill_path": "company_signals.gross_margin",
            "required": True,
            "templates": [
                "{code} {name} 毛利率 最新财报",
                "{name} 营业成本 毛利率 年报",
            ],
        },
        "rd_ratio": {
            "label": "研发费用率",
            "unit": "小数（研发费用 / 营业收入）",
            "fill_path": "company_signals.rd_ratio",
            "required": False,
            "templates": [
                "{code} {name} 研发费用率 研发投入占比",
                "{name} 研发费用 占营收比例",
            ],
        },
        "fixed_asset": {
            "label": "固定资产",
            "unit": "元（绝对金额，如 1500000000）",
            "fill_path": "company_signals.fixed_asset",
            "required": False,
            "templates": [
                "{code} {name} 固定资产 资产负债表",
                "{name} 固定资产原值 最新财报",
            ],
        },
        "total_asset": {
            "label": "总资产",
            "unit": "元（绝对金额）",
            "fill_path": "company_signals.total_asset",
            "required": False,
            "templates": [
                "{code} {name} 总资产 资产负债表",
                "{name} 资产总计 最新财报",
            ],
        },
        "net_profit_parent": {
            "label": "归母净利润",
            "unit": "元（绝对金额）",
            "fill_path": "company_signals.net_profit_parent",
            "required": False,
            "templates": [
                "{code} {name} 归母净利润 利润表",
                "{name} 净利润 归属于上市公司股东",
            ],
        },
        "roe": {
            "label": "净资产收益率 ROE",
            "unit": "小数（如 0.12 表示 12%）",
            "fill_path": "company_signals.roe",
            "required": False,
            "templates": [
                "{code} {name} ROE 净资产收益率",
                "{name} 加权平均净资产收益率",
            ],
        },
        "debt_ratio": {
            "label": "资产负债率",
            "unit": "小数（如 0.45 表示 45%）",
            "fill_path": "company_signals.debt_ratio",
            "required": False,
            "templates": [
                "{code} {name} 资产负债率",
                "{name} 负债合计 总资产 资产负债率",
            ],
        },
        "order_backlog": {
            "label": "订单 backlog / 合同负债",
            "unit": "元（绝对金额）或描述性文字",
            "fill_path": "industry_signals.industry_order_backlog",
            "required": False,
            "templates": [
                "{code} {name} 合同负债 订单 backlog",
                "{name} 在手订单 未交付订单金额",
            ],
        },
        "capacity_utilization": {
            "label": "产能利用率",
            "unit": "小数（如 0.85 表示 85%）",
            "fill_path": "industry_signals.industry_capacity_utilization",
            "required": False,
            "templates": [
                "{code} {name} 产能利用率",
                "{name} 产能 开工率 产线利用率",
            ],
        },
        "price_yoy": {
            "label": "产品价格同比变化",
            "unit": "小数（如 -0.05 表示下降 5%）",
            "fill_path": "industry_signals.industry_price_yoy",
            "required": False,
            "templates": [
                "{name} 产品售价 价格同比 最新",
                "{name} 行业价格走势 同比变化",
            ],
        },
        "inventory_days": {
            "label": "库存天数",
            "unit": "天（整数或小数）",
            "fill_path": "peer_basket_signals.inventory_days_median",
            "required": False,
            "templates": [
                "{code} {name} 库存周转天数",
                "{name} 存货周转天数 库存天数",
            ],
        },
        "peer_revenue_growth_median": {
            "label": "同业营收增速中位数",
            "unit": "% 或小数（需标注口径）",
            "fill_path": "peer_basket_signals.revenue_growth_median",
            "required": False,
            "templates": [
                "{name} 同行业公司 营收增速 中位数",
                "{code} {name} 可比公司 财报 营收同比",
            ],
        },
        "peer_gross_margin_median": {
            "label": "同业毛利率中位数",
            "unit": "% 或小数（需标注口径）",
            "fill_path": "peer_basket_signals.gross_margin_median",
            "required": False,
            "templates": [
                "{name} 同行业公司 毛利率 中位数",
                "{code} {name} 可比公司 财报 毛利率",
            ],
        },
        "peer_contract_liability_growth_median": {
            "label": "同业合同负债增速中位数",
            "unit": "% 或小数（需标注口径）",
            "fill_path": "peer_basket_signals.contract_liability_growth_median",
            "required": False,
            "templates": [
                "{name} 同行业公司 合同负债 增速 中位数",
                "{code} {name} 可比公司 合同负债 财报",
            ],
        },
    }

    tasks = []
    for field, meta in FIELD_META.items():
        # 检查字段是否缺失
        fill_path = meta["fill_path"]
        val = get_path_value(fill_path)
        if val is not None and val != "":
            continue  # 已有数据，跳过

        # 生成搜索关键词
        search_queries = [
            t.format(code=stock_code, name=stock_name)
            for t in meta["templates"]
        ]

        # 根据字段类型确定数据来源层级（L1-L4）
        financial_fields = {
            "revenue_growth", "gross_margin", "rd_ratio", "fixed_asset",
            "total_asset", "net_profit_parent", "roe", "debt_ratio",
            "peer_revenue_growth_median", "peer_gross_margin_median",
            "peer_contract_liability_growth_median",
        }
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
                "fill_path": fill_path,
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


def _build_system_a_output(
    methodology_meta: Dict[str, Any],
    lifecycle: Dict[str, Any],
    inflection: Dict[str, Any],
    readiness: str,
    usable: bool,
    business_exposure: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    routed_industry: str = "",
) -> Dict[str, Any]:
    """Expose A1, A2 and lifecycle as separate, stable conclusions."""
    prosperity = dict(methodology_meta.get("cyclical_phase") or {})
    turning_point = dict(methodology_meta.get("inflection_state") or {})
    structural = dict(methodology_meta.get("structural_lifecycle") or {})
    if not prosperity:
        prosperity = {
            "state": "undetermined" if not usable else "legacy",
            "label": "待判定" if not usable else lifecycle.get("stage_short") or lifecycle.get("stage") or "待判定",
            "evidence_refs": [],
        }
    if not turning_point:
        turning_point = {
            "state": "undetermined" if not usable else "legacy",
            "label": "待判定" if not usable else inflection.get("state_name") or "待判定",
            "evidence_refs": [],
        }
    if not structural:
        structural = {
            "state": "undetermined" if not usable else "legacy",
            "label": "待判定" if not usable else lifecycle.get("stage") or "待判定",
            "evidence_refs": [],
        }
    result = {
        "readiness": readiness,
        "usable": bool(usable),
        "prosperity": prosperity,
        "inflection": turning_point,
        "lifecycle": structural,
    }
    units = list(dict.fromkeys(
        str(item.get("industry_unit") or "").strip()
        for item in (business_exposure or [])
        if isinstance(item, dict) and str(item.get("industry_unit") or "").strip()
    ))
    unit_views: Dict[str, Dict[str, Any]] = {}
    reasoning_trace = dict(methodology_meta.get("reasoning_trace") or {})
    admitted_refs = {
        str(node.get("evidence_ref") or "")
        for node in reasoning_trace.get("nodes") or []
        if isinstance(node, dict)
        and node.get("admission_status") == "admitted"
        and node.get("evidence_ref")
    }
    unit_evidence_ids: Dict[str, set[str]] = {}
    for record in evidence or []:
        if not isinstance(record, dict) or str(record.get("scope") or "") != "industry":
            continue
        unit = str(record.get("industry_unit") or "").strip()
        evidence_id = str(record.get("evidence_id") or "").strip()
        if unit and evidence_id and evidence_id in admitted_refs:
            unit_evidence_ids.setdefault(unit, set()).add(evidence_id)

    def admitted_unit_view(unit: str) -> Optional[Dict[str, Any]]:
        refs = unit_evidence_ids.get(unit, set())
        if not refs:
            return None
        try:
            from .methodology import evaluate_admitted_trace_subset
        except ImportError:  # pragma: no cover - standalone skill import fallback
            from methodology import evaluate_admitted_trace_subset  # type: ignore
        derived = evaluate_admitted_trace_subset(
            reasoning_trace,
            refs,
            dict(methodology_meta.get("profile_admission") or {}),
        )
        if not derived.get("usable_for_system_a"):
            return None
        return {
            "industry_unit": unit,
            "readiness": "industry_ready",
            "usable": True,
            "inherited_global": False,
            "prosperity": dict(derived["cyclical_phase"]),
            "inflection": dict(derived["inflection_state"]),
            "lifecycle": dict(derived["structural_lifecycle"]),
            "evidence_refs": sorted(refs),
            "reason": "仅用该产业单元已准入节点，按同一 Methodology Profile 规则重新计算。",
        }

    def unavailable_unit_view(unit: str, reason: str) -> Dict[str, Any]:
        return {
            "industry_unit": unit,
            "readiness": "unit_evidence_required",
            "usable": False,
            "inherited_global": False,
            "prosperity": {"state": "undetermined", "label": "待独立判定", "evidence_refs": []},
            "inflection": {"state": "undetermined", "label": "待独立判定", "evidence_refs": []},
            "lifecycle": {"state": "undetermined", "label": "待独立判定", "evidence_refs": []},
            "reason": reason,
        }

    if len(units) == 1:
        explicit = admitted_unit_view(units[0])
        same_scope = (
            re.sub(r"[\W_]+", "", units[0]).lower()
            == re.sub(r"[\W_]+", "", str(routed_industry or "")).lower()
        )
        if explicit:
            unit_views[units[0]] = explicit
        elif usable and same_scope:
            unit_views[units[0]] = {
                **result,
                "industry_unit": units[0],
                "inherited_global": True,
                "reason": "单一产业单元与已准入的路由产业一致，可继承全局 System A。",
            }
        else:
            unit_views[units[0]] = unavailable_unit_view(
                units[0],
                "产业单元与已准入路由未证明同一，需补充独立行业证据。",
            )
    elif len(units) > 1:
        for unit in units:
            explicit = admitted_unit_view(unit)
            unit_views[unit] = explicit or unavailable_unit_view(
                unit,
                "多产业公司必须为该产业单元补充独立、已准入的行业证据；禁止套用全局或公司数据。",
            )
    result["industry_units"] = unit_views
    return result


def _normalize_business_exposure(real_data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in (real_data or {}).get("product_industry_map") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "product": item.get("product") or "待补",
                "material_or_technology": item.get("material_or_technology") or "待补",
                "form_and_function": item.get("form_and_function") or item.get("function") or "待补",
                "industry_unit": item.get("industry_unit") or "待补",
                "company_position": item.get("company_position") or "待补",
                "direct_customer": item.get("direct_customer") or "待补",
                "downstream_system": item.get("downstream_system") or "待补",
                "end_demand": item.get("end_demand") or "待补",
                "status": item.get("status") or "待补",
                "mapping_evidence": list(item.get("mapping_evidence") or item.get("evidence_ids") or []),
            }
        )
    return rows


def _build_combined_conclusion(
    system_a: Dict[str, Any],
    system_b: Dict[str, Any],
    system_a_ready: bool,
    system_b_ready: bool,
) -> Dict[str, Any]:
    """Cross A and B without allowing company facts to rewrite System A."""
    prosperity = dict(system_a.get("prosperity") or {}).get("label") or "待判定"
    inflection = dict(system_a.get("inflection") or {}).get("label") or "待判定"
    stock_type = system_b.get("stock_type") or "未判定"
    exposure = list(system_b.get("business_exposure") or [])
    unit_views = dict(system_a.get("industry_units") or {})
    unresolved_units = [
        unit for unit, view in unit_views.items()
        if not bool(dict(view or {}).get("usable"))
    ]

    if exposure and unresolved_units:
        status = "partial"
        summary = (
            f"公司包含{len(unit_views)}个产业单元，其中"
            f"{len(unresolved_units)}个缺少独立 System A 证据；"
            "不得把全局行业结论复制到各业务，先补齐逐单元景气与拐点。"
        )
    elif system_a_ready and system_b_ready and exposure:
        status = "complete"
        summary = (
            f"产业景气为{prosperity}、拐点为{inflection}；公司属于{stock_type}，"
            f"已建立{len(exposure)}项产品—产业回指，仍需逐项验证收入、利润与定价兑现。"
        )
    elif system_a_ready and system_b_ready:
        status = "partial"
        summary = (
            f"产业景气为{prosperity}、拐点为{inflection}；System B 已就绪，"
            "但产品—产业回指缺失，不能证明行业变化已传导到公司。"
        )
    elif system_a_ready:
        status = "partial"
        summary = (
            f"产业景气为{prosperity}、拐点为{inflection}；System B 数据不足，"
            "不能把行业结论直接外推为公司结论。"
        )
    elif system_b_ready:
        status = "blocked_by_system_a"
        summary = "System A 行业证据未通过准入；公司财务特征不能替代产业景气与拐点。"
    else:
        status = "insufficient_data"
        summary = "System A 与 System B 均未满足数据准入，只保留框架和待补字段。"

    crosswalk = []
    for item in exposure:
        unit = str(item.get("industry_unit") or "待补")
        unit_view = dict(unit_views.get(unit) or {})
        crosswalk.append(
            {
                "product": item.get("product"),
                "industry_unit": unit,
                "company_position": item.get("company_position"),
                "delivery_status": item.get("status"),
                "system_a_readiness": unit_view.get("readiness") or system_a.get("readiness"),
                "prosperity": dict(unit_view.get("prosperity") or system_a.get("prosperity") or {}).get("label") or "待判定",
                "inflection": dict(unit_view.get("inflection") or system_a.get("inflection") or {}).get("label") or "待判定",
                "lifecycle": dict(unit_view.get("lifecycle") or system_a.get("lifecycle") or {}).get("label") or "待判定",
                "transmission_status": (
                    "该产业单元的 System A 尚未独立准入，禁止外推公司兑现。"
                    if unit_view and not unit_view.get("usable")
                    else "待用分业务收入、毛利、产能与客户证据验证"
                ),
            }
        )
    return {
        "status": status,
        "summary": summary,
        "short_status": f"System A {prosperity} · 拐点 {inflection} · System B {stock_type}",
        "business_crosswalk": crosswalk,
        "valuation_alignment": system_b.get("valuation_driver") or "证据不足",
        "next_confirmation": (
            system_b.get("next_confirmation")
            or "补充分业务收入、毛利、产能利用率与客户认证/量产进展。"
        ),
        "invalidation": (
            "System A 核心指标反转，或公司产品未进入批量/收入与现金流未兑现。"
            if system_a_ready
            else "行业证据继续缺失或冲突时，不得形成方向性 A×B 结论。"
        ),
    }


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
    real_data = real_data or {}
    business_exposure = _normalize_business_exposure(real_data)
    valuation = dict(real_data.get("valuation_context") or {})
    shared = {
        "stock_type": stock_type if isinstance(stock_type, str) else "未判定",
        "business_exposure": business_exposure,
        "revenue_driver": valuation.get("revenue_driver") or "未取得分业务收入主线证据",
        "profit_driver": valuation.get("profit_driver") or "未取得分业务利润主线证据",
        "valuation_driver": valuation.get("valuation_driver") or "证据不足",
        "delivery": [
            {"product": item.get("product"), "status": item.get("status")}
            for item in business_exposure
        ],
        "next_confirmation": valuation.get("next_confirmation") or "补充分业务收入、利润、产能和客户兑现证据",
    }
    if stock_type in (None, "", "未判定"):
        return {
            **shared,
            "core_contradiction": "公司级财务输入不足，暂不判定个股类型。",
            "tracking_metrics": [
                "补充营收增速与研发费用率",
                "补充固定资产与总资产",
                "补充近三年归母净利润以计算利润稳定性",
            ],
            "risks": ["System B 数据不足，禁止使用默认值形成类型判断"],
        }

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
        **shared,
        "core_contradiction": template["core_contradiction"],
        "tracking_metrics": template["tracking_metrics"],
        "risks": template["risks"],
    }
