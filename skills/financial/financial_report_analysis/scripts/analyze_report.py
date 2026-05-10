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
    """Normalize input keys once data_sources finalizes field names.

    TODO(data_sources): align this mapping with data_sources/eastmoney.py and
    agents.signal.Signal. Until then, accept already-normalized demo keys.
    """

    return raw


def evaluate_steps(data: dict[str, Any], tracker: DataTracker) -> dict[str, str]:
    period = data.get("period", "unknown")
    source_name = data.get("source_name", "unknown source")
    source_type = data.get("source_type", "data_source")

    ocf_to_profit = ratio(data.get("operating_cash_flow"), data.get("net_profit_parent"))
    cash_collection = ratio(data.get("cash_received_from_sales"), data.get("revenue"))
    capex_to_depr = ratio(data.get("capex_cash_paid"), data.get("depreciation_amortization"))
    finance_cost_to_op_profit = ratio(data.get("finance_expense"), data.get("operating_profit"))
    goodwill_to_equity = ratio(data.get("goodwill"), data.get("equity_parent"))

    results: dict[str, str] = {}

    if ocf_to_profit is None or cash_collection is None:
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

    if finance_cost_to_op_profit is None:
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
        "operating_cash_flow_to_net_profit": ocf_to_profit,
        "cash_collection_ratio": cash_collection,
        "capex_to_depreciation": capex_to_depr,
        "finance_cost_to_operating_profit": finance_cost_to_op_profit,
        "goodwill_to_equity_parent": goodwill_to_equity,
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


def build_signal(raw_data: dict[str, Any]) -> dict[str, Any]:
    data = _normalize_finance_data(raw_data)
    tracker = DataTracker()
    missing_core_tables = not all(data.get(key) for key in ("income_statement_present", "balance_sheet_present", "cash_flow_statement_present"))
    unsupported_industry = data.get("industry") in {"bank", "insurance", "broker"}

    step_results = evaluate_steps(data, tracker)
    if missing_core_tables:
        tracker.add_red_flag("high", "三表缺失", "利润表、资产负债表、现金流量表任一缺失时必须降置信")

    direction, risk_level, needs_review = choose_direction(step_results, tracker)
    confidence = confidence_from_evidence(step_results, tracker, missing_core_tables)
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

    reasoning = data.get("summary") or f"七步链通过 {sum(v == 'pass' for v in step_results.values())} 项，红色预警 {len(tracker.red_flags)} 项。"
    signals = [
        f"{name}: {status}"
        for name, status in step_results.items()
        if status in {"pass", "fail", "watch"}
    ][:5]

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
