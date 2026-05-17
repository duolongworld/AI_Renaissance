#!/usr/bin/env python3
"""Build AI Renaissance financial Signal JSON from normalized financial data.

This script is a v2 scaffold. It keeps the skill boundary clear: data_sources
owns raw data fetching and field normalization; this script owns financial
rule evaluation and Signal-shaped output.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DataTracker:
    evidence: list[dict[str, Any]] = field(default_factory=list)
    red_flags: list[dict[str, Any]] = field(default_factory=list)

    def add_evidence(
        self,
        metric: str,
        value: Any,
        *,
        source_type: str,
        source_name: str,
        date: str,
        comparison: str = "",
        note: str = "",
    ) -> None:
        self.evidence.append(
            {
                "source_type": source_type,
                "source_name": source_name,
                "date": date,
                "metric": metric,
                "value": value,
                "comparison": comparison,
                "note": note,
            }
        )

    def add_red_flag(self, level: str, item: str, note: str) -> None:
        self.red_flags.append({"level": level, "item": item, "note": note})


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _normalize_finance_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize data source output into the fields used by the seven-step chain."""
    data = dict(raw)

    balance_row = _first_statement_row(data.get("balance"))
    income_row = _first_statement_row(data.get("income"))
    cashflow_row = _first_statement_row(data.get("cashflow"))

    if balance_row or income_row or cashflow_row:
        _set_default_value(data, "ticker", _first_value("unknown", balance_row, income_row, cashflow_row, key="SECUCODE"))
        _set_default_value(data, "company_name", _first_value("unknown", balance_row, income_row, cashflow_row, key="SECURITY_NAME_ABBR"))
        _set_default_value(data, "period", _first_value("unknown", balance_row, income_row, cashflow_row, key="REPORT_DATE_NAME"))
        data.setdefault("source_name", "东方财富财务报表")
        data.setdefault("source_type", "data_source")
        data.setdefault("balance_sheet_present", bool(balance_row))
        data.setdefault("income_statement_present", bool(income_row))
        data.setdefault("cash_flow_statement_present", bool(cashflow_row))

    _set_default_number(data, "operating_cash_flow", cashflow_row, "NETCASH_OPERATE")
    _set_default_number(data, "cash_received_from_sales", cashflow_row, "SALES_SERVICES")
    _set_default_number(data, "capex_cash_paid", cashflow_row, "CONSTRUCT_LONG_ASSET")
    _set_default_number(data, "net_profit_parent", income_row, "PARENT_NETPROFIT")
    _set_default_number(data, "revenue", income_row, "OPERATE_INCOME")
    _set_default_number(data, "operating_profit", income_row, "OPERATE_PROFIT")
    _set_default_number(data, "finance_expense", income_row, "FINANCE_EXPENSE")
    _set_default_number(data, "goodwill", balance_row, "GOODWILL")
    _set_default_number(data, "equity_parent", balance_row, "TOTAL_PARENT_EQUITY")
    _set_default_number(data, "receivable_growth", balance_row, "ACCOUNTS_RECE_YOY", scale=0.01)
    _set_default_number(data, "revenue_growth", income_row, "OPERATE_INCOME_YOY", scale=0.01)
    _set_default_number(data, "contract_liability_growth", balance_row, "CONTRACT_LIAB_YOY", scale=0.01)
    _set_default_number(data, "research_expense", income_row, "RESEARCH_EXPENSE")
    _set_default_number(data, "research_expense_growth", income_row, "RESEARCH_EXPENSE_YOY", scale=0.01)
    _set_default_number(data, "cash_and_equivalents", balance_row, "MONETARYFUNDS")

    industry = (data.get("industry") or data.get("industry_type") or "").lower()
    if industry in {"bank", "insurance", "broker", "银行", "保险", "券商"}:
        data["industry"] = {"银行": "bank", "保险": "insurance", "券商": "broker"}.get(industry, industry)

    return data


def _first_statement_row(statement: Any) -> dict[str, Any]:
    if isinstance(statement, dict):
        rows = statement.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        if "data" not in statement:
            return statement
    return {}


def _first_value(default: Any, *rows: dict[str, Any], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _set_default_value(data: dict[str, Any], target_key: str, value: Any) -> None:
    if data.get(target_key) in (None, "", "unknown"):
        data[target_key] = value


def _set_default_number(data: dict[str, Any], target_key: str, row: dict[str, Any], source_key: str, scale: float = 1.0) -> None:
    if target_key in data:
        return
    value = row.get(source_key)
    if value in (None, ""):
        return
    data[target_key] = float(value) * scale


def classify_business_stage(data: dict[str, Any]) -> dict[str, Any]:
    """Identify whether losses should be judged with a high-R&D commercialization lens."""
    rd_ratio = ratio(data.get("research_expense"), data.get("revenue"))
    cash_collection = ratio(data.get("cash_received_from_sales"), data.get("revenue"))
    revenue_growth = data.get("revenue_growth")
    contract_liability_growth = data.get("contract_liability_growth")
    receivable_growth = data.get("receivable_growth")

    high_rd = (rd_ratio is not None and rd_ratio >= 0.15) or (
        data.get("research_expense_growth") is not None and data.get("research_expense_growth") >= 0.3
    )
    commercialization_signals = {
        "revenue_high_growth": revenue_growth is not None and revenue_growth >= 0.3,
        "contract_liability_high_growth": contract_liability_growth is not None and contract_liability_growth >= 0.3,
        "cash_collection_strong": cash_collection is not None and cash_collection >= 0.9,
        "receivables_not_outpacing_revenue": (
            receivable_growth is not None
            and revenue_growth is not None
            and receivable_growth <= revenue_growth
        ),
    }
    commercialization_score = sum(commercialization_signals.values())
    stage = "rd_commercialization" if high_rd and commercialization_score >= 2 else "standard"

    return {
        "stage": stage,
        "rd_ratio": rd_ratio,
        "cash_collection_ratio": cash_collection,
        "high_rd": high_rd,
        "commercialization_score": commercialization_score,
        "commercialization_signals": commercialization_signals,
    }


def evaluate_steps(data: dict[str, Any], tracker: DataTracker, stage_context: dict[str, Any]) -> dict[str, str]:
    period = data.get("period", "unknown")
    source_name = data.get("source_name", "unknown source")
    source_type = data.get("source_type", "data_source")

    ocf_to_profit = ratio(data.get("operating_cash_flow"), data.get("net_profit_parent"))
    cash_collection = ratio(data.get("cash_received_from_sales"), data.get("revenue"))
    capex_to_depr = ratio(data.get("capex_cash_paid"), data.get("depreciation_amortization"))
    finance_cost_to_op_profit = ratio(data.get("finance_expense"), data.get("operating_profit"))
    goodwill_to_equity = ratio(data.get("goodwill"), data.get("equity_parent"))

    results: dict[str, str] = {}

    is_rd_commercialization = stage_context.get("stage") == "rd_commercialization"
    if data.get("net_profit_parent") is not None and data.get("net_profit_parent") <= 0:
        results["profit_quality"] = "watch" if is_rd_commercialization else "fail"
        if is_rd_commercialization:
            tracker.add_red_flag("medium", "研发商业化期亏损未收敛", "营收和合同负债高增，但归母净利润仍为负")
        else:
            tracker.add_red_flag("high", "归母净利润为负", "公司当期仍处亏损状态")
    elif data.get("operating_cash_flow") is not None and data.get("operating_cash_flow") < 0:
        results["profit_quality"] = "watch" if is_rd_commercialization else "fail"
        if is_rd_commercialization:
            tracker.add_red_flag("medium", "经营现金流仍为负", "商业化加速阶段仍需验证现金消耗收敛")
        else:
            tracker.add_red_flag("high", "经营现金流为负", "经营活动现金流净额为负")
    elif ocf_to_profit is None or cash_collection is None:
        results["profit_quality"] = "unknown"
    elif ocf_to_profit >= 1.0 and cash_collection >= 0.9:
        results["profit_quality"] = "pass"
    elif ocf_to_profit < 0.5 or cash_collection < 0.8:
        results["profit_quality"] = "fail"
        tracker.add_red_flag("high", "利润缺乏现金支撑", "现金利润比或销售收现显著偏低")
    else:
        results["profit_quality"] = "watch"

    if cash_collection is None:
        results["cash_flow_match"] = "unknown"
    elif cash_collection >= 0.9:
        results["cash_flow_match"] = "pass"
    else:
        results["cash_flow_match"] = "watch"

    if (
        is_rd_commercialization
        and data.get("operating_cash_flow") is not None
        and data.get("operating_cash_flow") < 0
        and not any(flag["item"] == "经营现金流仍为负" for flag in tracker.red_flags)
    ):
        tracker.add_red_flag("medium", "经营现金流仍为负", "商业化加速阶段仍需验证现金消耗收敛")

    receivable_growth = data.get("receivable_growth")
    revenue_growth = data.get("revenue_growth")
    contract_liability_growth = data.get("contract_liability_growth")
    if receivable_growth is None or revenue_growth is None:
        results["demand_authenticity"] = "unknown"
    elif receivable_growth <= revenue_growth and (contract_liability_growth is None or contract_liability_growth >= 0):
        results["demand_authenticity"] = "pass"
    else:
        results["demand_authenticity"] = "watch"
        tracker.add_red_flag("medium", "需求真实性待验证", "应收或合同负债与营收方向背离")

    if capex_to_depr is None:
        results["capex"] = "unknown"
    elif capex_to_depr >= 1.0:
        results["capex"] = "pass"
    else:
        results["capex"] = "watch"

    if data.get("operating_profit") is not None and data.get("operating_profit") <= 0 and data.get("finance_expense", 0) > 0:
        results["debt_rate_sensitivity"] = "watch"
        tracker.add_red_flag("medium", "营业利润为负且财务费用为正", "营业利润为负时财务费用压力不能按比例简单判为通过")
    elif finance_cost_to_op_profit is None:
        results["debt_rate_sensitivity"] = "unknown"
    elif finance_cost_to_op_profit > 0.2:
        results["debt_rate_sensitivity"] = "fail"
        tracker.add_red_flag("high", "财务费用侵蚀利润", "财务费用/营业利润超过 20%")
    elif finance_cost_to_op_profit > 0.1:
        results["debt_rate_sensitivity"] = "watch"
    else:
        results["debt_rate_sensitivity"] = "pass"

    if goodwill_to_equity is not None and goodwill_to_equity > 0.3:
        results["expansion_quality"] = "watch"
        tracker.add_red_flag("high", "商誉占归母权益过高", "商誉/归母权益超过 30%")
    else:
        results["expansion_quality"] = "pass"

    results["industry_adjustment"] = "pass" if data.get("industry") not in {"bank", "insurance", "broker"} else "fail"
    if results["industry_adjustment"] == "fail":
        tracker.add_red_flag("high", "金融行业不适用", "本 Skill 不适用于银行、保险、券商")

    for metric, value in {
        "net_profit_parent": data.get("net_profit_parent"),
        "revenue": data.get("revenue"),
        "operating_cash_flow": data.get("operating_cash_flow"),
        "operating_cash_flow_to_net_profit": ocf_to_profit,
        "cash_received_from_sales": data.get("cash_received_from_sales"),
        "cash_collection_ratio": cash_collection,
        "capex_cash_paid": data.get("capex_cash_paid"),
        "capex_to_depreciation": capex_to_depr,
        "finance_cost_to_operating_profit": finance_cost_to_op_profit,
        "goodwill_to_equity_parent": goodwill_to_equity,
        "research_expense": data.get("research_expense"),
        "research_expense_ratio": ratio(data.get("research_expense"), data.get("revenue")),
        "research_expense_growth": data.get("research_expense_growth"),
        "cash_and_equivalents": data.get("cash_and_equivalents"),
        "receivable_growth": data.get("receivable_growth"),
        "revenue_growth": data.get("revenue_growth"),
        "contract_liability_growth": data.get("contract_liability_growth"),
    }.items():
        if value is not None:
            tracker.add_evidence(
                metric,
                round(value, 4),
                source_type=source_type,
                source_name=source_name,
                date=period,
                comparison="computed",
                note="由归一化三表字段计算",
            )

    return results


def confidence_from_evidence(step_results: dict[str, str], tracker: DataTracker, missing_core_tables: bool) -> dict[str, Any]:
    evidence_count_score = 2 if len(tracker.evidence) >= 6 else 1 if len(tracker.evidence) >= 3 else 0
    source_types = {item.get("source_type") for item in tracker.evidence}
    independence_score = 2 if len(source_types) >= 3 else 1 if len(source_types) >= 2 else 0
    failed = sum(1 for value in step_results.values() if value == "fail")
    watch = sum(1 for value in step_results.values() if value == "watch")
    consistency_score = 2 if failed == 0 and watch <= 1 else 1 if failed <= 1 else 0
    reliable_sources = {"financial_report", "announcement", "data_source"}
    reliability_score = 2 if tracker.evidence and all(e.get("source_type") in reliable_sources for e in tracker.evidence) else 1

    total = evidence_count_score + independence_score + consistency_score + reliability_score
    cap = 0.4 if total <= 2 else 0.55 if total <= 4 else 0.7 if total <= 6 else 0.8 if total == 7 else 0.9
    if missing_core_tables:
        cap = min(cap, 0.4)
    if any(flag["level"] == "high" for flag in tracker.red_flags):
        cap = min(cap, 0.65)

    pass_count = sum(1 for value in step_results.values() if value == "pass")
    rule_strength = min(0.9, 0.35 + pass_count * 0.07)
    final_confidence = round(min(cap, rule_strength), 2)

    return {
        "evidence_count_score": evidence_count_score,
        "independence_score": independence_score,
        "consistency_score": consistency_score,
        "reliability_score": reliability_score,
        "total_score": total,
        "cap": cap,
        "final_confidence": final_confidence,
        "reason": "由 evidence 数量、独立性、一致性、可靠性反推",
    }


def choose_direction(step_results: dict[str, str], tracker: DataTracker) -> tuple[str, str, bool]:
    pass_count = sum(1 for value in step_results.values() if value == "pass")
    fail_count = sum(1 for value in step_results.values() if value == "fail")
    high_flags = sum(1 for flag in tracker.red_flags if flag["level"] == "high")

    if high_flags or fail_count >= 2 or pass_count <= 3:
        return "bearish", "high", True
    if pass_count >= 6 and not tracker.red_flags:
        return "bullish", "low", False
    return "neutral", "medium", False


def build_reasoning(data: dict[str, Any], step_results: dict[str, str], tracker: DataTracker, stage_context: dict[str, Any]) -> str:
    if data.get("summary"):
        return data["summary"]

    pass_count = sum(value == "pass" for value in step_results.values())
    if stage_context.get("stage") == "rd_commercialization":
        return (
            f"识别为高研发商业化过渡期，七步链通过 {pass_count} 项，红色预警 {len(tracker.red_flags)} 项。"
            "营收、合同负债和销售收现显示订单兑现加速，但亏损与经营现金流仍需验证收敛。"
        )

    return f"七步链通过 {pass_count} 项，红色预警 {len(tracker.red_flags)} 项。"


def build_signal_list(step_results: dict[str, str], stage_context: dict[str, Any]) -> list[str]:
    signals = []
    if stage_context.get("stage") == "rd_commercialization":
        signals.append("business_stage: rd_commercialization")

    signals.extend(
        f"{name}: {status}"
        for name, status in step_results.items()
        if status in {"pass", "fail", "watch"}
    )
    return signals[:6]


def build_signal(raw_data: dict[str, Any]) -> dict[str, Any]:
    data = _normalize_finance_data(raw_data)
    tracker = DataTracker()
    missing_core_tables = not all(data.get(key) for key in ("income_statement_present", "balance_sheet_present", "cash_flow_statement_present"))
    unsupported_industry = data.get("industry") in {"bank", "insurance", "broker"}

    stage_context = classify_business_stage(data)
    step_results = evaluate_steps(data, tracker, stage_context)
    if missing_core_tables:
        tracker.add_red_flag("high", "三表缺失", "利润表、资产负债表、现金流量表任一缺失时必须降置信")

    direction, risk_level, needs_review = choose_direction(step_results, tracker)
    confidence = confidence_from_evidence(step_results, tracker, missing_core_tables)
    unknown_count = sum(1 for value in step_results.values() if value == "unknown")
    insufficient_key_metrics = not tracker.evidence or unknown_count >= 4
    if insufficient_key_metrics:
        direction = "neutral"
        risk_level = "high"
        needs_review = True
        confidence["final_confidence"] = min(confidence["final_confidence"], 0.4)
        confidence["cap"] = min(confidence["cap"], 0.4)
        confidence["reason"] = "关键财务字段不足，强制降置信并转人工复核"
    if missing_core_tables:
        direction = "neutral"
        risk_level = "high"
        needs_review = True
    if unsupported_industry:
        direction = "neutral"
        risk_level = "high"
        needs_review = True
        confidence["final_confidence"] = min(confidence["final_confidence"], 0.4)
        confidence["cap"] = min(confidence["cap"], 0.4)
        confidence["reason"] = "金融行业不适用本 Skill，强制降置信并转人工复核"

    reasoning = build_reasoning(data, step_results, tracker, stage_context)
    signals = build_signal_list(step_results, stage_context)

    return {
        "direction": direction,
        "confidence": confidence["final_confidence"],
        "reasoning": reasoning,
        "signals": signals,
        "source": "financial-report-analysis",
        "signal_type": "financial",
        "stock_code": data.get("ticker", "unknown"),
        "weight": 1.0,
        "meta": {
            "output_version": "0.1",
            "skill_name": "financial-report-analysis",
            "owner_group": "专家1组（财务）",
            "target": data.get("ticker", "unknown"),
            "period": data.get("period", "unknown"),
            "time_horizon": "short",
            "risk_level": risk_level,
            "company_name": data.get("company_name", "unknown"),
            "business_stage": stage_context,
            "step_results": step_results,
            "red_flags": tracker.red_flags,
            "key_findings": signals,
            "confidence_breakdown": confidence,
            "evidence": tracker.evidence,
            "risk_notes": [flag["note"] for flag in tracker.red_flags],
            "uncertainties": [],
            "needs_human_review": needs_review,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args()

    signal = build_signal(json.loads(args.input_json.read_text(encoding="utf-8")))
    payload = json.dumps(signal, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
