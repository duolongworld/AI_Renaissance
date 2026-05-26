#!/usr/bin/env python3
"""
Industrial Sentinel V4.5 端到端流水线 — 真实数据版
Pipeline: 股票代码 → 加载真实数据 → 拐点判定 → 类型分析 → HTML仪表盘

用法:
    python3 core/pipeline.py <stock_code>
    python3 core/pipeline.py AXTI.US

输出:
    生成 HTML 仪表盘文件, 打印文件路径
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline_v45")

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
    determine_lifecycle_phase,
    detect_dimension_contradictions,
    InflectionState,
)
from core.system_b import (
    identify_stock_type,
    get_stock_type_description,
    get_adaptive_weights,
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
                logger.info("[V4.5] 加载真实数据: %s", path.name)
                return data
            except Exception as e:
                logger.error("加载数据失败 %s: %s", path, e)
                continue
    logger.warning("[V4.5] 未找到 %s 的真实数据，所有指标将标记为「数据缺失」", stock_code)
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
    """安全地将输入值转换为数字。V4.5兼容显式字符串占位（如「数据缺失」）。
    
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

# ═══════════════════════════════════════════════════════════════
# Step 2: 生命周期阶段判定（基于真实数据）
# ═══════════════════════════════════════════════════════════════

def determine_lifecycle_from_real_data(real_data: Optional[Dict]) -> Dict[str, Any]:
    """
    基于真实财务指标判定生命周期阶段。
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
            "analysis": "请补充财报数据或行业研报数据以进行生命周期判定。",
        }

    signals = real_data.get("real_signals", {})
    rev_growth = _safe_num(signals.get("revenue_growth"))
    gm = _safe_num(signals.get("gross_margin"))
    backlog_raw = signals.get("order_backlog")
    backlog = _safe_num(backlog_raw)
    capex = str(signals.get("capex_plan", "")).lower()
    util = _safe_num(signals.get("capacity_utilization"))

    # 推理逻辑
    indicators = []
    if rev_growth is not None:
        indicators.append({"label": "营收增速", "value": f"{rev_growth:.0f}%", "trend": "up" if rev_growth > 20 else "flat", "source": signals.get("revenue_growth_source", "财报")})
    if gm is not None:
        indicators.append({"label": "毛利率", "value": f"{gm:.1f}%", "trend": "up" if gm > 20 else "flat", "source": signals.get("gross_margin_source", "财报")})
    if backlog is not None:
        indicators.append({"label": "订单backlog", "value": f"${backlog:.0f}M", "trend": "up", "source": signals.get("order_backlog_source", "财报")})
    elif backlog_raw is not None and isinstance(backlog_raw, str) and backlog_raw.strip() not in ("数据缺失", "待补充", "", "null", "None"):
        indicators.append({"label": "订单/需求", "value": backlog_raw, "trend": "up", "source": signals.get("order_backlog_source", "财报")})
    if util is not None:
        indicators.append({"label": "产能利用率", "value": f"{util:.0f}%", "trend": "up" if util > 80 else "flat", "source": signals.get("capacity_utilization_source", "财报")})
    if capex:
        indicators.append({"label": "扩产状态", "value": "进行中" if capex == "underway" else capex, "trend": "up", "source": signals.get("capex_plan_source", "新闻")})

    # 生命周期判定逻辑
    if rev_growth is not None and rev_growth >= 30 and capex == "underway" and (util is None or util >= 80):
        stage = "成长期"
        stage_short = "成长"
        subtitle = "高速扩张"
        desc = f"营收增速 {rev_growth:.0f}% 处于高速区间，产能扩张已启动，订单 backlog 强劲。行业处于成长期加速阶段，AI基础设施需求驱动 multi-year growth cycle。"
        color = "#10b981"
        color_bg = "rgba(16,185,129,0.12)"
        analysis = "成长期核心特征：需求增速 > 产能增速，价格有支撑，毛利率修复中。风险在于扩产进度和地缘政治（如出口许可）。"
    elif rev_growth is not None and rev_growth >= 15:
        stage = "成长期"
        stage_short = "成长"
        subtitle = "稳健增长"
        desc = f"营收增速 {rev_growth:.0f}% 保持较快增长，行业处于成长期。"
        color = "#10b981"
        color_bg = "rgba(16,185,129,0.12)"
        analysis = "成长期：关注产能利用率是否接近瓶颈，以及竞争格局变化。"
    elif rev_growth is not None and rev_growth > 0:
        stage = "成熟期"
        stage_short = "成熟"
        subtitle = "增速放缓"
        desc = f"营收增速 {rev_growth:.0f}% 温和，行业可能进入成熟期。"
        color = "#f59e0b"
        color_bg = "rgba(245,158,11,0.12)"
        analysis = "成熟期：关注市场份额稳定性、成本控制、分红能力。"
    elif rev_growth is not None and rev_growth <= 0:
        stage = "衰退期"
        stage_short = "衰退"
        subtitle = "需求收缩"
        desc = f"营收增速 {rev_growth:.0f}% 非正，行业面临需求收缩。"
        color = "#ef4444"
        color_bg = "rgba(239,68,68,0.12)"
        analysis = "衰退期：除非有明确的供给侧出清或技术换代催化剂，否则回避。"
    else:
        stage = "数据缺失"
        stage_short = "?"
        subtitle = "无数据"
        desc = "缺少营收增速等关键指标，无法判定生命周期阶段。"
        color = "#64748b"
        color_bg = "rgba(100,116,139,0.12)"
        analysis = "请补充真实财报数据。"

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

def determine_inflection_from_real_data(real_data: Optional[Dict]) -> Dict[str, Any]:
    """
    调用 system_a.determine_inflection_state 的 V4.5 路径（real_signals）。
    """
    if not real_data:
        return {
            "state_name": "数据缺失",
            "state_color": "#64748b",
            "state_color_bg": "rgba(100,116,139,0.12)",
            "matched_signals": "无信号",
            "inflection_data_cards": "",
            "inflection_logic": "未提供真实数据，无法判定拐点状态。",
        }

    signals = real_data.get("real_signals", {})
    # 调用 system_a 的 V4.5 真实信号路径
    result = determine_inflection_state(
        real_signals=signals,
        min_signals_required=2,
    )

    # 构建数据卡片HTML
    data_cards = []
    card_keys = [
        ("revenue_growth", "营收增速", "%", "财报"),
        ("gross_margin", "毛利率", "%", "财报"),
        ("order_backlog", "订单backlog", "M", "财报"),
        ("capacity_utilization", "产能利用率", "%", "新闻"),
        ("price_yoy", "价格同比", "%", "研报"),
        ("inventory_days", "库存天数", "天", "财报"),
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
    matched_signals_text = "、".join(result.matched_signals) if result.matched_signals else "无明确匹配信号"

    return {
        "state_name": result.state_name,
        "state_color": result.color_hex,
        "state_color_bg": f"rgba({int(result.color_hex[1:3],16)},{int(result.color_hex[3:5],16)},{int(result.color_hex[5:7],16)},0.12)",
        "matched_signals": matched_signals_text,
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
    except Exception:
        pass
    
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
                        "source": "财报",
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
                metric_text = f"营收增速 {rev}"
                quality_text = f"毛利率 {gm}"
            else:
                metric_text = "环节数据缺失"
                quality_text = "—"
            
            # 第二列显示环节名+小字标注数据来源
            name_cell = f'<b>{seg_name}</b>'
            if matched:
                name_cell += f'<br/><span style="font-size:11px;color:var(--text-muted)">来源: {matched["name"]}({matched["code"]})</span>'
            
            # 第三列合并指标和营收
            metric_details = "<br/>".join(metrics) if metrics else "—"
            if matched and matched.get('revenue_growth') is not None:
                metric_details += f'<br/><span style="color:var(--green)">营收增速 {rev}</span>'
            
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
    """加载产业链结构说明（V4.5精简卡片版）"""
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
    """从YAML动态读取产业链结构卡片（V4.5通用版）"""
    
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
            f'<div class="card" style="border-left:3px solid #2563eb;">',
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
# Step 6: HTML 生成（V4 模板）
# ═══════════════════════════════════════════════════════════════

def generate_html_v45(
    stock_info: Dict[str, str],
    lifecycle: Dict[str, Any],
    inflection: Dict[str, Any],
    system_b: Dict[str, Any],
    industry_data: List[Dict],
    chain_html: str,
) -> str:
    """使用 v4 模板生成 HTML"""
    template_path = TEMPLATES_DIR / "pipeline-output-v4.html"
    if not template_path.exists():
        logger.error("V4 模板不存在: %s", template_path)
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
        "{{data_source_footer}}": "数据来源: AXT Inc 财报(10-K/10-Q) + 行业研报 + 新闻 | 本报告仅供研究参考，不构成投资建议",
    }

    html = template
    for key, val in replacements.items():
        html = html.replace(key, str(val))

    return html


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def run_pipeline(stock_code: str) -> str:
    """运行完整流水线，返回生成的HTML文件路径"""
    logger.info("=" * 50)
    logger.info("Industrial Sentinel V4.5 流水线启动")
    logger.info("目标标的: %s", stock_code)
    logger.info("=" * 50)

    # Step 1: 加载真实数据
    real_data = load_real_data(stock_code)
    stock_info = get_stock_info(stock_code, real_data)
    logger.info("[Step 1] 股票信息: %s (%s)", stock_info["stock_name"], stock_info["stock_code"])

    # Step 1.5: 自动检测 preset（如果未配置）
    preset_name = stock_info.get("preset", "")
    if not preset_name or preset_name == "generic":
        from core.auto_detect_preset import auto_detect_preset
        detected = auto_detect_preset(stock_code, DATA_DIR)
        if detected:
            stock_info["preset"] = detected
            logger.info("[Step 1.5] 自动检测到 preset: %s", detected)
            # 如果行业名称缺失，从YAML补充
            if stock_info.get("industry") in ("数据缺失", "", None):
                yaml_data = load_preset_yaml(detected)
                if yaml_data:
                    stock_info["industry"] = yaml_data.get("industry_name", detected)
                    logger.info("[Step 1.5] 从YAML补充行业名称: %s", stock_info["industry"])
        else:
            logger.warning("[Step 1.5] 无法自动检测 preset，使用 generic 模板")
    else:
        logger.info("[Step 1.5] 使用配置 preset: %s", preset_name)

    # Step 1.6: 数据完整性检查 — 缺失较多时自动生成AI采集任务清单
    missing_count = 0
    if not real_data:
        missing_count = 999
    else:
        signals = real_data.get("real_signals", {})
        industry_data = real_data.get("industry_data", [])
        # 检查核心字段
        core_fields = ["revenue_growth", "gross_margin", "order_backlog", "capacity_utilization", "price_yoy"]
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
                print(f"已自动生成AI数据采集任务清单:")
                print(f"  {task_path}")
                print(f"\n对方AI执行流程:")
                print(f"  1. 读取任务清单 → 按★必填优先搜索")
                print(f"  2. 校验来源+日期 → 按field_path回填JSON")
                print(f"  3. 缺失标注'数据缺失'，不编造")
                print(f"  4. 数据填满后重新运行: python3 core/pipeline.py {stock_code}")
                print(f"{'='*60}\n")
        except Exception as e:
            logger.error("[Step 1.6] 生成采集任务失败: %s", e)

    # Step 2: 生命周期判定
    lifecycle = determine_lifecycle_from_real_data(real_data)
    logger.info("[Step 2] 生命周期: %s", lifecycle["stage"])

    # Step 3: 拐点判定（V4.5 真实信号路径）
    inflection = determine_inflection_from_real_data(real_data)
    logger.info("[Step 3] 拐点状态: %s", inflection["state_name"])

    # Step 4: System B 类型判定
    system_b = determine_system_b_from_real_data(real_data)
    logger.info("[Step 4] System B 类型: %s", system_b["type"])

    # Step 5: 产业链结构
    chain_html = load_industry_chain(stock_info)

    # Step 6: 行业数据
    industry_data = real_data.get("industry_data", []) if real_data else []

    # Step 7: 生成 HTML
    html = generate_html_v45(
        stock_info=stock_info,
        lifecycle=lifecycle,
        inflection=inflection,
        system_b=system_b,
        industry_data=industry_data,
        chain_html=chain_html,
    )

    # 保存
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_code = re.sub(r"[^A-Za-z0-9]", "_", stock_code)
    out_path = REPORTS_DIR / f"{safe_code}_v45_{timestamp}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("=" * 50)
    logger.info("V4.5 流水线完成 ✅")
    logger.info("输出文件: %s", out_path)
    logger.info("=" * 50)
    return str(out_path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Industrial Sentinel V4.5")
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
