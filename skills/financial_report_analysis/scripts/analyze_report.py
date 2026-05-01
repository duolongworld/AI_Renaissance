#!/usr/bin/env python3
"""
财报分析脚本 - 自动化数据获取与比率计算

用法:
    python3 analyze_report.py <股票代码> [--periods 4] [--output report.md]

示例:
    python3 analyze_report.py sh600519
    python3 analyze_report.py sz000001 --periods 6 --output 分析报告.md
    python3 analyze_report.py hk00700

股票代码格式:
    沪市: sh600519  深市: sz000001  港股: hk00700  美股: usAAPL
"""

import subprocess
import json
import sys
import argparse
import os
from datetime import datetime


# ============================================================
# 数据溯源追踪器
# ============================================================

class DataTracker:
    """
    数据溯源追踪器：记录每个关键数据的来源，防止幻觉。
    
    使用方式：
        tracker = DataTracker()
        tracker.record("合同负债", 1.795, "东财API·资产负债表·2026Q1")
        tracker.record("收现比", 1.77, "计算：销售收现2.901亿/营收1.638亿", category="B")
        tracker.cite("合同负债")  # → "1.795亿 ← 东财API·资产负债表·2026Q1"
    """
    
    def __init__(self):
        self._records = {}  # key -> {"value": ..., "source": ..., "category": ..., "formula": ...}
        self._sources = {}  # source_id -> {"credibility": ..., "scope": ...}
    
    def record(self, key: str, value, source: str, category: str = "A", formula: str = ""):
        """
        记录一个数据的来源。
        
        Args:
            key: 数据名称（如"合同负债"、"收现比"）
            value: 数据值
            source: 来源标识（如"东财API·资产负债表·2026Q1"）
            category: 数据类别
                A = 原始数据（直接从API/公告获取）
                B = 计算比率（基于原始数据计算）
                C = 低可信来源（二手媒体、估算）
            formula: 计算公式（category=B时必填）
        """
        self._records[key] = {
            "value": value,
            "source": source,
            "category": category,
            "formula": formula,
        }
    
    def register_source(self, source_id: str, credibility: str, scope: str):
        """注册数据源及其可信度"""
        self._sources[source_id] = {
            "credibility": credibility,
            "scope": scope,
        }
    
    def cite(self, key: str) -> str:
        """生成带来源引用的数据行"""
        rec = self._records.get(key)
        if not rec:
            return f"⚠️ {key}：数据未记录来源"
        
        val_str = self._fmt_val(rec["value"])
        source = rec["source"]
        
        if rec["category"] == "A":
            return f"{val_str} ← {source}"
        elif rec["category"] == "B":
            formula = rec.get("formula", "")
            if formula:
                return f"{val_str} ← 计算：{formula} ← {source}"
            return f"{val_str} ← 计算 ← {source}"
        elif rec["category"] == "C":
            return f"⚠️ {val_str} ← ⚠️{source}"
        return f"{val_str} ← {source}"
    
    def cite_inline(self, key: str) -> str:
        """生成简短的内联引用（用于表格中）"""
        rec = self._records.get(key)
        if not rec:
            return "—"
        source = rec["source"]
        # 缩短来源标识
        if "东财API" in source:
            short = "东财API"
        elif "westock" in source:
            short = "westock"
        elif "neodata" in source:
            short = "neodata"
        elif "巨潮" in source:
            short = "巨潮PDF"
        elif "公司公告" in source:
            short = "公司公告"
        else:
            short = source[:20]
        
        prefix = "⚠️" if rec["category"] == "C" else ""
        return f"{prefix}←{short}"
    
    def source_table(self) -> str:
        """生成数据源清单表格"""
        if not self._sources:
            return "| 数据源 | 可信度 | 覆盖范围 |\n|--------|-------|---------|\n| （未注册数据源） | — | — |"
        
        lines = ["| 数据源 | 可信度 | 覆盖范围 |", "|--------|-------|---------|"]
        for sid, info in self._sources.items():
            cred = info["credibility"]
            scope = info["scope"]
            lines.append(f"| {sid} | {cred} | {scope} |")
        return "\n".join(lines)
    
    def all_citations(self) -> list:
        """返回所有数据引用列表（用于附录）"""
        result = []
        for key, rec in self._records.items():
            result.append(f"- **{key}**：{self.cite(key)}")
        return result
    
    @staticmethod
    def _fmt_val(val):
        """格式化数值"""
        if val is None:
            return "N/A"
        if isinstance(val, float):
            if abs(val) >= 1e8:
                return f"{val/1e8:.2f}亿"
            elif abs(val) >= 1e4:
                return f"{val/1e4:.1f}万"
            elif abs(val) < 1:
                return f"{val:.2%}"
            return f"{val:.2f}"
        return str(val)


# 全局追踪器实例
tracker = DataTracker()


def run_westock(command: str) -> dict:
    """调用 westock-data CLI 并返回解析后的数据"""
    full_cmd = f"npx --yes westock-data-skillhub@latest {command}"
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True, timeout=60
        )
        output = result.stdout.strip()
        # 尝试解析JSON
        if output.startswith("{") or output.startswith("["):
            return json.loads(output)
        # 非JSON格式，返回原始文本
        return {"raw_text": output}
    except subprocess.TimeoutExpired:
        return {"error": "westock-data 命令超时"}
    except json.JSONDecodeError:
        return {"raw_text": output}
    except Exception as e:
        return {"error": str(e)}


def safe_divide(a, b, default=None):
    """安全除法，避免除零错误"""
    if b is None or b == 0 or a is None:
        return default
    return a / b


def calc_change_rate(current, previous):
    """计算变化率"""
    if previous is None or previous == 0 or current is None:
        return None
    return (current - previous) / abs(previous)


def rate_level(value, thresholds):
    """根据阈值区间判断评级"""
    if value is None:
        return "数据缺失"
    for level, (low, high), label in thresholds:
        if low <= value < high:
            return label
    return "超出范围"


# ============================================================
# 核心比率计算
# ============================================================

def calc_cash_profit_ratio(operating_cf, net_profit):
    """经营现金流/归母净利润"""
    return safe_divide(operating_cf, net_profit)


def calc_cash_revenue_ratio(sales_cash, revenue):
    """销售收现/营收"""
    return safe_divide(sales_cash, revenue)


def calc_receivable_vs_revenue_change(ar_change_rate, rev_change_rate):
    """应收变化率 vs 营收变化率"""
    if ar_change_rate is None or rev_change_rate is None:
        return "数据缺失"

    if ar_change_rate < 0 and rev_change_rate > 0:
        return "强积极：收入增长但应收下降"
    elif ar_change_rate >= 0 and rev_change_rate > 0:
        if ar_change_rate < rev_change_rate:
            return "积极：应收增速慢于营收"
        else:
            return "警惕：应收增速快于营收"
    elif ar_change_rate > 0 and rev_change_rate <= 0:
        return "危险：收入下滑但应收增加"
    else:
        return "中性"


def calc_construction_ratio(construction_in_progress, fixed_assets):
    """在建工程占比"""
    total = (construction_in_progress or 0) + (fixed_assets or 0)
    return safe_divide(construction_in_progress, total)


def calc_net_debt_ratio(short_borrowing, long_borrowing, cash):
    """净债务率 = (短债+长债-现金)/净资产"""
    # 这里简化计算，净资产需从资产负债表获取
    net_debt = (short_borrowing or 0) + (long_borrowing or 0) - (cash or 0)
    return net_debt


def calc_financial_expense_erosion(financial_expense, operating_profit):
    """财务费用侵蚀度 = 财务费用/营业利润"""
    return safe_divide(financial_expense, operating_profit)


# ============================================================
# 分析引擎
# ============================================================

def analyze_financial_data(data_list: list) -> dict:
    """
    对财务数据列表执行七步分析
    data_list: 按时间倒序排列的财务数据列表，每项为一个报告期的数据
    """
    if not data_list or len(data_list) < 2:
        return {"error": "数据不足，至少需要2个报告期"}

    results = {
        "periods_analyzed": len(data_list),
        "report_dates": [],
        "step1_cash_validation": {},
        "step2_demand_validation": {},
        "step3_performance_indicator": {},
        "step4_capacity_signal": {},
        "step5_expansion_signal": {},
        "step6_expansion_risk": {},
        "step7_interest_sensitivity": {},
        "logic_chain": {},
    }

    for d in data_list:
        results["report_dates"].append(d.get("report_date", "未知"))

    # ---- 第一步：现金验证 ----
    cash_profit_ratios = []
    cash_revenue_ratios = []
    for d in data_list:
        ratio1 = calc_cash_profit_ratio(
            d.get("operating_cf"), d.get("net_profit")
        )
        ratio2 = calc_cash_revenue_ratio(
            d.get("sales_cash"), d.get("revenue")
        )
        cash_profit_ratios.append(ratio1)
        cash_revenue_ratios.append(ratio2)

    results["step1_cash_validation"] = {
        "cash_profit_ratio": cash_profit_ratios,
        "cash_revenue_ratio": cash_revenue_ratios,
        "cash_profit_trend": "改善" if (cash_profit_ratios[0] or 0) > (cash_profit_ratios[-1] or 0) else "恶化" if (cash_profit_ratios[0] or 0) < (cash_profit_ratios[-1] or 0) else "持平",
        "cash_revenue_trend": "改善" if (cash_revenue_ratios[0] or 0) > (cash_revenue_ratios[-1] or 0) else "恶化" if (cash_revenue_ratios[0] or 0) < (cash_revenue_ratios[-1] or 0) else "持平",
    }

    # ---- 第二步：需求验证 ----
    if len(data_list) >= 2:
        latest = data_list[0]
        previous = data_list[1]
        ar_change = calc_change_rate(latest.get("accounts_receivable"), previous.get("accounts_receivable"))
        rev_change = calc_change_rate(latest.get("revenue"), previous.get("revenue"))
        inventory_change = calc_change_rate(latest.get("inventory"), previous.get("inventory"))
        cip_change = calc_change_rate(latest.get("construction_in_progress"), previous.get("construction_in_progress"))

        demand_signal = calc_receivable_vs_revenue_change(ar_change, rev_change)

        results["step2_demand_validation"] = {
            "ar_change_rate": ar_change,
            "revenue_change_rate": rev_change,
            "inventory_change_rate": inventory_change,
            "cip_change_rate": cip_change,
            "demand_signal": demand_signal,
            "working_capital_note": _working_capital_note(ar_change, inventory_change, cip_change),
        }

    # ---- 第三步：业绩先行指标 ----
    contract_liability_changes = []
    for i in range(len(data_list) - 1):
        change = calc_change_rate(
            data_list[i].get("contract_liability"),
            data_list[i + 1].get("contract_liability"),
        )
        contract_liability_changes.append(change)

    results["step3_performance_indicator"] = {
        "contract_liability_changes": contract_liability_changes,
        "signal": _contract_liability_signal(contract_liability_changes),
    }

    # ---- 第四步：产能信号 ----
    cip_ratios = []
    cip_trend = []
    fa_trend = []
    capex_trend = []
    for i in range(len(data_list) - 1):
        ratio = calc_construction_ratio(
            data_list[i].get("construction_in_progress"),
            data_list[i].get("fixed_assets"),
        )
        cip_ratios.append(ratio)
        cip_trend.append(calc_change_rate(
            data_list[i].get("construction_in_progress"),
            data_list[i + 1].get("construction_in_progress"),
        ))
        fa_trend.append(calc_change_rate(
            data_list[i].get("fixed_assets"),
            data_list[i + 1].get("fixed_assets"),
        ))
        capex_trend.append(calc_change_rate(
            data_list[i].get("capex"),
            data_list[i + 1].get("capex"),
        ))

    results["step4_capacity_signal"] = {
        "cip_ratio": cip_ratios,
        "cip_trend": cip_trend,
        "fa_trend": fa_trend,
        "capex_trend": capex_trend,
        "capacity_signal": _capacity_signal(cip_trend, fa_trend, capex_trend),
    }

    # ---- 第五步：扩张信号 ----
    results["step5_expansion_signal"] = {
        "capex_trend": capex_trend,
        "expansion_signal": "资本开支放量" if any(t and t > 0.1 for t in (capex_trend or [])) else "资本开支缩量",
    }

    # ---- 第六步：扩张风险 ----
    if len(data_list) >= 2:
        latest = data_list[0]
        previous = data_list[1]
        short_borrow_change = calc_change_rate(latest.get("short_borrowing"), previous.get("short_borrowing"))
        long_borrow_change = calc_change_rate(latest.get("long_borrowing"), previous.get("long_borrowing"))
        net_debt = calc_net_debt_ratio(
            latest.get("short_borrowing"), latest.get("long_borrowing"), latest.get("cash")
        )

        results["step6_expansion_risk"] = {
            "net_debt": net_debt,
            "short_borrowing_change": short_borrow_change,
            "long_borrowing_change": long_borrow_change,
            "risk_level": _debt_risk_level(short_borrow_change, long_borrow_change, capex_trend),
        }

    # ---- 第七步：财务费用侵蚀 ----
    erosion_ratios = []
    for d in data_list:
        erosion = calc_financial_expense_erosion(
            d.get("financial_expense"), d.get("operating_profit")
        )
        erosion_ratios.append(erosion)

    results["step7_interest_sensitivity"] = {
        "erosion_ratios": erosion_ratios,
        "erosion_level": _erosion_level(erosion_ratios[0] if erosion_ratios else None),
    }

    # ---- 逻辑链验证 ----
    results["logic_chain"] = _validate_logic_chain(results)

    return results


def _working_capital_note(ar_change, inv_change, cip_change):
    """判断营运资本信号"""
    ar_down = ar_change is not None and ar_change < 0
    inv_up = inv_change is not None and inv_change > 0
    cip_up = cip_change is not None and cip_change > 0

    if ar_down and (inv_up or cip_up):
        return "积极：应收下降+存货/在建上升，需求真实+备产积极"
    elif ar_down:
        return "偏积极：应收下降，回款改善"
    elif inv_up and cip_up:
        return "中性偏积极：存货+在建上升，需确认非滞销"
    elif inv_up and not cip_up:
        return "警惕：存货上升但在建未增，可能滞销"
    else:
        return "中性"


def _contract_liability_signal(changes):
    """合同负债信号判断"""
    if not changes:
        return "数据不足"
    latest = changes[0]
    if latest is None:
        return "数据缺失"
    if latest > 0.2:
        return "强积极：合同负债大幅上升，未来业绩有保障"
    elif latest > 0:
        return "积极：合同负债稳步增长"
    elif latest > -0.2:
        return "警惕：合同负债小幅下滑"
    else:
        return "危险：合同负债大幅下降"


def _capacity_signal(cip_trend, fa_trend, capex_trend):
    """产能信号判断"""
    cip_up = any(t and t > 0 for t in (cip_trend or []))
    fa_up = any(t and t > 0 for t in (fa_trend or []))
    capex_up = any(t and t > 0 for t in (capex_trend or []))

    if cip_up and fa_up and capex_up:
        return "强扩张：真金白银在投未来"
    elif cip_up and capex_up:
        return "扩张中：产能建设中"
    elif fa_up and not capex_up:
        return "扩产完成：进入产能释放期"
    else:
        return "收缩/维持期"


def _debt_risk_level(short_change, long_change, capex_trend):
    """债务风险判断"""
    capex_up = any(t and t > 0.1 for t in (capex_trend or []))

    if short_change and short_change > 0.5:
        return "高风险：短期借款暴增，资金链可能紧张"
    if long_change and long_change > 0.5 and not capex_up:
        return "警惕：长期借款大增但资本开支未放量"
    if short_change and short_change > 0.2:
        return "需关注：短期借款增长较快"
    return "相对安全"


def _erosion_level(erosion_ratio):
    """财务费用侵蚀评级"""
    if erosion_ratio is None:
        return "数据缺失"
    if erosion_ratio < 0.05:
        return "安全：利息对利润几乎无影响"
    elif erosion_ratio < 0.10:
        return "良好：利息可控"
    elif erosion_ratio < 0.20:
        return "警惕：利息开始侵蚀利润"
    elif erosion_ratio < 0.40:
        return "危险：利润被利息严重侵蚀"
    else:
        return "极危：经营利润大部分用来还利息"


def _validate_logic_chain(results):
    """验证完整逻辑链"""
    chain = {
        "orders_real": False,
        "cash_returns": False,
        "receivables_ok": False,
        "inventory_cip_rising": False,
        "capex_expanding": False,
        "expansion_delivering": False,
    }
    notes = []

    # 1. 订单真实 → 合同负债上升
    cl_signal = results.get("step3_performance_indicator", {}).get("signal", "")
    if "积极" in cl_signal or "强积极" in cl_signal:
        chain["orders_real"] = True
    else:
        notes.append("合同负债未明显上升，订单真实性待验证")

    # 2. 现金先回 → 经营现金流/归母净利润 > 1
    cp_ratios = results.get("step1_cash_validation", {}).get("cash_profit_ratio", [])
    if cp_ratios and cp_ratios[0] is not None and cp_ratios[0] > 1.0:
        chain["cash_returns"] = True
    else:
        notes.append("现金利润比<1，利润可能缺乏现金支撑")

    # 3. 应收没恶化
    demand_signal = results.get("step2_demand_validation", {}).get("demand_signal", "")
    if "积极" in demand_signal or "强积极" in demand_signal:
        chain["receivables_ok"] = True
    elif "危险" in demand_signal:
        notes.append("应收恶化：收入下滑但应收增加")
    else:
        chain["receivables_ok"] = True  # 中性也算通过

    # 4. 存货和在建抬升
    wc_note = results.get("step2_demand_validation", {}).get("working_capital_note", "")
    if "备产积极" in wc_note:
        chain["inventory_cip_rising"] = True
    elif "滞销" in wc_note:
        notes.append("存货上升但在建未增，可能滞销")

    # 5. 资本开支放量
    exp_signal = results.get("step5_expansion_signal", {}).get("expansion_signal", "")
    if "放量" in exp_signal:
        chain["capex_expanding"] = True
    else:
        notes.append("资本开支未放量")

    # 6. 扩产兑现
    cap_signal = results.get("step4_capacity_signal", {}).get("capacity_signal", "")
    if "产能释放" in cap_signal or "强扩张" in cap_signal:
        chain["expansion_delivering"] = True

    # 评级
    passed = sum(1 for v in chain.values() if v)
    total = len(chain)
    if passed >= 5:
        grade = "A级：高确定性增长"
    elif passed >= 4:
        grade = "B级：需关注薄弱环节"
    elif passed >= 2:
        grade = "C级：增长逻辑存疑"
    else:
        grade = "D级：增长逻辑不可信"

    chain["passed_count"] = passed
    chain["total_count"] = total
    chain["grade"] = grade
    chain["risk_notes"] = notes

    return chain


# ============================================================
# 报告生成
# ============================================================

def generate_report(stock_code: str, analysis: dict, data_tracker: DataTracker = None) -> str:
    """生成Markdown格式的分析报告（含数据溯源）"""
    dates = analysis.get("report_dates", [])
    periods = analysis.get("periods_analyzed", 0)
    t = data_tracker or tracker

    lines = []
    lines.append(f"# {stock_code} 财报质量分析")
    lines.append(f"\n> 分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> 覆盖报告期：{periods}期 ({', '.join(str(d) for d in dates[:4])}{'...' if periods > 4 else ''})")
    
    # 数据源概览
    if t._sources:
        lines.append(">")
        lines.append("> **数据源概览：**")
        for sid, info in t._sources.items():
            lines.append(f"> - {sid}：{info['credibility']} — {info['scope']}")
    
    lines.append("")

    # 第一步
    s1 = analysis.get("step1_cash_validation", {})
    lines.append("## 一、利润现金验证")
    cp = s1.get("cash_profit_ratio", [])
    cr = s1.get("cash_revenue_ratio", [])
    cp_trend = s1.get("cash_profit_trend", "未知")
    cr_trend = s1.get("cash_revenue_trend", "未知")

    lines.append(f"- **经营现金流/归母净利润**：{', '.join(f'{r:.2f}' if r else 'N/A' for r in cp[:4])} → 趋势：{cp_trend}")
    lines.append(f"- **销售收现/营收**：{', '.join(f'{r:.2f}' if r else 'N/A' for r in cr[:4])} → 趋势：{cr_trend}")

    latest_cp = cp[0] if cp else None
    if latest_cp and latest_cp > 1.0:
        lines.append("- **利润质量总评**：✅ 高 — 利润有充足现金支撑")
    elif latest_cp and latest_cp > 0.8:
        lines.append("- **利润质量总评**：⚠️ 中 — 现金略低于利润，需关注")
    else:
        lines.append("- **利润质量总评**：❌ 低 — 利润可能缺乏现金支撑")
    lines.append("")

    # 第二步
    s2 = analysis.get("step2_demand_validation", {})
    lines.append("## 二、需求真实性验证")
    lines.append(f"- **应收账款变化率**：{_fmt_pct(s2.get('ar_change_rate'))}")
    lines.append(f"- **营收变化率**：{_fmt_pct(s2.get('revenue_change_rate'))}")
    lines.append(f"- **存货变化率**：{_fmt_pct(s2.get('inventory_change_rate'))}")
    lines.append(f"- **在建工程变化率**：{_fmt_pct(s2.get('cip_change_rate'))}")
    lines.append(f"- **需求信号**：{s2.get('demand_signal', '未知')}")
    lines.append(f"- **营运资本信号**：{s2.get('working_capital_note', '未知')}")
    lines.append("")

    # 第三步
    s3 = analysis.get("step3_performance_indicator", {})
    lines.append("## 三、业绩先行指标")
    cl_changes = s3.get("contract_liability_changes", [])
    lines.append(f"- **合同负债变化率**：{', '.join(_fmt_pct(c) for c in cl_changes[:4])}")
    lines.append(f"- **信号**：{s3.get('signal', '未知')}")
    lines.append("")

    # 第四步
    s4 = analysis.get("step4_capacity_signal", {})
    lines.append("## 四、产能扩张信号")
    lines.append(f"- **在建工程占比**：{', '.join(f'{r:.1%}' if r else 'N/A' for r in s4.get('cip_ratio', [])[:4])}")
    lines.append(f"- **在建工程趋势**：{', '.join(_fmt_pct(t) for t in s4.get('cip_trend', [])[:4])}")
    lines.append(f"- **固定资产趋势**：{', '.join(_fmt_pct(t) for t in s4.get('fa_trend', [])[:4])}")
    lines.append(f"- **资本开支趋势**：{', '.join(_fmt_pct(t) for t in s4.get('capex_trend', [])[:4])}")
    lines.append(f"- **产能信号总评**：{s4.get('capacity_signal', '未知')}")
    lines.append("")

    # 第五步
    s5 = analysis.get("step5_expansion_signal", {})
    lines.append("## 五、扩张信号")
    lines.append(f"- **资本开支趋势**：{', '.join(_fmt_pct(t) for t in s5.get('capex_trend', [])[:4])}")
    lines.append(f"- **扩张信号**：{s5.get('expansion_signal', '未知')}")
    lines.append("")

    # 第六步
    s6 = analysis.get("step6_expansion_risk", {})
    lines.append("## 六、扩张风险评估")
    nd = s6.get("net_debt")
    lines.append(f"- **净债务**：{_fmt_num(nd)}")
    lines.append(f"- **短期借款变化**：{_fmt_pct(s6.get('short_borrowing_change'))}")
    lines.append(f"- **长期借款变化**：{_fmt_pct(s6.get('long_borrowing_change'))}")
    lines.append(f"- **风险等级**：{s6.get('risk_level', '未知')}")
    lines.append("")

    # 第七步
    s7 = analysis.get("step7_interest_sensitivity", {})
    lines.append("## 七、财务费用侵蚀")
    er = s7.get("erosion_ratios", [])
    lines.append(f"- **财务费用/营业利润**：{', '.join(f'{r:.1%}' if r else 'N/A' for r in er[:4])}")
    lines.append(f"- **侵蚀评级**：{s7.get('erosion_level', '未知')}")
    lines.append("")

    # 综合判断
    lc = analysis.get("logic_chain", {})
    lines.append("## 八、综合判断")
    lines.append(f"- **逻辑链完整度**：{lc.get('passed_count', 0)}/{lc.get('total_count', 6)}")
    lines.append(f"- **评级**：{lc.get('grade', '未知')}")
    lines.append("")

    risk_notes = lc.get("risk_notes", [])
    if risk_notes:
        lines.append("### 关键风险点")
        for note in risk_notes:
            lines.append(f"- ⚠️ {note}")
        lines.append("")

    # 逻辑链各环节
    lines.append("### 逻辑链各环节状态")
    labels = {
        "orders_real": "订单真实（合同负债上升）",
        "cash_returns": "现金先回（现金利润比>1）",
        "receivables_ok": "应收没恶化",
        "inventory_cip_rising": "存货和在建抬升",
        "capex_expanding": "资本开支放量",
        "expansion_delivering": "扩产兑现",
    }
    for key, label in labels.items():
        status = "✅" if lc.get(key) else "❌"
        lines.append(f"- {status} {label}")

    lines.append("")
    lines.append("---")
    lines.append("*本报告由 financial-report-analysis skill 自动生成，仅供参考，不构成投资建议。*")
    
    # 数据溯源附录
    lines.append("")
    lines.append("## 附录：数据溯源")
    citations = t.all_citations()
    if citations:
        lines.append("")
        lines.append("### 关键数据来源")
        for c in citations[:30]:  # 限制30条，避免过长
            lines.append(c)
    
    # 数据源清单
    lines.append("")
    lines.append("### 数据源清单")
    lines.append(t.source_table())

    return "\n".join(lines)


def _fmt_pct(val):
    """格式化百分比"""
    if val is None:
        return "N/A"
    return f"{val:.1%}"


def _fmt_num(val):
    """格式化数值"""
    if val is None:
        return "N/A"
    if abs(val) >= 1e8:
        return f"{val/1e8:.1f}亿"
    elif abs(val) >= 1e4:
        return f"{val/1e4:.1f}万"
    else:
        return f"{val:.1f}"


# ============================================================
# 数据获取（westock-data接口）
# ============================================================

def fetch_financial_data(stock_code: str, periods: int = 4) -> list:
    """
    通过 westock-data 获取财务数据并解析为结构化列表
    返回按时间倒序排列的数据列表
    """
    # 获取财务报表
    finance_data = run_westock(f"finance {stock_code} {periods}")

    if "error" in finance_data:
        print(f"❌ 获取财务数据失败: {finance_data['error']}", file=sys.stderr)
        return []

    if "raw_text" in finance_data:
        # 非JSON输出，尝试从文本中提取
        print("⚠️ westock-data 返回非结构化数据，需手动解析", file=sys.stderr)
        print(finance_data["raw_text"][:500], file=sys.stderr)
        return _parse_raw_finance_data(finance_data["raw_text"], periods)

    # JSON格式直接使用
    return _normalize_finance_data(finance_data, periods)


def _normalize_finance_data(data: dict, periods: int) -> list:
    """将westock-data JSON输出标准化为分析所需格式"""
    # westock-data finance 返回的数据结构可能包含多个报告期
    # 这里做通用适配
    result = []

    # 尝试不同的数据格式
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # 可能在某个key下
        items = data.get("data", data.get("list", data.get("items", [data])))
    else:
        return result

    for item in items[:periods]:
        if not isinstance(item, dict):
            continue
        normalized = {
            "report_date": item.get("reportDate") or item.get("report_date") or item.get("date", ""),
            # 利润表
            "revenue": _to_float(item.get("totalOperateIncome") or item.get("revenue") or item.get("营业收入")),
            "net_profit": _to_float(item.get("parentNetProfit") or item.get("net_profit") or item.get("归母净利润")),
            "operating_profit": _to_float(item.get("operateProfit") or item.get("operating_profit") or item.get("营业利润")),
            # 现金流量表
            "operating_cf": _to_float(item.get("netCashFromOperatingActivities") or item.get("operating_cf") or item.get("经营活动现金流净额")),
            "sales_cash": _to_float(item.get("salesServicesReceivedCash") or item.get("sales_cash") or item.get("销售收现")),
            "capex": _to_float(item.get("cashPaidForFixedAssets") or item.get("capex") or item.get("购建固定资产支付的现金")),
            # 资产负债表
            "accounts_receivable": _to_float(item.get("accountsReceivable") or item.get("accounts_receivable") or item.get("应收账款")),
            "inventory": _to_float(item.get("inventory") or item.get("存货")),
            "contract_liability": _to_float(item.get("contractLiability") or item.get("contract_liability") or item.get("合同负债") or item.get("预收款项")),
            "construction_in_progress": _to_float(item.get("constructionInProgress") or item.get("construction_in_progress") or item.get("在建工程")),
            "fixed_assets": _to_float(item.get("fixedAssets") or item.get("fixed_assets") or item.get("固定资产")),
            "cash": _to_float(item.get("cash") or item.get("货币资金")),
            "short_borrowing": _to_float(item.get("shortLoan") or item.get("short_borrowing") or item.get("短期借款")),
            "long_borrowing": _to_float(item.get("longLoan") or item.get("long_borrowing") or item.get("长期借款")),
            "financial_expense": _to_float(item.get("financialExpense") or item.get("financial_expense") or item.get("财务费用")),
        }
        result.append(normalized)

    return result


def _parse_raw_finance_data(text: str, periods: int) -> list:
    """从原始文本中尝试提取财务数据（备用解析器）"""
    # 这是一个简化的文本解析器，适用于表格格式的输出
    # 实际使用时可能需要根据westock-data的具体输出格式调整
    result = []
    lines = text.strip().split("\n")

    # 查找包含数据的行
    for line in lines:
        if not line.strip():
            continue
        # 尝试提取数值（非常粗略的解析）
        # 实际使用中建议直接使用JSON输出
        pass

    return result


def _to_float(val):
    """将各种格式的数值转为float"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace(",", "").replace("，", "").strip()
        if val in ("-", "--", "N/A", "", "null"):
            return None
        try:
            # 处理带单位的值
            if val.endswith("亿"):
                return float(val[:-1]) * 1e8
            elif val.endswith("万"):
                return float(val[:-1]) * 1e4
            elif val.endswith("%"):
                return float(val[:-1]) / 100
            return float(val)
        except (ValueError, TypeError):
            return None
    return None


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="财报分析脚本 - 自动化数据获取与比率计算",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 analyze_report.py sh600519
  python3 analyze_report.py sz000001 --periods 6 --output 报告.md
  python3 analyze_report.py hk00700

股票代码格式:
  沪市: sh600519  深市: sz000001  港股: hk00700  美股: usAAPL
        """,
    )
    parser.add_argument("stock_code", help="股票代码（如 sh600519）")
    parser.add_argument("--periods", type=int, default=4, help="获取报告期数（默认4）")
    parser.add_argument("--output", "-o", help="输出文件路径（默认输出到控制台）")
    parser.add_argument("--data-only", action="store_true", help="仅输出获取的原始数据，不生成分析报告")

    args = parser.parse_args()

    print(f"📊 正在获取 {args.stock_code} 的财务数据（最近{args.periods}期）...")

    data_list = fetch_financial_data(args.stock_code, args.periods)

    if not data_list:
        print("❌ 未能获取有效的财务数据，请检查股票代码或网络连接", file=sys.stderr)
        sys.exit(1)

    # 注册数据源到追踪器
    tracker.register_source("westock-data", "★★★★", f"finance·{args.stock_code}·最近{args.periods}期")
    
    # 为获取到的关键数据记录来源
    for d in data_list:
        period = d.get("report_date", "未知")
        for key in ["revenue", "net_profit", "operating_cf", "sales_cash", "capex",
                     "accounts_receivable", "inventory", "contract_liability",
                     "construction_in_progress", "fixed_assets", "cash",
                     "short_borrowing", "long_borrowing", "financial_expense"]:
            val = d.get(key)
            if val is not None:
                tracker.record(f"{key}_{period}", val, f"westock·finance·{args.stock_code}")

    if args.data_only:
        print(json.dumps(data_list, ensure_ascii=False, indent=2))
        return

    print(f"✅ 获取到 {len(data_list)} 期数据，开始分析...")

    analysis = analyze_financial_data(data_list)

    if "error" in analysis:
        print(f"❌ 分析失败: {analysis['error']}", file=sys.stderr)
        sys.exit(1)

    report = generate_report(args.stock_code, analysis, tracker)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"✅ 报告已保存到: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
