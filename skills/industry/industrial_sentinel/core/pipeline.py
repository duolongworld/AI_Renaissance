#!/usr/bin/env python3
"""
Industrial Sentinel 端到端流水线 — 真实数据版
Pipeline: 股票代码 → 加载真实数据 → 拐点判定 → 类型分析 → HTML仪表盘

用法:
    python3 core/pipeline.py <stock_code>
    python3 core/pipeline.py AXTI.US

输出:
    生成 HTML 仪表盘文件, 打印文件路径
"""

import json
import logging
import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("industrial_sentinel_pipeline")

# ── 路径 ──
SCRIPT_DIR = Path(__file__).parent.parent.resolve()
TEMPLATES_DIR = SCRIPT_DIR / "templates"
DATA_DIR = SCRIPT_DIR / "data"
REPORTS_DIR = SCRIPT_DIR / "reports"
REF_DIR = SCRIPT_DIR / "references"

# Ensure skill root is in sys.path
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.system_a import (
    determine_inflection_state,
)
from core.system_b import (
    get_stock_type_description,
)

# ═══════════════════════════════════════════════════════════════
# Step 1: 加载真实数据
# ═══════════════════════════════════════════════════════════════

def load_real_data(stock_code: str) -> Optional[Dict[str, Any]]:
    """
    加载股票的真实数据 JSON。
    支持常见A股简称映射。
    """
    alias_map = {
        "贵州茅台": "600519.SH",
        "宁德时代": "300750.SZ",
        "比亚迪": "002594.SZ",
        "东山精密": "002384.SZ",
    }
    resolved_code = alias_map.get(stock_code, stock_code)
    
    candidates = [
        DATA_DIR / f"{resolved_code}_real_data.json",
        DATA_DIR / f"{stock_code}_real_data.json",
        DATA_DIR / f"{stock_code.upper()}_real_data.json",
        DATA_DIR / f"{stock_code.lower()}_real_data.json",
    ]
    # 支持交易所后缀自动去除（如 AXTI.US → AXTI）
    base_code = re.sub(r'\.(US|HK|SH|SZ|BJ)$', '', resolved_code, flags=re.IGNORECASE)
    if base_code != resolved_code:
        candidates.insert(0, DATA_DIR / f"{base_code}_real_data.json")
    base_code_raw = re.sub(r'\.(US|HK|SH|SZ|BJ)$', '', stock_code, flags=re.IGNORECASE)
    if base_code_raw != stock_code and base_code_raw != base_code:
        candidates.insert(0, DATA_DIR / f"{base_code_raw}_real_data.json")

    seen = set()
    for path in candidates:
        ps = str(path)
        if ps in seen:
            continue
        seen.add(ps)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("加载真实数据: %s", path.name)
                return data
            except Exception as e:
                logger.error("加载数据失败 %s: %s", path, e)
                continue
    logger.warning("未找到 %s 的真实数据，所有指标将标记为「数据缺失」", stock_code)
    return None

def get_stock_info(stock_code: str, real_data: Optional[Dict]) -> Dict[str, str]:
    """提取股票基本信息"""
    if real_data:
        return {
            "stock_code": real_data.get("stock_code", stock_code),
            "stock_name": real_data.get("stock_name", stock_code),
            "industry": real_data.get("industry", "数据缺失"),
            "sub_industry": real_data.get("sub_industry", "数据缺失"),
        "preset": real_data.get("preset", "generic"),
            "chain_position": real_data.get("chain_position", "数据缺失"),
        }
    return {
        "stock_code": stock_code,
        "stock_name": stock_code,
        "industry": "数据缺失",
        "sub_industry": "数据缺失",
        "chain_position": "数据缺失",
        "preset": "generic",
    }

# ═══════════════════════════════════════════════════════════════
# 数据安全转换辅助
# ═══════════════════════════════════════════════════════════════

def _safe_num(value) -> Optional[float]:
    """安全地将输入值转换为数字。兼容显式字符串占位（如「数据缺失」）。
    
    Returns:
        float: 成功转换的数值
        None: 值无效、为空字符串、或显式标注「数据缺失」「待补充」等占位符
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        if v in ("数据缺失", "待补充", "待填写", "N/A", "—", "", "null", "None"):
            return None
        # 尝试移除百分号、千分位逗号后转换
        cleaned = v.replace("%", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _first_present(source: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", "数据缺失", "待补充"):
            return value
    return None


def _build_system_a_signals(real_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """构造 System A 输入：只接受已通过准入的行业或同业代理信号。

    ``company_signals`` / ``real_signals`` 属于 System B。即使行业数据
    完全缺失，也禁止把单家公司财务回退成行业信号。
    """
    if not real_data:
        return {}

    industry = real_data.get("industry_signals") or {}
    peer = real_data.get("peer_basket_signals") or {}
    if not isinstance(industry, dict):
        industry = {"qualitative_signals": industry}
    if not isinstance(peer, dict):
        peer = {}

    result: Dict[str, Any] = {}
    scopes: Dict[str, str] = {}

    def put(target: str, source: Dict[str, Any], keys: List[str], scope: str) -> None:
        if target in result:
            return
        value = _first_present(source, keys)
        if value is None:
            return
        result[target] = value
        scopes[target] = scope
        source_key = next((k for k in keys if source.get(k) == value), "")
        if source_key and source.get(f"{source_key}_source"):
            result[f"{target}_source"] = source[f"{source_key}_source"]

    put("revenue_growth", industry, ["industry_revenue_growth", "industry_market_growth", "industry_demand_growth"], "industry")
    put("order_backlog", industry, ["industry_order_growth", "industry_order_backlog", "industry_demand_growth"], "industry")
    put("capacity_utilization", industry, ["industry_capacity_utilization", "industry_capacity_util"], "industry")
    put("price_yoy", industry, ["industry_price_yoy", "industry_price_trend"], "industry")
    put("inventory_days", industry, ["industry_inventory_days", "industry_inventory_cycle"], "industry")
    put("capex_plan", industry, ["industry_capex_plan", "industry_capacity_expansion"], "industry")
    put("policy_count", industry, ["industry_policy_count"], "industry")
    put("policy_score", industry, ["industry_policy_score"], "industry")
    put("penetration_rate", industry, ["industry_penetration_rate"], "industry")
    put("competition_score", industry, ["industry_competition_score"], "industry")

    put("revenue_growth", peer, ["revenue_growth_median", "peer_revenue_growth_median"], "peer_basket")
    put("gross_margin", peer, ["gross_margin_median", "peer_gross_margin_median"], "peer_basket")
    put("order_backlog", peer, ["contract_liability_growth_qoq_median", "contract_liability_growth_yoy_median", "contract_liability_growth_median"], "peer_basket")
    put("inventory_days", peer, ["inventory_days_median", "peer_inventory_days_median"], "peer_basket")
    put("capex_plan", peer, ["capex_trend", "capex_growth_median", "construction_in_progress_growth_median"], "peer_basket")

    for key in ("inflection_signals", "lifecycle_signals", "qualitative_signals"):
        value = industry.get(key)
        if value:
            result[key] = value
            scopes[key] = "industry"

    result["_signal_scope"] = scopes
    return result

# ═══════════════════════════════════════════════════════════════
# Step 2: 生命周期阶段判定（基于真实数据）
# ═══════════════════════════════════════════════════════════════

def determine_lifecycle_from_segments(segment_data: list) -> dict:
    """多业务公司分部判定。
    新业务(增速>50%)占比>=30% + 旧业务(增速<0%) → 结构转型"""
    if not segment_data or len(segment_data) < 2:
        return None
    new_segs = [s for s in segment_data if s.get("revenue_growth", 0) > 50]
    old_segs = [s for s in segment_data if s.get("revenue_growth", 0) < 0]
    if not new_segs:
        return None
    new_mix = sum(s.get("revenue_mix", 0) for s in new_segs)
    old_mix = sum(s.get("revenue_mix", 0) for s in old_segs) if old_segs else 0
    transition_score = min(1.0, new_mix * 0.4 / 100 + 0.3)
    if new_mix >= 30 and old_mix >= 20:
        stage, short = "结构转型·拐点确认", "转型确认"
        desc = f"新业务占比{new_mix:.0f}%，旧业务占比{old_mix:.0f}%，转型拐点已确认"
    elif new_mix >= 20:
        stage, short = "结构转型·拐点初期", "转型初期"
        desc = f"新业务占比{new_mix:.0f}%，拐点初期"
    else:
        return None
    seg_results = []
    for seg in segment_data:
        g = seg.get("revenue_growth", 0)
        s = "成长期" if g >= 30 else ("成长期(稳健)" if g >= 15 else ("成熟期" if g > 0 else "衰退期"))
        seg_results.append({"name": seg.get("segment_name",""), "stage": s, "growth": g, "mix": seg.get("revenue_mix",0)})
    return {"stage": stage, "stage_short": short, "subtitle": "结构转型", "desc": desc,
            "segment_analysis": seg_results, "transition_score": round(transition_score, 2),
            "color": "#f59e0b", "color_bg": "rgba(245,158,11,0.12)",
            "indicators": [{"label": "新业务占比", "value": f"{new_mix:.0f}%"}, {"label": "转型进度", "value": f"{transition_score*100:.0f}%"}],
            "analysis": f"新业务占比{new_mix:.0f}%，毛利率趋势验证中 | 关键节点：新业务突破30%即为结构拐点确认"}



def determine_lifecycle_from_real_data(real_data: Optional[Dict]) -> Dict[str, Any]:
    """
    基于行业级指标和同业验证信号判定生命周期阶段。
    无算法评分，仅做逻辑推理。
    """
    if not real_data:
        return {
            "stage": "数据缺失",
            "stage_short": "?",
            "subtitle": "无数据",
            "desc": "未提供真实数据，无法判定生命周期阶段。",
            "color": "#64748b",
            "color_bg": "rgba(100,116,139,0.12)",
            "indicators": [],
            "analysis": "请补充行业级数据或同业篮子数据以进行生命周期判定。",
        }

    signals = _build_system_a_signals(real_data)
    
    # 优化1: 优先检查结构转型
    seg_data = signals.get("segment_data", [])
    if seg_data and len(seg_data) >= 2:
        seg_result = determine_lifecycle_from_segments(seg_data)
        if seg_result and seg_result.get("transition_score", 0) >= 0.35:
            return seg_result
    
    rev_growth = _safe_num(signals.get("revenue_growth"))
    gm = _safe_num(signals.get("gross_margin"))
    backlog_raw = signals.get("order_backlog")
    backlog = _safe_num(backlog_raw)
    capex = str(signals.get("capex_plan", "")).lower()
    util = _safe_num(signals.get("capacity_utilization"))
    price_yoy = _safe_num(signals.get("price_yoy"))
    inv_days = _safe_num(signals.get("inventory_days"))
    penetration = _safe_num(signals.get("penetration_rate"))

    # 推理逻辑
    indicators = []
    if rev_growth is not None:
        indicators.append({"label": "行业/同业增速", "value": f"{rev_growth:.0f}%", "trend": "up" if rev_growth > 20 else "flat", "source": signals.get("revenue_growth_source", signals.get("_signal_scope", {}).get("revenue_growth", "行业数据"))})
    if gm is not None:
        indicators.append({"label": "同业毛利率", "value": f"{gm:.1f}%", "trend": "up" if gm > 20 else "flat", "source": signals.get("gross_margin_source", signals.get("_signal_scope", {}).get("gross_margin", "同业篮子"))})
    if backlog is not None:
        indicators.append({"label": "行业订单/需求", "value": f"{backlog:.0f}", "trend": "up", "source": signals.get("order_backlog_source", signals.get("_signal_scope", {}).get("order_backlog", "行业数据"))})
    elif backlog_raw is not None and isinstance(backlog_raw, str) and backlog_raw.strip() not in ("数据缺失", "待补充", "", "null", "None"):
        indicators.append({"label": "行业订单/需求", "value": backlog_raw, "trend": "up", "source": signals.get("order_backlog_source", signals.get("_signal_scope", {}).get("order_backlog", "行业数据"))})
    if util is not None:
        indicators.append({"label": "行业产能利用率", "value": f"{util:.0f}%", "trend": "up" if util > 80 else "flat", "source": signals.get("capacity_utilization_source", signals.get("_signal_scope", {}).get("capacity_utilization", "行业数据"))})
    if price_yoy is not None:
        indicators.append({"label": "行业价格同比", "value": f"{price_yoy:.1f}%", "trend": "up" if price_yoy > 0 else "down", "source": signals.get("price_yoy_source", signals.get("_signal_scope", {}).get("price_yoy", "行业数据"))})
    if inv_days is not None:
        indicators.append({"label": "行业库存天数", "value": f"{inv_days:.0f}天", "trend": "down" if inv_days < 45 else "flat", "source": signals.get("inventory_days_source", signals.get("_signal_scope", {}).get("inventory_days", "行业数据"))})
    if penetration is not None:
        indicators.append({"label": "行业渗透率", "value": f"{penetration:.1f}%", "trend": "up" if penetration < 30 else "flat", "source": signals.get("penetration_rate_source", signals.get("_signal_scope", {}).get("penetration_rate", "行业数据"))})
    if capex:
        indicators.append({"label": "扩产状态", "value": "进行中" if capex == "underway" else capex, "trend": "up", "source": signals.get("capex_plan_source", "新闻")})

    # 生命周期判定逻辑
    demand_positive = rev_growth is not None and rev_growth >= 15
    demand_hot = rev_growth is not None and rev_growth >= 30
    order_positive = backlog is not None and backlog >= 0
    price_positive = price_yoy is not None and price_yoy >= 0
    supply_tight = util is not None and util >= 85
    inventory_heavy = inv_days is not None and inv_days >= 70

    if penetration is not None and penetration < 15 and (demand_hot or order_positive):
        stage = "导入期"
        stage_short = "导入"
        subtitle = "渗透率低位加速"
        desc = f"行业渗透率 {penetration:.1f}% 仍处低位，需求/订单已开始改善，处于导入期向成长期切换窗口。"
        color = "#38bdf8"
        color_bg = "rgba(56,189,248,0.12)"
        analysis = "导入期核心特征：渗透率低、需求弹性大、供给仍在爬坡。重点跟踪技术验证、客户导入和单位经济性。"
    elif demand_hot and capex == "underway" and (util is None or util >= 80):
        stage = "成长期"
        stage_short = "成长"
        subtitle = "高速扩张"
        desc = f"行业/同业增速 {rev_growth:.0f}% 处于高速区间，产能扩张已启动，订单或需求强劲。行业处于成长期加速阶段。"
        color = "#10b981"
        color_bg = "rgba(16,185,129,0.12)"
        analysis = "成长期核心特征：需求增速 > 产能增速，价格有支撑，毛利率修复中。风险在于扩产进度和地缘政治（如出口许可）。"
    elif demand_positive or (penetration is not None and penetration < 30 and (order_positive or price_positive)):
        stage = "成长期"
        stage_short = "成长"
        subtitle = "稳健增长"
        growth_text = f"{rev_growth:.0f}%" if rev_growth is not None else "数据缺失"
        desc = f"行业/同业增速 {growth_text}，订单或价格出现改善，行业处于成长期。"
        color = "#10b981"
        color_bg = "rgba(16,185,129,0.12)"
        analysis = "成长期：关注产能利用率是否接近瓶颈，以及竞争格局变化。"
    elif (penetration is not None and penetration >= 30 and rev_growth is not None and rev_growth >= 0) or (rev_growth is not None and 0 < rev_growth < 15):
        stage = "成熟期"
        stage_short = "成熟"
        subtitle = "增速放缓"
        growth_text = f"{rev_growth:.0f}%" if rev_growth is not None else "数据缺失"
        desc = f"行业/同业增速 {growth_text} 温和，渗透率或竞争格局显示行业可能进入成熟期。"
        color = "#f59e0b"
        color_bg = "rgba(245,158,11,0.12)"
        analysis = "成熟期：关注市场份额稳定性、成本控制、分红能力。"
    elif (rev_growth is not None and rev_growth <= 0) or (price_yoy is not None and price_yoy < -5) or (inventory_heavy and not supply_tight):
        stage = "衰退期"
        stage_short = "衰退"
        subtitle = "需求收缩"
        growth_text = f"{rev_growth:.0f}%" if rev_growth is not None else "数据缺失"
        desc = f"行业/同业增速 {growth_text}，价格、库存或产能信号显示行业面临需求收缩。"
        color = "#ef4444"
        color_bg = "rgba(239,68,68,0.12)"
        analysis = "衰退期：除非有明确的供给侧出清或技术换代催化剂，否则回避。"
    else:
        stage = "数据缺失"
        stage_short = "?"
        subtitle = "无数据"
        desc = "缺少行业增速、产能、需求等关键指标，无法判定生命周期阶段。"
        color = "#64748b"
        color_bg = "rgba(100,116,139,0.12)"
        analysis = "请补充行业级数据或同业篮子验证数据。"

    return {
        "stage": stage,
        "stage_short": stage_short,
        "subtitle": subtitle,
        "desc": desc,
        "color": color,
        "color_bg": color_bg,
        "indicators": indicators,
        "analysis": analysis,
    }

# ═══════════════════════════════════════════════════════════════
# Step 3: 拐点判定（基于真实信号）
# ═══════════════════════════════════════════════════════════════

def cross_validate_with_industry(real_data):
    """stub: 跨行业交叉验证。后续接入产业链数据库做实质验证。"""
    return {"validation_signals": []}


def determine_inflection_from_real_data(real_data: Optional[Dict]) -> Dict[str, Any]:
    """
    调用 system_a.determine_inflection_state 的行业信号路径。
    """
    if not real_data:
        return {
            "state_name": "数据缺失",
            "state_color": "#64748b",
            "state_color_bg": "rgba(100,116,139,0.12)",
            "matched_signals": [],
            "inflection_data_cards": "",
            "inflection_logic": "未提供真实数据，无法判定拐点状态。",
        }

    signals = _build_system_a_signals(real_data)
    # 调用 system_a 的行业信号路径
    # 优化3: 行业交叉验证信号注入
    cross_result = cross_validate_with_industry(real_data)
    validation_signals = cross_result.get("validation_signals", [])
    if validation_signals:
        existing = signals.get("inflection_signals", [])
        if isinstance(existing, list):
            existing.extend(validation_signals)
        else:
            existing = validation_signals
        signals["inflection_signals"] = existing
    
    result = determine_inflection_state(
        real_signals=signals,
        min_signals_required=2,
    )

    # 构建数据卡片HTML
    data_cards = []
    card_keys = [
        ("revenue_growth", "行业/同业增速", "%", "行业/同业"),
        ("gross_margin", "同业毛利率", "%", "同业篮子"),
        ("order_backlog", "行业订单/需求", "", "行业数据"),
        ("capacity_utilization", "行业产能利用率", "%", "行业数据"),
        ("price_yoy", "行业价格同比", "%", "行业数据"),
        ("inventory_days", "行业库存天数", "天", "行业数据"),
    ]
    for key, label, unit, src_type in card_keys:
        val = signals.get(key)
        if val is not None:
            source_tag = f'<span class="source-tag source-{src_type.lower()}">{src_type}</span>'
            note = signals.get(f"{key}_source", "来源未标注")
            if isinstance(val, (int, float)):
                val_str = f"{val:.1f}"
            else:
                val_str = str(val)
            data_cards.append(
                f'<div class="data-card">'
                f'<div class="data-card-header">'
                f'<span class="data-card-name">{label}</span>'
                f'{source_tag}</div>'
                f'<div class="data-card-value">{val_str}<span class="data-card-unit">{unit}</span></div>'
                f'<div class="data-card-note">{note}</div>'
                f'</div>'
            )
        else:
            data_cards.append(
                f'<div class="data-card">'
                f'<div class="data-card-header">'
                f'<span class="data-card-name">{label}</span>'
                f'<span class="source-tag badge-gray">数据缺失</span></div>'
                f'<div class="data-card-value" style="color:var(--text-muted);">—</div>'
                f'<div class="data-card-note">未找到该指标的真实数据</div>'
                f'</div>'
            )

    inflection_data_cards_html = "\n".join(data_cards)
    matched_signals_list = result.matched_signals if result.matched_signals else []
    matched_signals_text = "、".join(
    [s.get("signal", str(s)) if isinstance(s, dict) else str(s) for s in matched_signals_list]
) if matched_signals_list else "无明确匹配信号"

    return {
        "state_name": result.state_name,
        "state_color": result.color_hex,
        "state_color_bg": f"rgba({int(result.color_hex[1:3],16)},{int(result.color_hex[3:5],16)},{int(result.color_hex[5:7],16)},0.12)",
        "matched_signals": matched_signals_text,
        "matched_signals_list": matched_signals_list,
        "inflection_data_cards": inflection_data_cards_html,
        "inflection_logic": real_data.get("inflection_logic", f"状态: {result.state_name} — 匹配 {len(result.matched_signals)} 个信号"),
    }

# ═══════════════════════════════════════════════════════════════
# Step 4: System B 类型判定（无评分）
# ═══════════════════════════════════════════════════════════════

def determine_system_b_from_real_data(real_data: Optional[Dict]) -> Dict[str, Any]:
    """
    基于真实财务指标进行 System B 类型判定，不输出评分。
    """
    if not real_data:
        return {
            "type": "数据缺失",
            "type_reason": "未提供真实数据",
            "core_contradiction": "无法判定",
            "tracking_metrics": "<li>请补充数据</li>",
            "risks": "<li>数据缺失</li>",
        }

    sb_input = real_data.get("system_b_input", {})
    if not sb_input:
        sb_input = real_data.get("company_signals", {}) or real_data.get("real_signals", {})
    stock_type = real_data.get("system_b_type", "mixed")
    type_reason = real_data.get("system_b_type_reason", "")
    contradiction = real_data.get("system_b_core_contradiction", "")
    tracking = real_data.get("system_b_tracking_metrics", [])
    risks = real_data.get("system_b_risks", [])

    type_desc = get_stock_type_description(stock_type)
    type_name = type_desc.get("name", stock_type)

    tracking_html = "\n".join([f"<li>{x}</li>" for x in tracking]) if tracking else "<li>无明确跟踪指标</li>"
    risks_html = "\n".join([f"<li>{x}</li>" for x in risks]) if risks else "<li>未识别明确风险</li>"

    return {
        "type": type_name,
        "type_en": stock_type,
        "type_reason": type_reason,
        "core_contradiction": contradiction,
        "tracking_metrics": tracking_html,
        "risks": risks_html,
    }

# ═══════════════════════════════════════════════════════════════
# Step 5: 产业链结构（从references加载）
# ═══════════════════════════════════════════════════════════════

def load_preset_yaml(preset_name: str) -> Optional[Dict[str, Any]]:
    """加载preset yaml文件（支持子目录层级结构）"""
    if not preset_name or preset_name == "generic":
        return None
    
    # 1. 先尝试根目录（兼容性）
    path = REF_DIR / "preset-chains" / f"{preset_name}.yaml"
    if path.exists():
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return None
    
    # 2. 递归搜索子目录（layer1-5结构）
    preset_dir = REF_DIR / "preset-chains"
    try:
        import yaml
        for subdir in preset_dir.iterdir():
            if subdir.is_dir():
                candidate = subdir / f"{preset_name}.yaml"
                if candidate.exists():
                    with open(candidate, "r", encoding="utf-8") as f:
                        return yaml.safe_load(f)
    except Exception as e:
        logger.warning("load_preset_yaml(%s) 失败: %s", preset_name, e)
    
    return None

def load_cross_verify_data(cross_verify: Dict[str, Any]) -> Dict[str, Any]:
    """加载交叉验证数据 — 新结构：以产业链环节为单位，从标的池取数据"""
    result = {"upstream": [], "midstream": [], "downstream": [], "external": []}
    if not cross_verify:
        return result
    
    for tier in ["upstream", "midstream", "downstream"]:
        segments = cross_verify.get(tier, [])
        for seg in segments:
            seg_name = seg.get("name", "未命名环节")
            metrics = seg.get("metrics", [])
            pool = seg.get("pool", [])
            
            matched = None
            for code in pool:
                data = load_real_data(code)
                if data:
                    signals = data.get("real_signals", {})
                    matched = {
                        "code": code,
                        "name": data.get("stock_name", code),
                        "revenue_growth": signals.get("revenue_growth"),
                        "gross_margin": signals.get("gross_margin"),
                        "source": "同业财报",
                    }
                    break
            
            result[tier].append({
                "segment_name": seg_name,
                "metrics": metrics,
                "matched": matched,
            })
    
    for ext in cross_verify.get("external_indicators", []):
        result["external"].append(ext)
    
    return result

def build_cross_verify_html(cross_data: Dict[str, Any], preset_name: str) -> str:
    """生成交叉验证分析HTML — 以产业链环节为单位"""
    rows = []
    for tier, label in [("upstream", "上游"), ("midstream", "中游"), ("downstream", "下游")]:
        segments = cross_data.get(tier, [])
        if not segments:
            continue
        for seg in segments:
            seg_name = seg.get("segment_name", "未命名")
            metrics = seg.get("metrics", [])
            matched = seg.get("matched")
            
            if matched:
                rev = f"{matched['revenue_growth']:.1f}%" if matched.get('revenue_growth') is not None else "—"
                gm = f"{matched['gross_margin']:.1f}%" if matched.get('gross_margin') is not None else "—"
                quality_text = f"同业毛利率 {gm}"
            else:
                quality_text = "—"
            
            # 第二列显示环节名+小字标注数据来源
            name_cell = f'<b>{seg_name}</b>'
            if matched:
                name_cell += f'<br/><span style="font-size:11px;color:var(--text-muted)">来源: {matched["name"]}({matched["code"]})</span>'
            
            # 第三列合并指标和同业验证
            metric_details = "<br/>".join(metrics) if metrics else "—"
            if matched and matched.get('revenue_growth') is not None:
                metric_details += f'<br/><span style="color:var(--green)">同业增速 {rev}</span>'
            
            rows.append(f"<tr><td>{label}</td><td>{name_cell}</td><td>{metric_details}</td><td>{quality_text}</td></tr>")
    
    for ext in cross_data.get("external", []):
        rows.append(f"<tr><td>外部</td><td colspan=3>{ext.get('name', '')}: {ext.get('metric', '')}</td></tr>")
    
    if not rows:
        return ""
    
    return (
        '<div class="analysis-box">'
        '<strong style="color:var(--blue);">产业链三层交叉验证：</strong><br/>'
        '<table style="margin-top:8px;font-size:12px;">'
        '<tr><th style="text-align:left;width:60px;">层级</th><th style="text-align:left;">产业链环节</th><th style="text-align:left;">景气指标</th><th style="text-align:left;">盈利质量</th></tr>'
        + "".join(rows) +
        '</table>'
        '</div>'
    )

def load_industry_chain(stock_info: Dict[str, str]) -> str:
    """加载产业链结构说明（精简卡片版）"""
    industry_name = stock_info.get("industry", "")
    chain_position = stock_info.get("chain_position", "")
    preset_name = stock_info.get("preset", "generic")
    
    # 加载预设产业链数据
    preset_data = load_preset_yaml(preset_name)
    
    # 构建产业链卡片（从YAML动态读取）
    cards_html = _build_chain_cards(preset_data, chain_position, industry_name)
    
    # 加载交叉验证数据
    cross_verify_html = ""
    if preset_data:
        cross_data = load_cross_verify_data(preset_data.get("cross_verify"))
        cross_verify_html = build_cross_verify_html(cross_data, preset_name)
    
    return cards_html + cross_verify_html

def _build_chain_cards(preset_data, chain_position: str, industry_name: str) -> str:
    """从YAML动态读取产业链结构卡片（通用版）"""
    
    if not preset_data:
        # 无preset数据时回退到占位符
        return (
            '<div class="card">'
            '<div class="card-title">产业链结构</div>'
            '<p style="color:var(--text-secondary);">'
            f'「{industry_name}」产业链结构卡片待补充。'
            '当前仅光通信/PCB行业已预置完整产业链数据。'
            '</p></div>'
        )
    
    # 从YAML读取上中下游节点
    cards = []
    layers = [
        ("上游", preset_data.get("upstream", {}).get("nodes", [])),
        ("中游", preset_data.get("midstream", {}).get("nodes", [])),
        ("下游", preset_data.get("downstream", {}).get("nodes", [])),
    ]
    
    for layer_name, nodes in layers:
        for node in nodes:
            # 从YAML读取字段，存在则用，不存在则跳过该字段
            card = {
                "title": f"{layer_name} · {node.get('name', '未命名')}",
                "profit": node.get("profit_pool", ""),
                "players": ", ".join(node.get("key_players", [])) if node.get("key_players") else "",
                "barrier": node.get("barrier", ""),
                "bargain": node.get("bargain_power", ""),
            }
            cards.append(card)
    
    if not cards:
        return (
            '<div class="card">'
            '<div class="card-title">产业链结构</div>'
            '<p style="color:var(--text-secondary);">'
            f'「{industry_name}」产业链结构卡片节点为空。'
            '</p></div>'
        )
    
    html_parts = ['<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px;">']
    for card in cards:
        parts = [
            '<div class="card" style="border-left:3px solid #2563eb;">',
            f'<div style="font-weight:600;font-size:14px;color:#e2e8f0;margin-bottom:8px;">{card["title"]}</div>',
        ]
        if card["profit"]:
            parts.append(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">{card["profit"]}</div>')
        if card["players"]:
            parts.append(f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;"><b>核心玩家：</b>{card["players"]}</div>')
        if card["barrier"]:
            parts.append(f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;"><b>壁垒：</b>{card["barrier"]}</div>')
        if card["bargain"]:
            parts.append(f'<div style="font-size:12px;color:#cbd5e1;"><b>议价权：</b>{card["bargain"]}</div>')
        parts.append('</div>')
        html_parts.append("".join(parts))
    html_parts.append('</div>')
    
    # 底部价值分配总结 — 从YAML读取
    val_alloc = preset_data.get("value_allocation", {}) if preset_data else {}
    bargaining = val_alloc.get("bargain_power", "")
    
    # 动态构建价值分配文本
    upstream_nodes = preset_data.get("upstream", {}).get("nodes", []) if preset_data else []
    midstream_nodes = preset_data.get("midstream", {}).get("nodes", []) if preset_data else []
    downstream_nodes = preset_data.get("downstream", {}).get("nodes", []) if preset_data else []
    
    # 提取各层利润池描述
    up_profits = [n.get("profit_pool", "") for n in upstream_nodes if n.get("profit_pool")]
    mid_profits = [n.get("profit_pool", "") for n in midstream_nodes if n.get("profit_pool")]
    down_profits = [n.get("profit_pool", "") for n in downstream_nodes if n.get("profit_pool")]
    
    # 构建价值分配总结文本
    up_summary = f"上游{len(upstream_nodes)}个环节" + (f"（{'; '.join(up_profits[:2])}）" if up_profits else "")
    mid_summary = f"中游{len(midstream_nodes)}个环节" + (f"（{'; '.join(mid_profits[:2])}）" if mid_profits else "")
    down_summary = f"下游{len(downstream_nodes)}个环节" + (f"（{'; '.join(down_profits[:2])}）" if down_profits else "")
    
    # 标的定位文本
    position_text = chain_position if chain_position else "未定位"
    
    html_parts.append(
        '<div style="display:flex;gap:12px;margin-top:8px;">'
        '<div style="flex:1;background:rgba(37,99,235,0.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#94a3b8;">'
        f'<b style="color:#e2e8f0;">价值分配总结：</b>{up_summary}。{mid_summary}。{down_summary}。'
        f'{bargaining}'
        '</div>'
        '<div style="flex:1;background:rgba(37,99,235,0.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#94a3b8;">'
        f'<b style="color:#e2e8f0;">标的定位：</b>当前标的「{position_text}」'
        '处于产业链中游位置，需关注扩产进度、客户认证及上游材料价格传导。'
        '</div>'
        '</div>'
    )
    
    return "\n".join(html_parts)

# ═══════════════════════════════════════════════════════════════
# Structured System A → System B → A×B report renderer
# ═══════════════════════════════════════════════════════════════

_STRUCTURED_REPORT_CSS = """
*{box-sizing:border-box}:root{--ink:#152235;--muted:#65758a;--paper:#f3f6f8;--panel:#fff;--line:#d9e1e8;--blue:#1d5f8a;--cyan:#0f7b83;--amber:#b46a17;--red:#a83f4a;--wash:#eaf1f5;--mono:"SFMono-Regular",Consolas,monospace}
html{scroll-behavior:smooth;overflow-x:hidden}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;overflow-wrap:anywhere}a{color:var(--blue)}a:focus-visible,summary:focus-visible{outline:3px solid #f0a647;outline-offset:3px}.wrap{max-width:1180px;margin:auto;padding:24px 28px 64px}.hero{position:relative;overflow:hidden;padding:34px;border-radius:22px;color:#fff;background:linear-gradient(125deg,#112f49,#175a70 58%,#0b7774);box-shadow:0 18px 44px rgba(28,62,84,.17)}.hero:after{content:"";position:absolute;right:-70px;top:-110px;width:330px;height:330px;border:50px solid rgba(255,255,255,.08);border-radius:50%}.hero>*{position:relative;z-index:1}.hero h1{margin:8px 0;font-size:clamp(30px,5vw,54px);line-height:1.06;letter-spacing:-.045em}.hero p{max-width:760px;margin:0;color:#d7e7ee}.meta-line{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}.tag{display:inline-flex;padding:4px 9px;border-radius:999px;background:#e6edf2;color:#40566a;font:700 11px/1.4 var(--mono)}.hero .tag{background:rgba(255,255,255,.14);color:#fff}.section{margin-top:18px;padding:24px 26px;background:var(--panel);border:1px solid var(--line);border-radius:17px}.section h2{margin:0 0 14px;font-size:20px;letter-spacing:-.02em}.section h3{margin:0 0 8px;font-size:14px}.kicker{font:700 11px/1.3 var(--mono);letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}.thesis{font-size:19px;line-height:1.55;max-width:900px;margin:0}.chain,.dashboard,.cards,.two{display:grid;gap:12px}.chain{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}.chain-card,.card,.mini{border:1px solid var(--line);border-radius:12px;padding:15px;background:#fbfcfd}.chain-card dl,.mini dl{display:grid;grid-template-columns:92px 1fr;gap:5px 9px;margin:10px 0 0}.chain-card dt,.mini dt{color:var(--muted)}.chain-card dd,.mini dd{margin:0}.dashboard{grid-template-columns:1fr 1fr}.dial{position:relative;min-height:190px;padding:18px;border:1px solid var(--line);border-radius:15px;background:linear-gradient(180deg,#fbfdfe,#f4f8fa);overflow:hidden}.dial:after{content:"";position:absolute;width:130px;height:130px;right:-26px;bottom:-44px;border:22px solid var(--accent,var(--blue));border-radius:50%;opacity:.16}.dial strong{display:block;margin:22px 0 7px;font-size:30px;letter-spacing:-.04em}.dial.a1{--accent:var(--blue)}.dial.a2{--accent:var(--amber)}.lifecycle{margin-top:10px;padding:10px 13px;border-left:4px solid var(--cyan);background:#edf7f7}.cards{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}.card strong{display:block;margin:5px 0}.two{grid-template-columns:1fr 1fr}.callout{padding:16px 18px;border-left:5px solid var(--amber);background:#fff7e9;border-radius:9px}.risk{border-left-color:var(--red);background:#fff1f3}.clean{margin:0;padding-left:19px}.clean li+li{margin-top:7px}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;border-collapse:collapse;min-width:720px}th,td{padding:10px 11px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}th{background:#edf3f6;color:#536779;font:700 11px var(--mono)}tr:last-child td{border-bottom:0}.mobile-ledger{display:none}.muted{color:var(--muted)}.status{font-weight:750}.footer{padding:25px 2px;color:var(--muted);font-size:12px}
@media(max-width:700px){.wrap{padding:12px 11px 42px}.hero{padding:25px 20px;border-radius:17px}.section{padding:19px 17px}.dashboard,.two{grid-template-columns:1fr}.dial{min-height:150px}.chain,.cards{grid-template-columns:1fr}.table-wrap{display:none}.mobile-ledger{display:grid;gap:9px}.mobile-ledger .mini dl{grid-template-columns:80px 1fr}.thesis{font-size:17px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{animation:none!important;transition:none!important}}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}.hero,.section{box-shadow:none;break-inside:avoid}}
"""


def _safe_report_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "待补"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _legacy_report_payload(
    stock_info: Mapping[str, Any],
    real_data: Optional[Mapping[str, Any]],
    lifecycle: Mapping[str, Any],
    inflection: Mapping[str, Any],
    system_b: Mapping[str, Any],
    chain_summary: Optional[List[Mapping[str, Any]]] = None,
    *,
    framework_only: bool = False,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Adapt the legacy CLI values to the structured report contract.

    ``run_pipeline`` predates the packet runtime and still computes a few
    values directly.  The report renderer, however, deliberately has one
    self-contained input contract.  Keeping this adapter local to the CLI
    lets both the framework-degraded and data-backed paths use the same
    renderer without making the legacy template a second report source.
    """
    data = dict(real_data or {})
    product_map = [
        dict(item)
        for item in data.get("product_industry_map") or []
        if isinstance(item, Mapping)
    ]
    evidence = [
        dict(item)
        for item in data.get("evidence") or []
        if isinstance(item, Mapping)
    ]
    # Some older JSON fixtures only expose ``industry_data`` rows.  Preserve
    # those facts as evidence rather than silently dropping them from the new
    # report's traceability ledger.
    for index, row in enumerate(data.get("industry_data") or [], 1):
        if not isinstance(row, Mapping):
            continue
        field = str(
            row.get("field_path")
            or row.get("indicator")
            or row.get("metric")
            or f"industry_data.{index}"
        )
        evidence.append(
            {
                "field_path": field,
                "scope": "industry",
                "value": row.get("value") or row.get("raw_value"),
                "report_period": row.get("report_period") or row.get("date"),
                "as_of_date": row.get("as_of_date") or row.get("date"),
                "source_type": row.get("source_type") or "industry_data",
                "source_title": row.get("source_title") or row.get("source") or "来源待补",
            }
        )

    target = {
        "stock_code": stock_info.get("stock_code"),
        "stock_name": stock_info.get("stock_name"),
        "industry": stock_info.get("industry") or "产业单元待补",
        "sub_sector": stock_info.get("sub_industry") or "",
        "preset": stock_info.get("preset") or "generic",
        "input_type": "stock_code",
    }
    as_of_date = (
        data.get("as_of_date")
        or data.get("generated_at")
        or datetime.now().strftime("%Y-%m-%d")
    )
    packet: Dict[str, Any] = {
        "schema_version": "industry-data/0.2",
        "target": target,
        "industry_signals": dict(data.get("industry_signals") or {}),
        "peer_basket_signals": dict(data.get("peer_basket_signals") or {}),
        "peer_basket_meta": dict(data.get("peer_basket_meta") or {}),
        "company_signals": dict(data.get("company_signals") or data.get("real_signals") or {}),
        "product_industry_map": product_map,
        "valuation_context": dict(data.get("valuation_context") or {}),
        "market_context": dict(data.get("market_context") or {}),
        "evidence": evidence,
        "needs_data": list(data.get("needs_data") or []),
        "as_of_date": as_of_date,
        "source_mode": "framework_only" if framework_only else str(data.get("source_mode") or "project"),
        "chain_summary": [dict(item) for item in (chain_summary or []) if isinstance(item, Mapping)],
    }
    if framework_only:
        packet["framework_only"] = True

    admitted_system_a = dict(data.get("system_a") or {})
    system_a_usable = bool(admitted_system_a.get("usable")) and not framework_only

    def admitted_dimension(name: str) -> Dict[str, Any]:
        value = admitted_system_a.get(name)
        if system_a_usable and isinstance(value, Mapping) and value.get("label"):
            return dict(value)
        return {"state": "undetermined", "label": "待判定", "evidence_refs": []}

    system_a = {
        "readiness": (
            admitted_system_a.get("readiness")
            if system_a_usable
            else "framework_only"
        ),
        "usable": system_a_usable,
        "prosperity": admitted_dimension("prosperity"),
        "inflection": admitted_dimension("inflection"),
        "lifecycle": admitted_dimension("lifecycle"),
    }
    business_exposure = product_map
    valuation = dict(data.get("valuation_context") or {})
    stock_code = str(target.get("stock_code") or "").upper()
    stock_name = str(target.get("stock_name") or "")
    try:
        from core.auto_detect_preset import _is_stock_code, resolve_stock_identity

        resolved_code, _ = resolve_stock_identity(stock_code or stock_name)
        recognized_company = _is_stock_code(stock_code) or _is_stock_code(resolved_code)
    except (ImportError, ValueError, TypeError):
        # Fail closed to the legacy A-share form if the local identity helper
        # cannot be loaded; company facts below can still select System B.
        recognized_company = bool(
            re.fullmatch(r"(?:SH|SZ|BJ)?\d{6}(?:\.(?:SH|SZ|BJ))?", stock_code)
        )
    company_branch = bool(
        recognized_company
        or packet["company_signals"]
        or product_map
    )
    system_b_output = {
        "stock_type": system_b.get("type") or system_b.get("stock_type") or "未判定",
        "core_contradiction": system_b.get("description") or "公司级财务输入待补。",
        "business_exposure": business_exposure,
        "revenue_driver": valuation.get("revenue_driver") or "未取得分业务收入主线证据",
        "profit_driver": valuation.get("profit_driver") or "未取得分业务利润主线证据",
        "valuation_driver": valuation.get("valuation_driver") or "证据不足",
        "risks": ["框架降级：缺少可验证的行业与公司数据。"] if framework_only else [],
        "next_confirmation": valuation.get("next_confirmation") or "补充行业证据与分业务兑现数据。",
    }
    if not company_branch:
        summary = "行业分支仅运行 System A；当前缺少通过准入的行业证据。"
    elif framework_only:
        summary = "资料状态：框架降级，System A 与 System B 均待补。"
    elif business_exposure:
        summary = (
            f"产业景气为{system_a['prosperity']['label']}、拐点为{system_a['inflection']['label']}；"
            f"已建立{len(business_exposure)}项产品—产业回指，仍需验证收入、利润与定价兑现。"
        )
    else:
        summary = "行业判断已生成，但产品—产业回指与公司兑现证据仍待补。"
    combined = {
        "status": "insufficient_data" if framework_only else "partial",
        "summary": summary,
        "short_status": (
            "行业分支 · System A 待补"
            if not company_branch
            else "框架降级 · 待补行业与公司证据"
            if framework_only
            else f"System A {system_a['prosperity']['label']} · {system_a['inflection']['label']}"
        ),
        "business_crosswalk": [],
        "next_confirmation": system_b_output["next_confirmation"],
        "invalidation": "补齐数据前不得形成方向性结论。" if framework_only else "核心行业指标反转或公司兑现未达预期。",
    }
    result = {
        "direction": "neutral" if framework_only else "unknown",
        "confidence": 0.2 if framework_only else 0.25,
        "reasoning": summary,
        "meta": {
            "output_version": "0.3",
            "readiness": "framework_only" if framework_only else "legacy",
            "stock_name": target["stock_name"],
            "stock_code": target["stock_code"],
            "industry": target["industry"],
            "source_mode": packet["source_mode"],
            "as_of_date": as_of_date,
            "evidence": evidence,
            "needs_data": bool(framework_only or packet["needs_data"]),
            "system_b_ready": bool(company_branch and not framework_only and packet["company_signals"]),
            "company_branch": company_branch,
            "product_industry_map": product_map,
            "system_a": system_a,
            "system_b": system_b_output,
            "combined_conclusion": combined,
            "chain_summary": packet["chain_summary"],
            "report_quality": {
                "content_map_checked": False,
                "attempts": 0,
                "quality_check_attempts": 0,
                "refinement_attempts": 0,
                "max_refinement_attempts": 1,
                "issues_before": [],
                "issues_after": [],
                "unresolved": [],
            },
        },
    }
    return packet, result


def _report_source(evidence: Mapping[str, Any]) -> str:
    title = escape(str(
        evidence.get("source_title")
        or evidence.get("source_name")
        or evidence.get("source_type")
        or "来源待补"
    ))
    url = str(evidence.get("source_url") or "")
    if url.startswith(("https://", "http://")):
        return (
            f'<a href="{escape(url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{title}</a>'
        )
    return title


def render_analysis_report(
    packet: Mapping[str, Any],
    skill_result: Mapping[str, Any],
    generated_at: Optional[str] = None,
) -> str:
    """Render one concise, self-contained System A → System B → A×B report."""
    packet = dict(packet or {})
    result = dict(skill_result or {})
    meta = dict(result.get("meta") or {})
    target = dict(packet.get("target") or {})
    system_a = dict(meta.get("system_a") or {})
    prosperity = dict(system_a.get("prosperity") or meta.get("cyclical_phase") or {})
    inflection = dict(system_a.get("inflection") or meta.get("inflection_state") or {})
    lifecycle = dict(system_a.get("lifecycle") or meta.get("structural_lifecycle") or {})
    system_b = dict(meta.get("system_b") or {})
    combined = dict(meta.get("combined_conclusion") or {})
    product_map = list(
        meta.get("product_industry_map")
        or packet.get("product_industry_map")
        or []
    )
    evidence = [
        dict(item)
        for item in (meta.get("evidence") or packet.get("evidence") or [])
        if isinstance(item, Mapping)
    ]
    trace_nodes = [
        dict(item)
        for item in dict(meta.get("reasoning_trace") or {}).get("nodes") or []
        if isinstance(item, Mapping)
    ]
    admitted = [
        item for item in trace_nodes
        if item.get("admission_status") == "admitted"
    ][:5]
    company_branch = (
        bool(meta.get("company_branch"))
        if "company_branch" in meta
        else bool(
            meta.get("system_b_ready")
            or product_map
            or system_b.get("business_exposure")
        )
    )
    source_mode = str(packet.get("source_mode") or meta.get("source_mode") or "")
    data_route = (
        "已有资料 + WEB"
        if any(token in source_mode for token in ("web", "curated", "live"))
        else "已有资料" if evidence else "资料不足"
    )
    generated = generated_at or datetime.now().isoformat(timespec="seconds")
    name = (
        target.get("stock_name")
        or meta.get("stock_name")
        or target.get("stock_code")
        or "行业研究"
    )
    industry = target.get("industry") or meta.get("industry") or "产业单元待补"
    # The first screen owns a short state/contradiction.  The full A×B
    # transmission summary belongs to its dedicated section below; using it
    # here as well creates a visible duplicate claim.
    thesis = (
        combined.get("short_status")
        or system_b.get("core_contradiction")
        or f"System A：{_safe_report_value(prosperity.get('label'))} · { _safe_report_value(inflection.get('label')) }"
        or "资料不足，暂不形成方向性结论。"
    )

    chain_summary = list(meta.get("chain_summary") or packet.get("chain_summary") or [])
    if product_map:
        chain_html = "".join(
            '<article class="chain-card" data-claim-id="map-{idx}">'
            '<span class="kicker">{unit}</span><h3>{product}</h3><dl>'
            '<dt>公司位置</dt><dd>{position}</dd>'
            '<dt>直接客户</dt><dd>{customer}</dd>'
            '<dt>进入系统</dt><dd>{system}</dd>'
            '<dt>终端需求</dt><dd>{demand}</dd>'
            '<dt>兑现状态</dt><dd>{status}</dd></dl></article>'.format(
                idx=index,
                unit=escape(_safe_report_value(item.get("industry_unit"))),
                product=escape(_safe_report_value(item.get("product"))),
                position=escape(_safe_report_value(item.get("company_position"))),
                customer=escape(_safe_report_value(item.get("direct_customer"))),
                system=escape(_safe_report_value(item.get("downstream_system"))),
                demand=escape(_safe_report_value(item.get("end_demand"))),
                status=escape(_safe_report_value(item.get("status"))),
            )
            for index, item in enumerate(product_map, 1)
        )
    elif chain_summary:
        layer_labels = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}
        chain_html = "".join(
            '<article class="chain-card" data-claim-id="chain-{idx}">'
            '<span class="kicker">{layer}</span><h3>{node}</h3><dl>'
            '<dt>关键参与者</dt><dd>{players}</dd>'
            '<dt>利润池</dt><dd>{profit}</dd></dl></article>'.format(
                idx=index,
                layer=escape(layer_labels.get(str(item.get("layer") or ""), str(item.get("layer") or "产业链"))),
                node=escape(_safe_report_value(item.get("node"))),
                players=escape(_safe_report_value(", ".join(item.get("key_players") or []))),
                profit=escape(_safe_report_value(item.get("profit_pool"))),
            )
            for index, item in enumerate(chain_summary, 1)
            if isinstance(item, Mapping)
        )
    else:
        chain_html = (
            '<article class="chain-card"><span class="kicker">待补</span>'
            '<h3>产品—产业地图尚未建立</h3><p class="muted">'
            "需补产品功能、公司层级、直接客户、下游系统与终端需求。</p></article>"
        )

    signal_cards = "".join(
        '<article class="card" data-claim-id="signal-{idx}">'
        '<span class="kicker">{role}</span><strong>{indicator}</strong>'
        '<span class="status">{observation}</span>'
        '<p class="muted">{period} · {source}</p></article>'.format(
            idx=index,
            role=escape(str(item.get("role_name") or item.get("role") or "证据")),
            indicator=escape(str(
                item.get("indicator_id")
                or item.get("field_path")
                or "待补"
            )),
            observation=escape(str(item.get("observation") or "unknown")),
            period=escape(str(
                item.get("report_period")
                or item.get("as_of_date")
                or "日期待补"
            )),
            source=escape(str(
                item.get("source_title")
                or item.get("source_type")
                or "来源待补"
            )),
        )
        for index, item in enumerate(admitted, 1)
    ) or (
        '<article class="card"><strong>决定性行业证据待补</strong>'
        '<p class="muted">当前只展示准入后的证据；公司材料不能替代行业证据。</p></article>'
    )

    unit_views = dict(
        meta.get("system_a_by_industry_unit")
        or meta.get("system_a_views")
        or {}
    )
    unit_cards = "".join(
        f'<article class="card" data-claim-id="unit-a-{index}">'
        f'<span class="kicker">{escape(str(unit_name))}</span>'
        f'<strong>{escape(_safe_report_value(dict(view.get("prosperity") or {}).get("label")))}</strong>'
        f'<p class="muted">拐点：{escape(_safe_report_value(dict(view.get("inflection") or {}).get("label")))} · '
        f'生命周期：{escape(_safe_report_value(dict(view.get("lifecycle") or {}).get("label")))}</p>'
        f'<p class="muted">{escape(_safe_report_value(view.get("reason") or view.get("readiness")))}</p>'
        '</article>'
        for index, (unit_name, view) in enumerate(unit_views.items(), 1)
        if isinstance(view, Mapping)
    )
    unit_section = (
        f'<section class="section" id="industry-unit-system-a"><span class="kicker">System A · per industry unit</span>'
        f'<h2>逐产业单元判断</h2><div class="cards">{unit_cards}</div></section>'
        if unit_cards
        else ""
    )

    table_rows: List[str] = []
    mobile_rows: List[str] = []
    for index, item in enumerate(evidence, 1):
        field = str(
            item.get("field_path")
            or item.get("claim_or_metric")
            or f"evidence-{index}"
        )
        period = (
            item.get("report_period")
            or item.get("period")
            or item.get("as_of_date")
            or "待补"
        )
        value = (
            item.get("value")
            if item.get("value") not in (None, "")
            else item.get("raw_values")
        )
        scope = (
            item.get("scope")
            or (field.split(".", 1)[0] if "." in field else "unknown")
        )
        source = _report_source(item)
        table_rows.append(
            f"<tr><td><code>{escape(field)}</code></td>"
            f"<td>{escape(_safe_report_value(period))}</td>"
            f"<td>{escape(_safe_report_value(value))}</td>"
            f"<td>{escape(_safe_report_value(scope))}</td><td>{source}</td></tr>"
        )
        mobile_rows.append(
            f'<article class="mini"><strong>{escape(field)}</strong><dl>'
            f'<dt>期间</dt><dd>{escape(_safe_report_value(period))}</dd>'
            f'<dt>值/口径</dt><dd>{escape(_safe_report_value(value))}</dd>'
            f'<dt>作用域</dt><dd>{escape(_safe_report_value(scope))}</dd>'
            f"<dt>来源</dt><dd>{source}</dd></dl></article>"
        )
    if not table_rows:
        table_rows.append(
            '<tr><td colspan="5">待补：关键证据、来源定位与时效。</td></tr>'
        )
        mobile_rows.append(
            '<article class="mini">待补：关键证据、来源定位与时效。</article>'
        )

    risks = list(dict.fromkeys(
        list(system_b.get("risks") or [])
        + list(meta.get("uncertainties") or [])
    ))
    risks_html = "".join(
        f"<li>{escape(str(item))}</li>" for item in risks[:8]
    ) or "<li>暂无已验证风险；不等于无风险。</li>"

    company_html = ""
    if company_branch:
        exposure = list(system_b.get("business_exposure") or [])
        exposure_html = "".join(
            f'<article class="mini"><strong>'
            f'{escape(_safe_report_value(item.get("product")))}</strong><p>'
            f'{escape(_safe_report_value(item.get("industry_unit")))} · '
            f'{escape(_safe_report_value(item.get("status")))}</p></article>'
            for item in exposure
        ) or (
            '<article class="mini">待补产品—产业回指，'
            "System B 不向 System A 反向填数。</article>"
        )
        crosswalk = list(combined.get("business_crosswalk") or [])
        crosswalk_html = "".join(
            f'<article class="mini" data-claim-id="crosswalk-{index}"><strong>'
            f'{escape(_safe_report_value(item.get("industry_unit")))}</strong><p>'
            f'{escape(_safe_report_value(item.get("product")))} · '
            f'A景气：{escape(_safe_report_value(item.get("prosperity")))} · '
            f'A拐点：{escape(_safe_report_value(item.get("inflection")))}</p><p>'
            f'{escape(_safe_report_value(item.get("transmission_status")))}</p></article>'
            for index, item in enumerate(crosswalk, 1)
            if isinstance(item, Mapping)
        ) or '<article class="mini">待补逐产业单元 A×B 回指。</article>'
        company_html = f"""
<section class="section" id="system-b"><span class="kicker">System B · Company</span><h2>公司暴露与兑现</h2><div class="two"><div><h3>{escape(_safe_report_value(system_b.get("stock_type")))}</h3><p>{escape(_safe_report_value(system_b.get("core_contradiction")))}</p></div><div class="cards">{exposure_html}</div></div></section>
<section class="section" id="valuation-drivers"><span class="kicker">Revenue ≠ Profit ≠ Valuation</span><h2>三条主线</h2><div class="cards"><article class="card"><span class="kicker">收入</span><strong>{escape(_safe_report_value(system_b.get("revenue_driver")))}</strong></article><article class="card"><span class="kicker">利润</span><strong>{escape(_safe_report_value(system_b.get("profit_driver")))}</strong></article><article class="card"><span class="kicker">市值</span><strong>{escape(_safe_report_value(system_b.get("valuation_driver")))}</strong></article></div></section>
<section class="section" id="combined-conclusion"><span class="kicker">A × B</span><h2>传导差与错配</h2><div class="cards">{crosswalk_html}</div><p class="thesis" style="margin-top:14px">{escape(_safe_report_value(combined.get("summary")))}</p><div class="two" style="margin-top:14px"><div class="callout"><h3>下一验证</h3>{escape(_safe_report_value(combined.get("next_confirmation")))}</div><div class="callout risk"><h3>失效条件</h3>{escape(_safe_report_value(combined.get("invalidation")))}</div></div></section>"""

    peer_period = str(
        dict(packet.get("peer_basket_meta") or {}).get("report_period")
        or "待补"
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(str(name))} · 产业链分析</title><style>{_STRUCTURED_REPORT_CSS}</style></head>
<body><main class="wrap">
<header class="hero" id="report-header"><span class="kicker" style="color:#c9e1e8">Industrial Sentinel · {escape(data_route)}</span><h1>{escape(str(name))}</h1><p>{escape(str(industry))} · 先产业、后公司、再交叉</p><div class="meta-line"><span class="tag">截至 {escape(str(packet.get("as_of_date") or "待补"))}</span><span class="tag">报告期 {escape(peer_period)}</span><span class="tag">readiness {escape(str(meta.get("readiness") or "unknown"))}</span></div></header>
<section class="section" id="industry-thesis" data-claim-id="thesis-1"><span class="kicker">Core thesis</span><h2>结论</h2><p class="thesis">{escape(str(thesis))}</p></section>
<section class="section" id="chain-map"><span class="kicker">Product → Industry unit</span><h2>产业链结构 · 产品—产业地图</h2><div class="chain">{chain_html}</div></section>
<section class="section" id="system-a"><span class="kicker">System A · Industry only</span><h2>产业景气与产业链拐点</h2><div class="dashboard"><article class="dial a1" id="prosperity-dashboard" data-claim-id="a1"><span class="kicker">A1 · 现在强不强</span><strong>{escape(_safe_report_value(prosperity.get("label")))}</strong><p class="muted">只由准入后的 industry / peer 证据驱动。</p></article><article class="dial a2" id="inflection-dashboard" data-claim-id="a2"><span class="kicker">A2 · 方向是否改变</span><strong>{escape(_safe_report_value(inflection.get("label")))}</strong><p class="muted">领先与确认信号分开，不与景气度机械加权。</p></article></div><div class="lifecycle">生命周期：<strong>{escape(_safe_report_value(lifecycle.get("label")))}</strong></div></section>
{unit_section}
<section class="section" id="industry-signals"><span class="kicker">Decision evidence</span><h2>决定性行业证据</h2><div class="cards">{signal_cards}</div></section>
{company_html}
<section class="section" id="risks"><span class="kicker">Counter evidence</span><h2>风险、反证与缺口</h2><div class="callout risk"><ul class="clean">{risks_html}</ul></div></section>
<section class="section" id="evidence-ledger"><span class="kicker">Traceability</span><h2>证据账本</h2><div class="table-wrap"><table><thead><tr><th>字段/主张</th><th>期间</th><th>值/口径</th><th>作用域</th><th>来源</th></tr></thead><tbody>{''.join(table_rows)}</tbody></table></div><div class="mobile-ledger">{''.join(mobile_rows)}</div></section>
<footer class="footer">生成时间 {escape(generated)} · 分析截至 {escape(str(packet.get("as_of_date") or "待补"))} · 最新报告期 {escape(peer_period)} · 不构成投资建议。</footer>
</main></body></html>"""


# ═══════════════════════════════════════════════════════════════
# Step 6: Legacy template HTML 生成
# ═══════════════════════════════════════════════════════════════

def render_html_report(
    stock_info: Dict[str, str],
    lifecycle: Dict[str, Any],
    inflection: Dict[str, Any],
    system_b: Dict[str, Any],
    industry_data: List[Dict],
    chain_html: str,
) -> str:
    """使用统一模板生成 HTML"""
    template_path = TEMPLATES_DIR / "pipeline-output.html"
    if not template_path.exists():
        logger.error("HTML 模板不存在: %s", template_path)
        return ""

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 生成生命周期指标HTML
    lifecycle_indicators_html = ""
    for ind in lifecycle.get("indicators", []):
        lifecycle_indicators_html += (
            f'<div style="padding:10px;border-radius:8px;background:rgba(255,255,255,0.03);border:1px solid var(--border);">'
            f'<div style="font-size:11px;color:var(--text-muted);">{ind["label"]}</div>'
            f'<div style="font-size:18px;font-weight:700;color:var(--text-primary);">{ind["value"]}</div>'
            f'<div style="font-size:10px;color:var(--text-muted);">{ind.get("source", "")}</div>'
            f'</div>'
        )

    # 生成行业数据表格行
    industry_rows = ""
    for row in industry_data:
        src_tag = f'<span class="source-tag source-{row.get("source_type", "news").lower()}">{row.get("source_type", "新闻")}</span>'
        analysis_cell = row.get("analysis", "")
        if not analysis_cell:
            # 自动生成简要分析
            yoy = row.get("yoy_change", "")
            if "+" in str(yoy):
                analysis_cell = "正向增长"
            elif "-" in str(yoy):
                analysis_cell = "同比下降，需关注原因"
            else:
                analysis_cell = "—"
        industry_rows += (
            f'<tr>'
            f'<td>{row.get("indicator", row.get("metric", ""))}</td>'
            f'<td><strong>{row.get("value", "")}</strong> <span style="color:var(--text-muted);font-size:12px;">{row.get("yoy_change", "")}</span></td>'
            f'<td>{src_tag}</td>'
            f'<td>{row.get("date", "")}</td>'
            f'<td>{analysis_cell}</td>'
            f'</tr>'
        )

    # 替换模板变量
    replacements = {
        "{{stock_name}}": stock_info.get("stock_name", ""),
        "{{stock_code}}": stock_info.get("stock_code", ""),
        "{{industry_name}}": stock_info.get("industry", ""),
        "{{chain_position}}": stock_info.get("chain_position", ""),
        "{{sub_sector}}": stock_info.get("sub_sector", ""),
        "{{data_source_line}}": "数据来源: 财报 + 行业研报 + 新闻",
        "{{generated_at}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{lifecycle_stage}}": lifecycle.get("stage", "数据缺失"),
        "{{lifecycle_stage_short}}": lifecycle.get("stage_short", "?"),
        "{{lifecycle_subtitle}}": lifecycle.get("subtitle", ""),
        "{{lifecycle_desc}}": lifecycle.get("desc", ""),
        "{{lifecycle_color}}": lifecycle.get("color", "#64748b"),
        "{{lifecycle_color_bg}}": lifecycle.get("color_bg", "rgba(100,116,139,0.12)"),
        "{{lifecycle_indicators}}": lifecycle_indicators_html,
        "{{lifecycle_analysis_points}}": lifecycle.get("analysis", ""),
        "{{state_name}}": inflection.get("state_name", "数据缺失"),
        "{{state_color}}": inflection.get("state_color", "#64748b"),
        "{{state_color_bg}}": inflection.get("state_color_bg", "rgba(100,116,139,0.12)"),
        "{{matched_signals}}": inflection.get("matched_signals", ""),
        "{{inflection_data_cards}}": inflection.get("inflection_data_cards", ""),
        "{{inflection_logic}}": inflection.get("inflection_logic", ""),
        "{{industry_chain_structure}}": chain_html,
        "{{industry_data_rows}}": industry_rows,
        "{{system_b_type}}": system_b.get("type", "数据缺失"),
        "{{system_b_type_reason}}": system_b.get("type_reason", ""),
        "{{system_b_core_contradiction}}": system_b.get("core_contradiction", ""),
        "{{system_b_tracking_metrics}}": system_b.get("tracking_metrics", ""),
        "{{system_b_risks}}": system_b.get("risks", ""),
        "{{data_source_footer}}": "数据来源: 财报 + 行业研报 + 公开数据 | 本报告仅供研究参考，不构成投资建议",
    }

    html = template
    for key, val in replacements.items():
        html = html.replace(key, str(val))

    return html

# ═══════════════════════════════════════════════════════════════
# 数据缺失降级：基于 preset YAML 生成框架级信号
# ═══════════════════════════════════════════════════════════════

def build_framework_from_preset(stock_code: str, preset_name: str) -> Dict[str, Any]:
    """
    当 real_data 缺失时，基于 preset YAML 生成框架级信息。
    降级信号 confidence 降低，但仍能输出产业链结构。
    """
    yaml_data = load_preset_yaml(preset_name) or {}

    stock_info = {
        "stock_code": stock_code,
        "stock_name": stock_code,
        "industry": yaml_data.get("industry_name", preset_name),
        "preset": preset_name,
        "sub_industry": "",
        "chain_position": "",
    }

    # 降级生命周期：标注为框架模式
    lifecycle = {
        "stage": "框架降级",
        "stage_short": "?",
        "subtitle": "缺少真实财务数据",
        "desc": "未找到 real_data.json，基于 preset YAML 输出产业链框架信息。请补充财报数据以启用完整生命周期判定。",
        "color": "#f59e0b",
        "color_bg": "rgba(245,158,11,0.12)",
        "indicators": [
            {"label": "真实数据", "value": "缺失", "source": "框架降级"},
        ],
        "analysis": "待采集真实数据后重新运行 pipeline。",
    }

    # 降级拐点
    inflection = {
        "state_name": "数据缺失",
        "state_color": "#64748b",
        "state_color_bg": "rgba(100,116,139,0.12)",
        "matched_signals": [],
        "inflection_logic": "未提供真实数据，基于 preset 框架输出。",
        "signals": {},
        "policy_catalyst": {},
        "reasoning": f"产业链框架分析 | preset={preset_name} | 数据状态: 待采集",
    }

    # 降级 System B
    system_b = {
        "type": "未判定",
        "description": "缺少真实财务数据，无法判定个股类型。",
        "weight_profile": {},
    }

    # 从 YAML 提取产业链结构信息
    chain_summary = []
    for section_name in ("upstream", "midstream", "downstream"):
        section = yaml_data.get(section_name, {})
        nodes = section.get("nodes", []) if isinstance(section, dict) else []
        for node in nodes:
            players = node.get("key_players", [])
            profit = node.get("profit_pool", "")
            chain_summary.append({
                "layer": section_name,
                "node": node.get("name", ""),
                "key_players": players,
                "profit_pool": profit,
            })

    return {
        "stock_info": stock_info,
        "lifecycle": lifecycle,
        "inflection": inflection,
        "system_b": system_b,
        "chain_summary": chain_summary,
        "data_quality": "framework_only",
        "yaml_data": yaml_data,
    }

def _chain_summary_to_html(chain_summary: list) -> str:
    """将产业链摘要转为卡片式 HTML（与 _build_chain_cards 风格统一）。"""
    if not chain_summary:
        return "<p>暂无可用的产业链结构数据。</p>"
    
    layers_map = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}
    
    # 按层级分组
    sorted_items = {"upstream": [], "midstream": [], "downstream": []}
    for item in chain_summary:
        layer = item.get("layer", "midstream")
        if layer not in sorted_items:
            sorted_items[layer] = []
        sorted_items[layer].append(item)
    
    html_parts = ['<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:16px;">']
    for layer_key in ["upstream", "midstream", "downstream"]:
        for item in sorted_items.get(layer_key, []):
            layer_cn = layers_map.get(layer_key, layer_key)
            players = ", ".join(item.get("key_players", [])[:5])
            barrier = item.get("barrier", "")
            bargain = item.get("bargain_power", "")
            
            parts = [
                '<div class="card" style="border-left:3px solid #2563eb;">',
                f'<div style="font-weight:600;font-size:14px;color:#e2e8f0;margin-bottom:8px;">{layer_cn} · {item.get("node", "")}</div>',
            ]
            if item.get("profit_pool"):
                parts.append(f'<div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">{item["profit_pool"]}</div>')
            if players:
                parts.append(f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;"><b>核心玩家：</b>{players}</div>')
            if barrier:
                parts.append(f'<div style="font-size:12px;color:#cbd5e1;margin-bottom:4px;"><b>壁垒：</b>{barrier}</div>')
            if bargain:
                parts.append(f'<div style="font-size:12px;color:#cbd5e1;"><b>议价权：</b>{bargain}</div>')
            parts.append('</div>')
            html_parts.append("".join(parts))
    html_parts.append('</div>')
    
    # 底部总览（对齐 _build_chain_cards 风格）
    up_count = len(sorted_items.get("upstream", []))
    mid_count = len(sorted_items.get("midstream", []))
    down_count = len(sorted_items.get("downstream", []))
    html_parts.append(
        '<div style="display:flex;gap:12px;margin-top:8px;">'
        '<div style="flex:1;background:rgba(37,99,235,0.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#94a3b8;">'
        f'<b style="color:#e2e8f0;">产业链概览（框架降级）：</b>上游{up_count}环节 · 中游{mid_count}环节 · 下游{down_count}环节。'
        '数据缺失，基于预设产业链框架生成。</div>'
        '<div style="flex:1;background:rgba(37,99,235,0.08);border-radius:8px;padding:10px 14px;font-size:12px;color:#94a3b8;">'
        '<b style="color:#e2e8f0;">数据状态：</b>框架降级模式 — 使用预设产业链结构，缺乏真实财务数据支撑。建议回填核心指标后重新生成。</div>'
        '</div>'
    )
    return "\n".join(html_parts)

# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def save_history(stock_code: str, snapshot: Dict[str, Any]):
    """P2-2: 将运行快照追加到历史记录 (data/history/<code>.jsonl)"""
    history_dir = DATA_DIR / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    hist_file = history_dir / f"{stock_code}.jsonl"
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stock_code": stock_code,
        **snapshot,
    }
    try:
        with open(hist_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\\n")
        logger.info(f"历史记录已保存: {hist_file} ({hist_file.stat().st_size} bytes)")
    except Exception as e:
        logger.warning(f"历史记录保存失败: {e}")

def run_pipeline(stock_code: str, real_data: Optional[Dict[str, Any]] = None, generate_html: bool = True) -> str:
    """运行完整流水线，返回生成的HTML文件路径

    Args:
        stock_code: 股票代码
            real_data: 可选，由调用方传入的实时数据 dict。若提供则直接使用，
                       不再从本地 JSON 重新加载，确保 CLI 报告与分析数据一致。
        generate_html: 是否生成 HTML 报告文件。当作为 Agent Skill 被调用时
                       应设为 False，避免重复生成报告；独立 CLI 使用时保持 True。
    """
    logger.info("=" * 50)
    logger.info("Industrial Sentinel 流水线启动")
    logger.info("目标标的: %s", stock_code)
    logger.info("=" * 50)

    # Step 1: 加载真实数据（优先使用调用方传入的数据）
    if real_data is None:
        real_data = load_real_data(stock_code)
    else:
        logger.info("[Step 1] 使用调用方传入的实时数据，跳过本地 JSON 加载")

    # Step 1.0: 数据缺失 → 框架降级。
    # 真实数据抓取由 data_sources/ 层负责，Skill runtime 不直接联网或落盘。
    detected = None
    if real_data is None:
        # 先检测 preset
        preset_name = "generic"
        try:
            from core.auto_detect_preset import auto_detect_preset
            detected = auto_detect_preset(stock_code, DATA_DIR, allow_provider_lookup=False)
            if detected:
                preset_name = detected
        except Exception as e:
            logger.debug("auto_detect_preset 失败: %s, 使用 generic", e)

        logger.warning("[Step 1.0] real_data 缺失，启用框架降级模式 (preset=%s)", preset_name)
        framework = build_framework_from_preset(stock_code, preset_name)
        stock_info = framework["stock_info"]
        lifecycle = framework["lifecycle"]
        inflection = framework["inflection"]
        system_b = framework["system_b"]
        chain_summary = framework["chain_summary"]

        # 生成降级 HTML（仅在独立 CLI 模式下生成）
        if generate_html:
            packet, result = _legacy_report_payload(
                stock_info,
                None,
                lifecycle,
                inflection,
                system_b,
                chain_summary,
                framework_only=True,
            )
            html = render_analysis_report(packet, result)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_code = re.sub(r"[^A-Za-z0-9]", "_", stock_code)
            out_path = REPORTS_DIR / f"{safe_code}_framework_{timestamp}.html"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("框架降级报告: %s", out_path)
            return str(out_path)
        else:
            logger.info("框架降级模式 (Agent 模式，跳过 HTML 生成)")
            return ""

    stock_info = get_stock_info(stock_code, real_data)
    logger.info("[Step 1] 股票信息: %s (%s)", stock_info["stock_name"], stock_info["stock_code"])

    # Step 1.5: 自动检测 preset（如果未配置）
    preset_name = stock_info.get("preset", "")
    if not preset_name or preset_name == "generic":
        # 无论 real_data 是否存在，都尝试自动检测 preset
        if detected is None:
            try:
                from core.auto_detect_preset import auto_detect_preset
                detected = auto_detect_preset(stock_code, DATA_DIR, allow_provider_lookup=False)
            except Exception as e:
                logger.debug("auto_detect_preset 失败: %s", e)

        if detected:
            stock_info["preset"] = detected
            logger.info("[Step 1.5] 自动检测到 preset: %s", detected)
        else:
            logger.warning("[Step 1.5] 无法自动检测 preset，使用 generic 模板")
    else:
        logger.info("[Step 1.5] 使用配置 preset: %s", preset_name)

    # 如果行业名称缺失，从 preset YAML 补充（无论 preset 怎么来的）
    if stock_info.get("industry") in ("数据缺失", "", None):
        yaml_data = load_preset_yaml(stock_info.get("preset", ""))
        if yaml_data:
            stock_info["industry"] = yaml_data.get("industry_name", stock_info["preset"])
            logger.info("[Step 1.5] 从YAML补充行业名称: %s", stock_info["industry"])

    # Step 1.6: 数据完整性检查 — 缺失较多时自动生成AI采集任务清单
    missing_count = 0
    if not real_data:
        missing_count = 999
    else:
        signals = _build_system_a_signals(real_data)
        industry_data = real_data.get("industry_data", [])
        # 检查核心字段
        core_fields = ["revenue_growth", "order_backlog", "capacity_utilization", "price_yoy", "inventory_days", "capex_plan"]
        missing_count = sum(1 for f in core_fields if signals.get(f) is None)
        if not industry_data:
            missing_count += 3
    
    if missing_count >= 3:
        logger.warning("[Step 1.6] 数据缺失较多(%d项)，自动生成AI采集任务清单...", missing_count)
        try:
            from core.data_collection_guide import generate_collection_guide, save_guide
            guide = generate_collection_guide(
                stock_info.get("preset", "generic"),
                stock_info.get("stock_code", ""),
                stock_info.get("stock_name", ""),
            )
            if guide:
                task_path = save_guide(guide)
                logger.info("[Step 1.6] 采集任务清单已生成: %s", task_path)
                logger.info("[Step 1.6] 请让对方AI按清单搜索数据，回填后继续运行pipeline")
                # 在终端输出醒目标记
                print(f"\n{'='*60}")
                print(f"⚠️  数据缺失警告: {missing_count}项核心数据未填充")
                print(f"{'='*60}")
                print("已自动生成AI数据采集任务清单:")
                print(f"  {task_path}")
                print("\n对方AI执行流程:")
                print("  1. 读取任务清单 → 按★必填优先搜索")
                print("  2. 校验来源+日期 → 按field_path回填JSON")
                print("  3. 缺失标注'数据缺失'，不编造")
                print(f"  4. 数据填满后重新运行: python3 core/pipeline.py {stock_code}")
                print(f"{'='*60}\n")
        except Exception as e:
            logger.error("[Step 1.6] 生成采集任务失败: %s", e)

    # Step 2: 生命周期判定
    lifecycle = determine_lifecycle_from_real_data(real_data)
    logger.info("[Step 2] 生命周期: %s", lifecycle["stage"])

    # Step 3: 拐点判定（真实信号路径）
    inflection = determine_inflection_from_real_data(real_data)
    logger.info("[Step 3] 拐点状态: %s", inflection["state_name"])

    # Step 4: System B 类型判定
    system_b = determine_system_b_from_real_data(real_data)
    logger.info("[Step 4] System B 类型: %s", system_b["type"])

    # Step 5: 产业链结构
    chain_html = load_industry_chain(stock_info)

    # Step 6: 行业数据
    industry_data = real_data.get("industry_data", []) if real_data else []

    # Step 7: 生成 HTML（仅在独立 CLI 模式下生成，Agent 集成模式跳过）
    if generate_html:
        packet, result = _legacy_report_payload(
            stock_info,
            real_data,
            lifecycle,
            inflection,
            system_b,
            real_data.get("chain_summary") if isinstance(real_data, dict) else None,
            framework_only=False,
        )
        html = render_analysis_report(packet, result)

        # 保存
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_code = re.sub(r"[^A-Za-z0-9]", "_", stock_code)
        out_path = REPORTS_DIR / f"{safe_code}_industry_{timestamp}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("=" * 50)
        logger.info("流水线完成 ✅")
        logger.info("输出文件: %s", out_path)
        logger.info("=" * 50)
        return str(out_path)
    else:
        logger.info("=" * 50)
        logger.info("流水线完成 ✅ (Agent 模式，跳过 HTML 生成)")
        logger.info("=" * 50)
        return ""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Industrial Sentinel")
    parser.add_argument("stock_code", help="股票代码/名称")
    parser.add_argument("--preset", help="强制指定产业链preset")
    parser.add_argument("--auto", action="store_true", help="强制自动检测preset")
    args = parser.parse_args()

    code_upper = args.stock_code.upper()
    # 始终使用原始代码（带点）作为文件名
    json_path = DATA_DIR / f"{code_upper}_real_data.json"
    # 如果有旧的 sanitized 文件，删除它避免混淆
    safe = re.sub(r"[^A-Za-z0-9]", "_", code_upper)
    old_path = DATA_DIR / f"{safe}_real_data.json"
    if old_path.exists() and old_path != json_path:
        old_path.unlink()
        logger.info("[清理] 删除旧格式文件: %s", old_path.name)

    # 加载或创建 real_data
    real_data = load_real_data(args.stock_code)
    if real_data is None:
        real_data = {
            "stock_code": code_upper,
            "stock_name": code_upper,
            "industry": "数据缺失",
            "preset": "generic",
            "generated_at": datetime.now().strftime("%Y-%m-%d"),
        }

    # 如果指定了 --preset，覆盖配置
    if args.preset:
        real_data["preset"] = args.preset
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(real_data, f, ensure_ascii=False, indent=2)
        logger.info("[强制指定] preset = %s", args.preset)

    # 如果指定了 --auto，清除 preset 触发自动检测
    if args.auto:
        if "preset" in real_data:
            del real_data["preset"]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(real_data, f, ensure_ascii=False, indent=2)
            logger.info("[强制自动] 已清除JSON中的preset配置")

    output_path = run_pipeline(args.stock_code)
    print(output_path)
