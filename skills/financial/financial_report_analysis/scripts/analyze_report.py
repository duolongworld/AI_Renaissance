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
                **metric_info(metric),
                "value": value,
                "comparison": comparison,
                "note": note,
            }
        )

    def add_red_flag(self, level: str, item: str, note: str) -> None:
        self.red_flags.append({"level": level, "item": item, "note": note})


METRIC_CATALOG = {
    "net_profit_parent": ("归母净利润", "归属于母公司股东的净利润，衡量当期最终盈利。"),
    "revenue": ("营业收入", "公司主营业务和其他经营活动确认的收入。"),
    "gross_margin": ("毛利率", "营业收入扣除营业成本后的毛利占收入比例，衡量产品盈利能力。"),
    "operating_cash_flow": ("经营现金流净额", "经营活动产生的现金流量净额，衡量利润是否有现金支撑。"),
    "operating_cash_flow_qoq": ("经营现金流环比", "经营现金流净额相对上一报告期的变化；需要单季口径或累计数拆分后才可靠。"),
    "operating_cash_flow_to_net_profit": ("现金利润比", "经营现金流净额 / 归母净利润，用来验证利润含金量。"),
    "cash_received_from_sales": ("销售收现", "销售商品、提供劳务收到的现金，衡量客户真实付款。"),
    "cash_collection_ratio": ("销售收现率", "销售收现 / 营业收入，衡量收入兑现为现金的程度。"),
    "capex_cash_paid": ("资本开支现金支出", "购建固定资产、无形资产和其他长期资产支付的现金。"),
    "capex_to_depreciation": ("资本开支/折旧摊销", "资本开支现金支出 / 折旧摊销，衡量扩张投入是否覆盖资产消耗。"),
    "finance_cost_to_operating_profit": ("财务费用/营业利润", "财务费用占营业利润比例，衡量利息和融资成本压力。"),
    "goodwill_to_equity_parent": ("商誉/归母权益", "商誉占归母权益比例，衡量并购资产减值风险。"),
    "research_expense": ("研发费用", "当期费用化研发投入。"),
    "research_expense_qoq": ("研发费用环比", "研发费用相对上一报告期的变化；需要单季口径或累计数拆分后才可靠。"),
    "research_expense_ratio": ("研发费用率", "研发费用 / 营业收入，衡量研发投入强度。"),
    "research_expense_growth": ("研发费用同比增速", "研发费用相对去年同期的增长。"),
    "cash_and_equivalents": ("货币资金", "账面货币资金，衡量现金安全垫。"),
    "prepayment_growth": ("预付款同比增速", "预付款项相对去年同期的增长，可能反映供应链锁单或资金占用。"),
    "other_receivables_growth": ("其他应收同比增速", "其他应收款相对去年同期的增长，需关注关联方往来和资金占用。"),
    "other_payables_growth": ("其他应付同比增速", "其他应付款相对去年同期的增长，可能反映往来款或费用延后。"),
    "inventory_growth": ("存货同比增速", "存货相对去年同期的增长，用来验证备货和需求匹配。"),
    "fixed_asset_growth": ("固定资产同比增速", "固定资产相对去年同期的增长，反映产能/设备扩张。"),
    "intangible_asset_growth": ("无形资产同比增速", "无形资产相对去年同期的增长，科技公司常与技术/并购资产相关。"),
    "construction_in_progress_growth": ("在建工程同比增速", "在建工程相对去年同期的增长，反映尚未转固的建设投入。"),
    "total_noncurrent_assets_growth": ("非流动资产同比增速", "非流动资产相对去年同期的增长，衡量长期资产扩张。"),
    "receivable_growth": ("应收账款同比增速", "应收账款相对去年同期的增长，用来验证收入是否变成应收堆积。"),
    "revenue_growth": ("营收同比增速", "营业收入相对去年同期的增长。"),
    "revenue_qoq": ("营收环比", "营业收入相对上一报告期的变化；需要单季口径或累计数拆分后才可靠。"),
    "contract_liability_growth": ("合同负债同比增速", "合同负债相对去年同期的增长，常作为预收和订单前瞻代理。"),
    "contract_liability_qoq": ("合同负债环比", "合同负债相对上一报告期末的变化，观察订单前瞻是否继续加速。"),
    "receivable_qoq": ("应收账款环比", "应收账款相对上一报告期末的变化，观察收入增长是否转成应收压力。"),
    "prepayment_qoq": ("预付款环比", "预付款项相对上一报告期末的变化，观察供应链锁单或资金占用变化。"),
    "other_receivables_qoq": ("其他应收环比", "其他应收款相对上一报告期末的变化，观察关联方往来和资金占用变化。"),
    "other_payables_qoq": ("其他应付环比", "其他应付款相对上一报告期末的变化，观察往来款和费用延后变化。"),
    "inventory_qoq": ("存货环比", "存货相对上一报告期末的变化，观察备货是否加速。"),
    "cash_and_equivalents_qoq": ("货币资金环比", "货币资金相对上一报告期末的变化，观察现金安全垫变化。"),
    "fixed_asset_qoq": ("固定资产环比", "固定资产相对上一报告期末的变化，观察产能资产变化。"),
    "intangible_asset_qoq": ("无形资产环比", "无形资产相对上一报告期末的变化，观察技术/并购资产变化。"),
    "total_noncurrent_assets_qoq": ("非流动资产环比", "非流动资产相对上一报告期末的变化，观察长期资产扩张。"),
    "gross_margin_qoq": ("毛利率环比", "毛利率相对上一报告期的变化；需要单季收入和成本口径后才可靠。"),
    "signed_orders": ("已签订单", "已签署合同或订单金额，用于验证合同负债和后续收入兑现。"),
    "order_backlog": ("在手订单", "尚未交付或确认收入的订单储备，用于判断未来收入能见度。"),
    "capacity_expansion_plan": ("产能扩张计划", "公告或管理层披露的扩产、产线建设、项目投产计划。"),
    "supplier_long_term_agreements": ("供应商长协", "与关键供应商签署的长期供货协议，用于验证供给保障。"),
    "segments": ("业务分部", "按业务、地区或产品拆分的收入和利润结构。"),
    "product_lines": ("产品线", "按产品类别拆分的收入、增速、毛利率和订单结构。"),
    "top_customer_concentration": ("前五大客户集中度", "前五大客户收入占比，衡量大客户依赖和订单集中风险。"),
    "top_supplier_concentration": ("前五大供应商集中度", "前五大供应商采购占比，衡量供应链集中风险。"),
    "related_party_customer_ratio": ("关联方客户占比", "关联方客户收入占比，用于排查收入真实性和交易公允性。"),
    "related_party_supplier_ratio": ("关联方供应商占比", "关联方供应商采购占比，用于排查成本真实性和交易公允性。"),
    "capacity_utilization": ("产能利用率", "实际产出或使用产能占设计产能比例，验证扩产是否被需求吸收。"),
    "depreciation_amortization": ("折旧摊销", "固定资产折旧和无形资产摊销，反映资产消耗并用于计算资本开支覆盖。"),
    "asset_liability_ratio": ("资产负债率", "总负债 / 总资产，衡量财务杠杆和偿债压力。"),
    "rd_ratio": ("研发投入率", "研发投入或研发费用占营业收入比例，衡量科技公司的研发强度。"),
}


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
    previous_period_data = data.get("previous_period_data") if isinstance(data.get("previous_period_data"), dict) else {}
    previous_previous_period_data = (
        data.get("previous_previous_period_data")
        if isinstance(data.get("previous_previous_period_data"), dict)
        else {}
    )
    previous_balance_row = _first_statement_row(previous_period_data.get("balance"))
    previous_income_row = _first_statement_row(previous_period_data.get("income"))
    previous_cashflow_row = _first_statement_row(previous_period_data.get("cashflow"))
    previous_previous_income_row = _first_statement_row(previous_previous_period_data.get("income"))
    previous_previous_cashflow_row = _first_statement_row(previous_previous_period_data.get("cashflow"))

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
    _set_default_number(data, "operating_cost", income_row, "OPERATE_COST")
    _set_default_number(data, "goodwill", balance_row, "GOODWILL")
    _set_default_number(data, "equity_parent", balance_row, "TOTAL_PARENT_EQUITY")
    _set_default_number(data, "receivable_growth", balance_row, "ACCOUNTS_RECE_YOY", scale=0.01)
    _set_default_number(data, "revenue_growth", income_row, "OPERATE_INCOME_YOY", scale=0.01)
    _set_default_number(data, "contract_liability_growth", balance_row, "CONTRACT_LIAB_YOY", scale=0.01)
    _set_default_number(data, "research_expense", income_row, "RESEARCH_EXPENSE")
    _set_default_number(data, "research_expense_growth", income_row, "RESEARCH_EXPENSE_YOY", scale=0.01)
    _set_default_number(data, "cash_and_equivalents", balance_row, "MONETARYFUNDS")
    _set_default_number(data, "prepayment", balance_row, "PREPAYMENT")
    _set_default_number(data, "prepayment_growth", balance_row, "PREPAYMENT_YOY", scale=0.01)
    _set_default_number(data, "other_receivables", balance_row, "TOTAL_OTHER_RECE")
    _set_default_number(data, "other_receivables_growth", balance_row, "TOTAL_OTHER_RECE_YOY", scale=0.01)
    _set_default_number(data, "other_payables", balance_row, "TOTAL_OTHER_PAYABLE")
    _set_default_number(data, "other_payables_growth", balance_row, "TOTAL_OTHER_PAYABLE_YOY", scale=0.01)
    _set_default_number(data, "inventory", balance_row, "INVENTORY")
    _set_default_number(data, "inventory_growth", balance_row, "INVENTORY_YOY", scale=0.01)
    _set_default_number(data, "fixed_asset", balance_row, "FIXED_ASSET")
    _set_default_number(data, "fixed_asset_growth", balance_row, "FIXED_ASSET_YOY", scale=0.01)
    _set_default_number(data, "intangible_asset", balance_row, "INTANGIBLE_ASSET")
    _set_default_number(data, "intangible_asset_growth", balance_row, "INTANGIBLE_ASSET_YOY", scale=0.01)
    _set_default_number(data, "construction_in_progress", balance_row, "CIP")
    _set_default_number(data, "construction_in_progress_growth", balance_row, "CIP_YOY", scale=0.01)
    _set_default_number(data, "total_noncurrent_assets_growth", balance_row, "TOTAL_NONCURRENT_ASSETS_YOY", scale=0.01)
    _set_default_qoq(data, "contract_liability_qoq", balance_row, previous_balance_row, "CONTRACT_LIAB")
    _set_default_qoq(data, "receivable_qoq", balance_row, previous_balance_row, "ACCOUNTS_RECE")
    _set_default_qoq(data, "prepayment_qoq", balance_row, previous_balance_row, "PREPAYMENT")
    _set_default_qoq(data, "other_receivables_qoq", balance_row, previous_balance_row, "TOTAL_OTHER_RECE")
    _set_default_qoq(data, "other_payables_qoq", balance_row, previous_balance_row, "TOTAL_OTHER_PAYABLE")
    _set_default_qoq(data, "inventory_qoq", balance_row, previous_balance_row, "INVENTORY")
    _set_default_qoq(data, "cash_and_equivalents_qoq", balance_row, previous_balance_row, "MONETARYFUNDS")
    _set_default_qoq(data, "fixed_asset_qoq", balance_row, previous_balance_row, "FIXED_ASSET")
    _set_default_qoq(data, "intangible_asset_qoq", balance_row, previous_balance_row, "INTANGIBLE_ASSET")
    _set_default_qoq(data, "total_noncurrent_assets_qoq", balance_row, previous_balance_row, "TOTAL_NONCURRENT_ASSETS")
    _set_single_quarter_qoq(
        data,
        income_row,
        cashflow_row,
        previous_income_row,
        previous_cashflow_row,
        previous_previous_income_row,
        previous_previous_cashflow_row,
    )

    industry = (data.get("industry") or data.get("industry_type") or "").lower()
    if industry in {"bank", "insurance", "broker", "银行", "保险", "券商"}:
        data["industry"] = {"银行": "bank", "保险": "insurance", "券商": "broker"}.get(industry, industry)

    return data


def _first_statement_row(statement: Any) -> dict[str, Any]:
    if isinstance(statement, list) and statement and isinstance(statement[0], dict):
        return statement[0]
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


def _set_default_qoq(data: dict[str, Any], target_key: str, current_row: dict[str, Any], previous_row: dict[str, Any], source_key: str) -> None:
    if target_key in data:
        return
    current_value = current_row.get(source_key)
    previous_value = previous_row.get(source_key)
    qoq = ratio(current_value, previous_value)
    if qoq is not None:
        data[target_key] = qoq - 1.0


def _set_single_quarter_qoq(
    data: dict[str, Any],
    income_row: dict[str, Any],
    cashflow_row: dict[str, Any],
    previous_income_row: dict[str, Any],
    previous_cashflow_row: dict[str, Any],
    previous_previous_income_row: dict[str, Any],
    previous_previous_cashflow_row: dict[str, Any],
) -> None:
    current_report_date = _report_date_from_rows(data.get("period"), income_row, cashflow_row)
    previous_report_date = _report_date_from_rows(data.get("previous_report_date"), previous_income_row, previous_cashflow_row)
    previous_previous_report_date = _report_date_from_rows(
        data.get("previous_previous_report_date"),
        previous_previous_income_row,
        previous_previous_cashflow_row,
    )
    current_quarter = _single_quarter_metrics(
        income_row,
        cashflow_row,
        previous_income_row,
        previous_cashflow_row,
        current_report_date,
    )
    previous_quarter = _single_quarter_metrics(
        previous_income_row,
        previous_cashflow_row,
        previous_previous_income_row,
        previous_previous_cashflow_row,
        previous_report_date,
    )

    if not current_quarter or not previous_quarter:
        return

    qoq = {
        "revenue_qoq": _change_rate(current_quarter.get("revenue"), previous_quarter.get("revenue")),
        "research_expense_qoq": _change_rate(current_quarter.get("research_expense"), previous_quarter.get("research_expense")),
        "gross_margin_qoq": _change_rate(current_quarter.get("gross_margin"), previous_quarter.get("gross_margin")),
        "operating_cash_flow_qoq": _change_rate(
            current_quarter.get("operating_cash_flow"),
            previous_quarter.get("operating_cash_flow"),
        ),
    }
    for key, value in qoq.items():
        if value is not None and key not in data:
            data[key] = value

    data["single_quarter_metrics"] = {
        "current_report_date": current_report_date,
        "previous_report_date": previous_report_date,
        "previous_previous_report_date": previous_previous_report_date,
        "current_quarter": {key: _round_optional(value) for key, value in current_quarter.items()},
        "previous_quarter": {key: _round_optional(value) for key, value in previous_quarter.items()},
        "qoq": {key: _round_optional(value) for key, value in qoq.items() if value is not None},
    }


def _single_quarter_metrics(
    income_row: dict[str, Any],
    cashflow_row: dict[str, Any],
    base_income_row: dict[str, Any],
    base_cashflow_row: dict[str, Any],
    report_date: str | None,
) -> dict[str, float] | None:
    quarter_month = _quarter_end_month(report_date)
    if quarter_month is None:
        return None

    metrics = {
        "revenue": _single_quarter_value(income_row, base_income_row, "OPERATE_INCOME", quarter_month),
        "operating_cost": _single_quarter_value(income_row, base_income_row, "OPERATE_COST", quarter_month),
        "research_expense": _single_quarter_value(income_row, base_income_row, "RESEARCH_EXPENSE", quarter_month),
        "operating_cash_flow": _single_quarter_value(cashflow_row, base_cashflow_row, "NETCASH_OPERATE", quarter_month),
        "cash_received_from_sales": _single_quarter_value(cashflow_row, base_cashflow_row, "SALES_SERVICES", quarter_month),
        "capex_cash_paid": _single_quarter_value(cashflow_row, base_cashflow_row, "CONSTRUCT_LONG_ASSET", quarter_month),
    }
    if metrics["revenue"] is not None and metrics["operating_cost"] is not None:
        metrics["gross_margin"] = ratio(metrics["revenue"] - metrics["operating_cost"], metrics["revenue"])
    else:
        metrics["gross_margin"] = None

    available = {key: value for key, value in metrics.items() if value is not None}
    return available or None


def _single_quarter_value(row: dict[str, Any], base_row: dict[str, Any], source_key: str, quarter_month: int) -> float | None:
    value = _number_from_row(row, source_key)
    if value is None:
        return None
    if quarter_month == 3:
        return value
    base_value = _number_from_row(base_row, source_key)
    if base_value is None:
        return None
    return value - base_value


def _number_from_row(row: dict[str, Any], source_key: str) -> float | None:
    value = row.get(source_key)
    if value in (None, ""):
        return None
    return float(value)


def _report_date_from_rows(default: Any, *rows: dict[str, Any]) -> str | None:
    for row in rows:
        for key in ("REPORT_DATE", "REPORTDATE", "REPORT_DATE_NAME"):
            value = row.get(key)
            if value not in (None, "", "unknown"):
                return str(value)[:10]
    if default in (None, "", "unknown"):
        return None
    return str(default)[:10]


def _quarter_end_month(report_date: str | None) -> int | None:
    if not report_date:
        return None
    try:
        month = int(str(report_date)[5:7])
        day = int(str(report_date)[8:10])
    except (ValueError, IndexError):
        return None
    if (month, day) in {(3, 31), (6, 30), (9, 30), (12, 31)}:
        return month
    return None


def _change_rate(current_value: float | None, previous_value: float | None) -> float | None:
    value = ratio(current_value, previous_value)
    if value is None:
        return None
    return value - 1.0


def _round_optional(value: Any) -> Any:
    return round(value, 4) if isinstance(value, (float, int)) else value


def metric_info(metric: str) -> dict[str, str]:
    label, meaning = METRIC_CATALOG.get(metric, (metric, "暂未配置中文释义。"))
    return {"metric_label": label, "metric_meaning": meaning}


def metric_labels(metrics: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {metric: metric_info(metric) for metric in metrics}


def trend_confirmation_from_periods(data: dict[str, Any]) -> dict[str, Any]:
    """Use YoY and QoQ as separate evidence chains for confidence, not direction."""
    confirmations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    def add_confirmation(kind: str, item: str, metrics: list[str], note: str) -> None:
        confirmations.append({"kind": kind, "item": item, "metrics": metrics, "note": note})

    def add_conflict(item: str, metrics: list[str], note: str) -> None:
        conflicts.append({"item": item, "metrics": metrics, "note": note})

    revenue_growth = data.get("revenue_growth")
    revenue_qoq = data.get("revenue_qoq")
    if revenue_growth is not None and revenue_qoq is not None:
        if revenue_growth > 0 and revenue_qoq > 0:
            add_confirmation(
                "positive",
                "营收同比和单季环比同向增长",
                ["revenue_growth", "revenue_qoq"],
                "收入增长同时获得同比和单季环比验证。",
            )
        elif revenue_growth > 0 and revenue_qoq < -0.05:
            add_conflict(
                "营收同比增长但单季环比回落",
                ["revenue_growth", "revenue_qoq"],
                "同比增长可能受低基数或前期订单影响，最近一季收入动能需要复核。",
            )

    contract_liability_growth = data.get("contract_liability_growth")
    contract_liability_qoq = data.get("contract_liability_qoq")
    if contract_liability_growth is not None and contract_liability_qoq is not None:
        if contract_liability_growth >= 0.3 and contract_liability_qoq >= 0.05:
            add_confirmation(
                "positive",
                "合同负债同比和环比同向增长",
                ["contract_liability_growth", "contract_liability_qoq"],
                "订单/预收前瞻同时获得同比和环比验证。",
            )
        elif contract_liability_growth >= 0.3 and contract_liability_qoq <= -0.05:
            add_conflict(
                "合同负债同比高增但环比回落",
                ["contract_liability_growth", "contract_liability_qoq"],
                "同比改善可能受低基数影响，最近一季订单/预收趋势需要复核。",
            )

    receivable_growth = data.get("receivable_growth")
    receivable_qoq = data.get("receivable_qoq")
    if revenue_growth is not None and receivable_growth is not None and receivable_qoq is not None:
        if receivable_growth <= revenue_growth and receivable_qoq <= max(contract_liability_qoq or 0, 0.1):
            add_confirmation(
                "positive",
                "应收未明显跑赢收入且环比受控",
                ["receivable_growth", "receivable_qoq", "revenue_growth"],
                "收入增长没有同步表现为应收账款异常堆积。",
            )
        elif receivable_growth <= revenue_growth and receivable_qoq >= 0.3:
            add_conflict(
                "应收同比受控但环比抬升较快",
                ["receivable_growth", "receivable_qoq", "revenue_growth"],
                "最近一季回款压力可能上升，需要跟踪账期和客户结构。",
            )

    pressure_threshold = None if revenue_growth is None else max(revenue_growth * 1.5, revenue_growth + 0.5)
    prepayment_growth = data.get("prepayment_growth")
    prepayment_qoq = data.get("prepayment_qoq")
    if prepayment_growth is not None and prepayment_qoq is not None:
        if pressure_threshold is not None and prepayment_growth > pressure_threshold and prepayment_qoq > 0.3:
            add_confirmation(
                "risk",
                "预付款同比和环比共同抬升",
                ["prepayment_growth", "prepayment_qoq", "revenue_growth"],
                "供应链锁单、产能爬坡或资金占用风险获得跨期验证。",
            )
        elif pressure_threshold is not None and prepayment_growth > pressure_threshold and prepayment_qoq < -0.1:
            add_conflict(
                "预付款同比高增但环比回落",
                ["prepayment_growth", "prepayment_qoq", "revenue_growth"],
                "资金占用压力可能已边际缓解。",
            )

    other_receivables_growth = data.get("other_receivables_growth")
    other_receivables_qoq = data.get("other_receivables_qoq")
    if other_receivables_growth is not None and other_receivables_qoq is not None:
        if pressure_threshold is not None and other_receivables_growth > pressure_threshold and other_receivables_qoq > 0.3:
            add_confirmation(
                "risk",
                "其他应收同比和环比共同抬升",
                ["other_receivables_growth", "other_receivables_qoq", "revenue_growth"],
                "关联方往来、保证金或资金占用风险获得跨期验证。",
            )
        elif pressure_threshold is not None and other_receivables_growth > pressure_threshold and other_receivables_qoq < -0.1:
            add_conflict(
                "其他应收同比高增但环比回落",
                ["other_receivables_growth", "other_receivables_qoq", "revenue_growth"],
                "其他应收压力可能已边际缓解。",
            )

    asset_pairs = [
        ("固定资产", "fixed_asset_growth", "fixed_asset_qoq"),
        ("无形资产", "intangible_asset_growth", "intangible_asset_qoq"),
        ("非流动资产", "total_noncurrent_assets_growth", "total_noncurrent_assets_qoq"),
    ]
    asset_confirmed = [
        (label, yoy_metric, qoq_metric)
        for label, yoy_metric, qoq_metric in asset_pairs
        if data.get(yoy_metric) is not None and data.get(qoq_metric) is not None and data[yoy_metric] > 0.2 and data[qoq_metric] > 0.05
    ]
    if asset_confirmed:
        add_confirmation(
            "positive",
            "长期资产同比和环比共同扩张",
            [metric for _, yoy_metric, qoq_metric in asset_confirmed for metric in (yoy_metric, qoq_metric)],
            "长期资产扩张趋势获得跨期验证，但仍需订单和产能利用率解释扩张质量。",
        )
    elif any(data.get(yoy_metric) is not None and data.get(qoq_metric) is not None and data[yoy_metric] > 0.2 and data[qoq_metric] < -0.05 for _, yoy_metric, qoq_metric in asset_pairs):
        add_conflict(
            "长期资产同比扩张但环比收缩",
            [metric for _, yoy_metric, qoq_metric in asset_pairs for metric in (yoy_metric, qoq_metric) if data.get(yoy_metric) is not None and data.get(qoq_metric) is not None],
            "资产扩张的近期持续性不足，需要结合产能和项目进度复核。",
        )

    raw_score = min(3, len(confirmations)) - min(2, len(conflicts))
    adjustment = max(-0.06, min(0.06, raw_score * 0.03))
    return {
        "score": raw_score,
        "adjustment": adjustment,
        "confirmations": confirmations,
        "conflicts": conflicts,
    }


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
        "contract_liability_sequential_growth": data.get("contract_liability_qoq") is not None and data["contract_liability_qoq"] > 0,
        "cash_buffer_sequential_stable": data.get("cash_and_equivalents_qoq") is not None and data["cash_and_equivalents_qoq"] >= -0.2,
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


def commercial_inflection_from_metrics(data: dict[str, Any], stage_context: dict[str, Any]) -> dict[str, Any]:
    """Judge whether a high-R&D loss maker is showing a commercial inflection."""

    def item(name: str, status: str, metrics: list[str], note: str) -> dict[str, Any]:
        return {"item": name, "status": status, "metrics": metrics, "note": note}

    if stage_context.get("stage") != "rd_commercialization":
        return {
            "status": "not_applicable",
            "score": 0,
            "passed_items": [],
            "borderline_items": [],
            "failed_items": [],
            "protection_flags": [],
            "details": [],
            "summary": "非高研发商业化阶段，不启用商业化拐点规则。",
        }

    net_profit_margin = ratio(data.get("net_profit_parent"), data.get("revenue"))
    revenue_growth = data.get("revenue_growth")
    revenue_qoq = data.get("revenue_qoq")
    cash_collection = ratio(data.get("cash_received_from_sales"), data.get("revenue"))
    receivable_growth = data.get("receivable_growth")
    contract_liability_qoq = data.get("contract_liability_qoq")
    cash_buffer_qoq = data.get("cash_and_equivalents_qoq")
    operating_cash_flow_qoq = data.get("operating_cash_flow_qoq")

    details: list[dict[str, Any]] = []
    protection_flags: list[str] = []
    blocking_protection_flags: list[str] = []

    if revenue_growth is not None and revenue_qoq is not None and revenue_growth >= 0.15 and revenue_qoq >= 0:
        details.append(item("revenue_momentum", "pass", ["revenue_growth", "revenue_qoq"], "营收同比和单季环比均改善。"))
    elif revenue_growth is not None and revenue_qoq is not None and revenue_growth >= 0.30 and revenue_qoq >= -0.05:
        details.append(item("revenue_momentum", "borderline", ["revenue_growth", "revenue_qoq"], "营收同比强增长，单季环比仅小幅回落。"))
    else:
        details.append(item("revenue_momentum", "fail", ["revenue_growth", "revenue_qoq"], "营收同比或单季环比未达到拐点确认线。"))

    receivable_controlled = (
        receivable_growth is not None
        and revenue_growth is not None
        and receivable_growth <= revenue_growth
    )
    if cash_collection is not None and cash_collection >= 0.9:
        details.append(item("cash_collection", "pass", ["cash_collection_ratio"], "销售收现率达到收入现金兑现要求。"))
    elif cash_collection is not None and cash_collection >= 0.8 and receivable_controlled:
        details.append(item("cash_collection", "borderline", ["cash_collection_ratio", "receivable_growth", "revenue_growth"], "销售收现率接近达标，且应收未明显跑赢收入。"))
    else:
        details.append(item("cash_collection", "fail", ["cash_collection_ratio"], "销售收现率不足或缺少应收受控验证。"))

    if contract_liability_qoq is not None and contract_liability_qoq > 0:
        details.append(item("contract_liability", "pass", ["contract_liability_qoq"], "合同负债环比改善。"))
    elif contract_liability_qoq is not None and contract_liability_qoq >= -0.05 and cash_collection is not None and cash_collection >= 1.0:
        details.append(item("contract_liability", "borderline", ["contract_liability_qoq", "cash_collection_ratio"], "合同负债小幅回落，但销售收现较强。"))
    else:
        details.append(item("contract_liability", "fail", ["contract_liability_qoq"], "合同负债环比未体现订单前瞻改善。"))

    if cash_buffer_qoq is not None and cash_buffer_qoq >= -0.20:
        details.append(item("cash_buffer", "pass", ["cash_and_equivalents_qoq"], "货币资金环比未明显恶化。"))
    elif cash_buffer_qoq is not None and cash_buffer_qoq >= -0.30 and operating_cash_flow_qoq is not None and operating_cash_flow_qoq > 0:
        details.append(item("cash_buffer", "borderline", ["cash_and_equivalents_qoq", "operating_cash_flow_qoq"], "货币资金小幅承压，但经营现金流环比改善。"))
    else:
        details.append(item("cash_buffer", "fail", ["cash_and_equivalents_qoq", "operating_cash_flow_qoq"], "现金缓冲明显恶化或缺少现金流改善验证。"))

    passed_items = [entry["item"] for entry in details if entry["status"] == "pass"]
    borderline_items = [entry["item"] for entry in details if entry["status"] == "borderline"]
    failed_items = [entry["item"] for entry in details if entry["status"] == "fail"]
    thin_profit = net_profit_margin is not None and net_profit_margin < 0.03
    if "contract_liability" in borderline_items and thin_profit:
        protection_flags.append("contract_liability_borderline_with_thin_profit")
        blocking_protection_flags.append("contract_liability_borderline_with_thin_profit")
    if operating_cash_flow_qoq is not None and operating_cash_flow_qoq <= -1.0:
        protection_flags.append("operating_cash_flow_qoq_collapse")
    if (
        receivable_growth is not None
        and revenue_growth is not None
        and receivable_growth > max(revenue_growth * 1.5, revenue_growth + 0.5)
    ):
        protection_flags.append("receivable_growth_outpaces_revenue")
    if (
        "operating_cash_flow_qoq_collapse" in protection_flags
        and "receivable_growth_outpaces_revenue" in protection_flags
    ):
        blocking_protection_flags.append("cashflow_and_receivable_pressure")

    required_not_failed = all(
        entry["status"] in {"pass", "borderline"} for entry in details
    )
    status = (
        "pass"
        if "revenue_momentum" in passed_items
        and len(passed_items) >= 3
        and required_not_failed
        and not blocking_protection_flags
        else "watch"
    )

    return {
        "status": status,
        "score": len(passed_items),
        "passed_items": passed_items,
        "borderline_items": borderline_items,
        "failed_items": failed_items,
        "protection_flags": protection_flags,
        "blocking_protection_flags": blocking_protection_flags,
        "details": details,
        "summary": (
            "营收、收现、合同负债和现金缓冲共同支持商业化拐点。"
            if status == "pass"
            else "商业化拐点证据不足，维持观察。"
        ),
    }


def has_non_core_direction_gap(step_results: dict[str, str]) -> bool:
    """Return whether missing non-core fields should affect confidence, not direction."""
    non_core_steps = {"capex"}
    return any(
        step in non_core_steps and status == "unknown"
        for step, status in step_results.items()
    )


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
        "gross_margin": ratio(
            None if data.get("revenue") is None or data.get("operating_cost") is None else data.get("revenue") - data.get("operating_cost"),
            data.get("revenue"),
        ),
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
        "prepayment_growth": data.get("prepayment_growth"),
        "other_receivables_growth": data.get("other_receivables_growth"),
        "other_payables_growth": data.get("other_payables_growth"),
        "inventory_growth": data.get("inventory_growth"),
        "fixed_asset_growth": data.get("fixed_asset_growth"),
        "intangible_asset_growth": data.get("intangible_asset_growth"),
        "construction_in_progress_growth": data.get("construction_in_progress_growth"),
        "total_noncurrent_assets_growth": data.get("total_noncurrent_assets_growth"),
        "contract_liability_qoq": data.get("contract_liability_qoq"),
        "receivable_qoq": data.get("receivable_qoq"),
        "prepayment_qoq": data.get("prepayment_qoq"),
        "inventory_qoq": data.get("inventory_qoq"),
        "cash_and_equivalents_qoq": data.get("cash_and_equivalents_qoq"),
        "fixed_asset_qoq": data.get("fixed_asset_qoq"),
        "intangible_asset_qoq": data.get("intangible_asset_qoq"),
        "total_noncurrent_assets_qoq": data.get("total_noncurrent_assets_qoq"),
        "revenue_qoq": data.get("revenue_qoq"),
        "research_expense_qoq": data.get("research_expense_qoq"),
        "gross_margin_qoq": data.get("gross_margin_qoq"),
        "operating_cash_flow_qoq": data.get("operating_cash_flow_qoq"),
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


def evaluate_additional_checks(data: dict[str, Any], tracker: DataTracker) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    """Evaluate optional forward-looking checks and explicitly mark missing data."""
    data_gaps: list[dict[str, str]] = []
    iteration_plan: list[dict[str, str]] = []

    def missing(area: str, field: str, reason: str) -> None:
        data_gaps.append({"area": area, "field": field, "reason": reason})

    revenue_growth = data.get("revenue_growth")
    contract_liability_growth = data.get("contract_liability_growth")
    cash_collection = ratio(data.get("cash_received_from_sales"), data.get("revenue"))

    working_capital = {
        "status": "unknown",
        "summary": "缺少足够往来账字段，暂不能判断资金占用或费用延后。",
        "metrics": {
            "prepayment_growth": data.get("prepayment_growth"),
            "other_receivables_growth": data.get("other_receivables_growth"),
            "other_payables_growth": data.get("other_payables_growth"),
            "inventory_growth": data.get("inventory_growth"),
            "prepayment_qoq": data.get("prepayment_qoq"),
            "other_receivables_qoq": data.get("other_receivables_qoq"),
            "other_payables_qoq": data.get("other_payables_qoq"),
            "inventory_qoq": data.get("inventory_qoq"),
        },
    }
    working_capital["metric_labels"] = metric_labels(working_capital["metrics"])
    working_values = [value for value in working_capital["metrics"].values() if value is not None]
    if working_values:
        pressure = []
        if data.get("prepayment_growth") is not None and revenue_growth is not None and data["prepayment_growth"] > max(revenue_growth * 1.5, revenue_growth + 0.5):
            pressure.append("prepayment_outpaces_revenue")
            tracker.add_red_flag("medium", "预付款增速显著高于营收", "需排查供应商预付、产能爬坡或资金占用")
        if data.get("prepayment_qoq") is not None and data["prepayment_qoq"] > 0.5:
            pressure.append("prepayment_qoq_jump")
            tracker.add_red_flag("medium", "预付款环比大幅增长", "科技制造公司需解释是否为供应链锁单、产能爬坡或资金占用")
        if data.get("other_receivables_growth") is not None and revenue_growth is not None and data["other_receivables_growth"] > max(revenue_growth * 1.5, revenue_growth + 0.5):
            pressure.append("other_receivables_outpaces_revenue")
            tracker.add_red_flag("medium", "其他应收增速显著高于营收", "其他应收可能隐藏关联方往来或资金占用")
        if data.get("other_receivables_qoq") is not None and data["other_receivables_qoq"] > 0.5:
            pressure.append("other_receivables_qoq_jump")
            tracker.add_red_flag("medium", "其他应收环比大幅增长", "需复核关联方往来、保证金或资金占用")
        if data.get("inventory_growth") is not None and contract_liability_growth is not None and data["inventory_growth"] > max(contract_liability_growth * 1.5, contract_liability_growth + 0.5):
            pressure.append("inventory_outpaces_contract_liability")
            tracker.add_red_flag("medium", "存货增速显著高于合同负债", "备货增长缺少订单前瞻支撑时需警惕滞销")
        working_capital["status"] = "watch" if pressure else "pass"
        working_capital["summary"] = "往来账存在需复核项。" if pressure else "预付、其他应收和存货未显示明显异常扩张。"
        working_capital["pressure_items"] = pressure
    else:
        missing("working_capital_quality", "prepayment/other_receivables/other_payables/inventory", "当前数据源未提供可用往来账字段或增速。")

    capacity = {
        "status": "unknown",
        "summary": "capex 与产能验证数据不足。",
        "metrics": {
            "capex_cash_paid": data.get("capex_cash_paid"),
            "fixed_asset_growth": data.get("fixed_asset_growth"),
            "intangible_asset_growth": data.get("intangible_asset_growth"),
            "construction_in_progress_growth": data.get("construction_in_progress_growth"),
            "total_noncurrent_assets_growth": data.get("total_noncurrent_assets_growth"),
            "contract_liability_qoq": data.get("contract_liability_qoq"),
            "fixed_asset_qoq": data.get("fixed_asset_qoq"),
            "intangible_asset_qoq": data.get("intangible_asset_qoq"),
            "total_noncurrent_assets_qoq": data.get("total_noncurrent_assets_qoq"),
            "contract_liability_growth": contract_liability_growth,
            "prepayment_growth": data.get("prepayment_growth"),
        },
    }
    capacity["metric_labels"] = metric_labels(capacity["metrics"])
    capacity_values = [value for value in capacity["metrics"].values() if value is not None]
    if capacity_values:
        support_count = sum(
            bool(condition)
            for condition in (
                contract_liability_growth is not None and contract_liability_growth > 0,
                data.get("contract_liability_qoq") is not None and data["contract_liability_qoq"] > 0,
                revenue_growth is not None and revenue_growth > 0,
                data.get("prepayment_growth") is not None and data["prepayment_growth"] > 0,
            )
        )
        asset_growth_values = [
            data.get("fixed_asset_growth"),
            data.get("intangible_asset_growth"),
            data.get("construction_in_progress_growth"),
            data.get("total_noncurrent_assets_growth"),
        ]
        expanding_assets = any(value is not None and value > 0.2 for value in asset_growth_values)
        if expanding_assets and support_count >= 2:
            capacity["status"] = "pass"
            capacity["summary"] = "资产扩张与营收、合同负债或预付款存在一定同向支撑。"
        elif expanding_assets:
            capacity["status"] = "watch"
            capacity["summary"] = "资产扩张已出现，但订单、营收或供应链预付支撑不足。"
            tracker.add_red_flag("medium", "资产扩张缺少前瞻支撑", "需结合订单、合同负债、产能利用率和预付款验证扩产质量")
        else:
            capacity["status"] = "watch"
            capacity["summary"] = "未观察到明显固定资产/在建工程扩张，需结合产能利用率判断是否轻资产扩张。"
    else:
        missing("capacity_forward_validation", "capex/fixed_asset/cip/intangible_asset", "当前数据源未提供可用于产能交叉验证的资产扩张字段。")
    if data.get("depreciation_amortization") is None:
        missing("capacity_forward_validation", "depreciation_amortization", "东财三表接口未直接提供折旧摊销，无法计算 capex/折旧覆盖比。")
    if data.get("capacity_utilization") is None:
        missing("capacity_forward_validation", "capacity_utilization", "需要年报 MD&A 或公告原文提取产能利用率。")

    forward_orders = {
        "status": "partial",
        "summary": "当前仅能用合同负债和销售收现作为订单兑现代理指标。",
        "metrics": {
            "contract_liability_growth": contract_liability_growth,
            "contract_liability_qoq": data.get("contract_liability_qoq"),
            "cash_collection_ratio": cash_collection,
            "signed_orders": data.get("signed_orders"),
            "order_backlog": data.get("order_backlog"),
            "capacity_expansion_plan": data.get("capacity_expansion_plan"),
            "supplier_long_term_agreements": data.get("supplier_long_term_agreements"),
        },
    }
    forward_orders["metric_labels"] = metric_labels(forward_orders["metrics"])
    if contract_liability_growth is not None and contract_liability_growth > 0.3 and cash_collection is not None and cash_collection >= 0.9:
        forward_orders["summary"] = "合同负债和销售收现显示订单兑现加速，但仍缺少订单/产能计划原文验证。"
    for field in ("signed_orders", "order_backlog", "capacity_expansion_plan", "supplier_long_term_agreements"):
        if data.get(field) is None:
            missing("forward_orders_capacity", field, "需要公告、年报 MD&A、订单公告或供应商长协数据源。")
    for field in ("revenue_qoq", "research_expense_qoq", "gross_margin_qoq", "operating_cash_flow_qoq"):
        if data.get(field) is None:
            missing("sequential_trend", field, "利润表/现金流环比需要当前期、上一报告期和上上报告期累计数拆分单季；当前数据不足，未硬算。")

    segment_product = {
        "status": "not_implemented",
        "summary": "当前未接入 segment/product line 数据，无法判断产品线收入占比、增速和毛利率变化。",
        "metrics": {
            "segments": data.get("segments"),
            "product_lines": data.get("product_lines"),
        },
    }
    segment_product["metric_labels"] = metric_labels(segment_product["metrics"])
    if data.get("segments") or data.get("product_lines"):
        segment_product["status"] = "data_available_unmodeled"
        segment_product["summary"] = "已检测到 segment/product line 数据，但尚未实现结构化评分。"
    else:
        missing("segment_product_analysis", "segments/product_lines", "需要年报/季报原文或结构化产品线数据。")

    customer_supplier = {
        "status": "not_implemented",
        "summary": "当前未接入前五大客户/供应商和关联方占比数据。",
        "metrics": {
            "top_customer_concentration": data.get("top_customer_concentration"),
            "top_supplier_concentration": data.get("top_supplier_concentration"),
            "related_party_customer_ratio": data.get("related_party_customer_ratio"),
            "related_party_supplier_ratio": data.get("related_party_supplier_ratio"),
        },
    }
    customer_supplier["metric_labels"] = metric_labels(customer_supplier["metrics"])
    customer_supplier_values = [value for value in customer_supplier["metrics"].values() if value is not None]
    if customer_supplier_values:
        concentration_flags = []
        if data.get("top_customer_concentration") is not None and data["top_customer_concentration"] >= 0.5:
            concentration_flags.append("top_customer_concentration_high")
            tracker.add_red_flag("medium", "客户集中度较高", "大客户依赖可能同时代表订单优势和回款风险")
        if data.get("related_party_customer_ratio") is not None and data["related_party_customer_ratio"] >= 0.2:
            concentration_flags.append("related_party_customer_ratio_high")
            tracker.add_red_flag("medium", "关联方客户占比较高", "需排查收入真实性和交易公允性")
        customer_supplier["status"] = "watch" if concentration_flags else "pass"
        customer_supplier["summary"] = "客户/供应商结构存在需复核项。" if concentration_flags else "客户/供应商集中度未触发当前阈值。"
        customer_supplier["pressure_items"] = concentration_flags
    else:
        missing("customer_supplier_quality", "top_customers/top_suppliers/related_party_ratios", "需要年报前五大客户/供应商或供应链数据。")

    benchmark = {
        "status": "iteration_plan",
        "summary": "同行标杆横向比较必要，但暂不作为本轮重点。",
        "metrics": ["gross_margin", "cash_collection_ratio", "rd_ratio", "capex_to_depreciation", "asset_liability_ratio"],
    }
    iteration_plan.append({
        "area": "peer_benchmark",
        "priority": "next_iteration",
        "note": "需要可比公司池、行业分组和指标分位数后再进入评分。",
    })

    checks = {
        "working_capital_quality": working_capital,
        "capacity_forward_validation": capacity,
        "forward_orders_capacity": forward_orders,
        "segment_product_analysis": segment_product,
        "customer_supplier_quality": customer_supplier,
        "peer_benchmark": benchmark,
    }
    return checks, data_gaps, iteration_plan


def confidence_from_evidence(
    step_results: dict[str, str],
    tracker: DataTracker,
    missing_core_tables: bool,
    data: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    trend_confirmation = trend_confirmation_from_periods(data)
    evidence_count_score = 2 if len(tracker.evidence) >= 6 else 1 if len(tracker.evidence) >= 3 else 0
    source_types = {item.get("source_type") for item in tracker.evidence}
    independence_score = 2 if len(source_types) >= 3 else 1 if len(source_types) >= 2 else 0
    failed = sum(1 for value in step_results.values() if value == "fail")
    watch = sum(1 for value in step_results.values() if value == "watch")
    consistency_score = 2 if failed == 0 and watch <= 1 else 1 if failed <= 1 else 0
    reliable_sources = {"financial_report", "announcement", "data_source"}
    reliability_score = 2 if tracker.evidence and all(e.get("source_type") in reliable_sources for e in tracker.evidence) else 1
    cross_period_score = (
        2
        if len(trend_confirmation["confirmations"]) >= 2 and not trend_confirmation["conflicts"]
        else 1
        if trend_confirmation["confirmations"] or trend_confirmation["conflicts"]
        else 0
    )

    total = evidence_count_score + independence_score + consistency_score + reliability_score + cross_period_score
    cap = 0.4 if total <= 2 else 0.55 if total <= 4 else 0.7 if total <= 6 else 0.8 if total <= 8 else 0.9
    if missing_core_tables:
        cap = min(cap, 0.4)
    if any(flag["level"] == "high" for flag in tracker.red_flags):
        cap = min(cap, 0.65)

    conclusion_support_score = conclusion_support_from_steps(step_results, direction)
    rule_strength = min(0.9, max(0.0, conclusion_support_score + trend_confirmation["adjustment"]))
    final_confidence = round(min(cap, rule_strength), 2)

    return {
        "evidence_count_score": evidence_count_score,
        "independence_score": independence_score,
        "consistency_score": consistency_score,
        "reliability_score": reliability_score,
        "cross_period_score": cross_period_score,
        "total_score": total,
        "cap": cap,
        "conclusion_support_score": conclusion_support_score,
        "trend_confirmation": trend_confirmation,
        "rule_strength_after_trend_confirmation": rule_strength,
        "final_confidence": final_confidence,
        "reason": "由 evidence 数量、独立性、一致性、可靠性、同比/环比跨期确认共同反推",
    }


def conclusion_support_from_steps(step_results: dict[str, str], direction: str) -> float:
    """Score how strongly the step statuses support the chosen conclusion."""
    if not step_results:
        return 0.0

    score_map_by_direction = {
        "bullish": {"pass": 1.0, "watch": 0.45, "unknown": 0.2, "fail": 0.0},
        "bearish": {"fail": 1.0, "watch": 0.65, "unknown": 0.25, "pass": 0.25},
        "neutral": {"watch": 0.85, "pass": 0.9, "unknown": 0.35, "fail": 0.25},
    }
    score_map = score_map_by_direction.get(direction, score_map_by_direction["neutral"])
    support_score = sum(score_map.get(status, 0.0) for status in step_results.values()) / len(step_results)
    return round(min(0.9, max(0.0, support_score)), 4)


def choose_direction(
    step_results: dict[str, str],
    tracker: DataTracker,
    commercial_inflection: dict[str, Any] | None = None,
) -> tuple[str, str, bool]:
    pass_count = sum(1 for value in step_results.values() if value == "pass")
    watch_count = sum(1 for value in step_results.values() if value == "watch")
    fail_count = sum(1 for value in step_results.values() if value == "fail")
    high_flags = sum(1 for flag in tracker.red_flags if flag["level"] == "high")
    non_core_gap = has_non_core_direction_gap(step_results)

    if high_flags or fail_count >= 2 or pass_count <= 3:
        return "bearish", "high", True
    if commercial_inflection and commercial_inflection.get("blocking_protection_flags"):
        return "neutral", "medium", False
    if commercial_inflection and commercial_inflection.get("status") == "pass":
        return "bullish", "medium", False
    if pass_count >= 6 and not tracker.red_flags:
        return "bullish", "low", False
    if non_core_gap and pass_count >= 5 and watch_count <= 1 and not tracker.red_flags:
        return "bullish", "medium", False
    return "neutral", "medium", False


def build_reasoning(
    data: dict[str, Any],
    step_results: dict[str, str],
    tracker: DataTracker,
    stage_context: dict[str, Any],
    commercial_inflection: dict[str, Any] | None = None,
) -> str:
    if data.get("summary"):
        return data["summary"]

    pass_count = sum(value == "pass" for value in step_results.values())
    if commercial_inflection and commercial_inflection.get("status") == "pass":
        reasoning = (
            f"识别为高研发商业化过渡期，七步链通过 {pass_count} 项，红色预警 {len(tracker.red_flags)} 项。"
            "营收同比/环比改善、销售收现率达标、合同负债环比改善且现金缓冲未明显恶化，"
            "判定为商业化拐点观察偏多。"
        )
        if has_non_core_direction_gap(step_results):
            reasoning += " 折旧摊销等非核心数据缺口仅影响置信度，不直接改变方向判断。"
        return reasoning
    if stage_context.get("stage") == "rd_commercialization":
        return (
            f"识别为高研发商业化过渡期，七步链通过 {pass_count} 项，红色预警 {len(tracker.red_flags)} 项。"
            "营收、合同负债和销售收现显示订单兑现加速，但亏损与经营现金流仍需验证收敛。"
        )

    reasoning = f"七步链通过 {pass_count} 项，红色预警 {len(tracker.red_flags)} 项。"
    if has_non_core_direction_gap(step_results):
        reasoning += " 折旧摊销等非核心数据缺口仅影响置信度，不直接改变方向判断。"
    return reasoning


def build_signal_list(
    step_results: dict[str, str],
    stage_context: dict[str, Any],
    commercial_inflection: dict[str, Any] | None = None,
) -> list[str]:
    signals = []
    if stage_context.get("stage") == "rd_commercialization":
        signals.append("business_stage: rd_commercialization")
    if commercial_inflection and commercial_inflection.get("status") in {"pass", "watch"}:
        signals.append(f"commercial_inflection: {commercial_inflection['status']}")

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
    additional_checks, data_gaps, iteration_plan = evaluate_additional_checks(data, tracker)
    commercial_inflection = commercial_inflection_from_metrics(data, stage_context)
    if missing_core_tables:
        tracker.add_red_flag("high", "三表缺失", "利润表、资产负债表、现金流量表任一缺失时必须降置信")

    direction, risk_level, needs_review = choose_direction(step_results, tracker, commercial_inflection)
    confidence = confidence_from_evidence(step_results, tracker, missing_core_tables, data, direction)
    if has_non_core_direction_gap(step_results):
        confidence["final_confidence"] = max(0.0, round(confidence["final_confidence"] - 0.03, 2))
        confidence["reason"] += "；折旧摊销等非核心数据缺口小幅降低置信度"
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

    reasoning = build_reasoning(data, step_results, tracker, stage_context, commercial_inflection)
    signals = build_signal_list(step_results, stage_context, commercial_inflection)

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
            "commercial_inflection": commercial_inflection,
            "additional_checks": additional_checks,
            "single_quarter_metrics": data.get("single_quarter_metrics", {}),
            "step_results": step_results,
            "red_flags": tracker.red_flags,
            "key_findings": signals,
            "confidence_breakdown": confidence,
            "evidence": tracker.evidence,
            "data_gaps": data_gaps,
            "iteration_plan": iteration_plan,
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
