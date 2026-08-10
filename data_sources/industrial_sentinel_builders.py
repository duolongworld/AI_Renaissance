"""Financial statement builders for Industrial Sentinel.

Provider dictionaries are converted into company signals and controlled peer
proxies. The builders never fetch data and never manufacture missing values.
"""

from __future__ import annotations

from datetime import date, datetime
from statistics import median, pstdev
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def build_company_financial_signals(
    financial_data: Optional[Mapping[str, Any]],
    stock_code: str,
    stock_name: str = "",
    provider: str = "eastmoney",
) -> Dict[str, Any]:
    """Derive multi-period System B and peer-builder inputs from three statements."""
    data = dict(financial_data or {})
    income_rows = _statement_rows(data.get("income"))
    balance_rows = _statement_rows(data.get("balance"))
    cashflow_rows = _statement_rows(data.get("cashflow"))

    latest_income, previous_income = _latest_two(income_rows)
    latest_balance, previous_balance = _latest_two(balance_rows)
    latest_cashflow, previous_cashflow = _latest_two(cashflow_rows)
    income_periods = (_row_period(latest_income), _row_period(previous_income))
    balance_periods = (_row_period(latest_balance), _row_period(previous_balance))
    cashflow_periods = (_row_period(latest_cashflow), _row_period(previous_cashflow))
    report_period = income_periods[0] or balance_periods[0] or cashflow_periods[0]
    previous_report_period = income_periods[1] or balance_periods[1] or cashflow_periods[1]

    revenue = _first_number(latest_income, "OPERATE_INCOME", "TOTAL_OPERATE_INCOME")
    previous_revenue = _first_number(previous_income, "OPERATE_INCOME", "TOTAL_OPERATE_INCOME")
    operating_cost = _first_number(latest_income, "OPERATE_COST", "TOTAL_OPERATE_COST")
    previous_operating_cost = _first_number(previous_income, "OPERATE_COST", "TOTAL_OPERATE_COST")
    net_profit = _first_number(latest_income, "PARENT_NETPROFIT", "PARENT_NET_PROFIT")
    research_expense = _first_number(latest_income, "RESEARCH_EXPENSE", "RD_EXPENSE")

    reported_revenue_growth = _first_number(latest_income, "OPERATE_INCOME_YOY", "TOTAL_OPERATE_INCOME_YOY")
    previous_reported_revenue_growth = _first_number(
        previous_income,
        "OPERATE_INCOME_YOY",
        "TOTAL_OPERATE_INCOME_YOY",
    )
    revenue_growth = reported_revenue_growth
    if revenue_growth is None:
        revenue_growth = _growth_percent(revenue, previous_revenue)
    gross_margin = _ratio_percent(_difference(revenue, operating_cost), revenue)
    previous_gross_margin = _ratio_percent(
        _difference(previous_revenue, previous_operating_cost),
        previous_revenue,
    )
    gross_margin_change = _difference(gross_margin, previous_gross_margin)
    rd_ratio = _ratio_percent(research_expense, revenue)

    fixed_asset = _first_number(latest_balance, "FIXED_ASSET", "FIXED_ASSETS")
    total_asset = _first_number(
        latest_balance,
        "TOTAL_ASSETS",
        "TOTAL_LIAB_EQUITY",
        "TOTAL_ASSETS_END",
        "ASSETS_TOTAL",
    )
    total_liabilities = _first_number(
        latest_balance,
        "TOTAL_LIABILITIES",
        "TOTAL_LIAB",
        "LIABILITIES_TOTAL",
    )
    parent_equity = _first_number(latest_balance, "TOTAL_PARENT_EQUITY", "PARENT_EQUITY")
    asset_lightness = None
    if fixed_asset is not None and total_asset and total_asset > 0:
        asset_lightness = max(0.0, min(1.0, 1.0 - fixed_asset / total_asset))

    contract_liability = _first_number(
        latest_balance,
        "CONTRACT_LIAB",
        "CONTRACT_LIABILITIES",
        "CONTRACT_LIABILITY",
        "ADVANCE_RECEIVABLES",
    )
    previous_contract_liability = _first_number(
        previous_balance,
        "CONTRACT_LIAB",
        "CONTRACT_LIABILITIES",
        "CONTRACT_LIABILITY",
        "ADVANCE_RECEIVABLES",
    )
    reported_contract_liability_growth = _first_number(
        latest_balance,
        "CONTRACT_LIAB_YOY",
        "CONTRACT_LIABILITIES_YOY",
    )
    previous_reported_contract_liability_growth = _first_number(
        previous_balance,
        "CONTRACT_LIAB_YOY",
        "CONTRACT_LIABILITIES_YOY",
    )
    contract_liability_growth_qoq = _growth_percent(contract_liability, previous_contract_liability)
    contract_liability_growth = contract_liability_growth_qoq

    inventory = _first_number(latest_balance, "INVENTORY", "INVENTORIES")
    previous_inventory = _first_number(previous_balance, "INVENTORY", "INVENTORIES")
    inventory_days = _inventory_days(inventory, operating_cost, balance_periods[0])
    previous_inventory_days = _inventory_days(
        previous_inventory,
        previous_operating_cost,
        balance_periods[1],
    )
    inventory_days_change = _difference(inventory_days, previous_inventory_days)

    construction_in_progress = _first_number(
        latest_balance,
        "CIP",
        "CONSTRUCTION_IN_PROGRESS",
    )
    previous_cip = _first_number(
        previous_balance,
        "CIP",
        "CONSTRUCTION_IN_PROGRESS",
    )
    construction_in_progress_growth = _growth_percent(construction_in_progress, previous_cip)

    capex = _first_number(
        latest_cashflow,
        "CONSTRUCT_LONG_ASSET",
        "CASH_PAID_FOR_FIXED_ASSETS",
        "PURCHASE_FIXED_ASSETS_CASH",
    )
    previous_capex = _first_number(
        previous_cashflow,
        "CONSTRUCT_LONG_ASSET",
        "CASH_PAID_FOR_FIXED_ASSETS",
        "PURCHASE_FIXED_ASSETS_CASH",
    )
    capex_growth = _growth_percent(capex, previous_capex)
    operating_cash_flow = _first_number(
        latest_cashflow,
        "NETCASH_OPERATE",
        "NET_CASH_FLOWS_OPER_ACT",
        "NET_CASHFLOW_OPERATE",
    )
    operating_cash_flow_to_net_profit = _ratio(operating_cash_flow, net_profit)

    profit_stability = _profit_stability(income_rows)
    annual_net_profits = [
        _first_number(row, "PARENT_NETPROFIT", "PARENT_NET_PROFIT")
        for row in income_rows
        if _row_period(row).endswith("12-31")
    ][:3]
    annual_periods = [
        _row_period(row)
        for row in income_rows
        if _row_period(row).endswith("12-31")
        and _first_number(row, "PARENT_NETPROFIT", "PARENT_NET_PROFIT") is not None
    ][:3]
    signals = _drop_none(
        {
            "revenue_growth": revenue_growth,
            "gross_margin": gross_margin,
            "gross_margin_change": gross_margin_change,
            "rd_ratio": rd_ratio,
            "research_expense_ratio": rd_ratio,
            "fixed_asset": fixed_asset,
            "total_asset": total_asset,
            "net_profit_parent": net_profit,
            "roe": _ratio(net_profit, parent_equity),
            "debt_ratio": _ratio(total_liabilities, total_asset),
            "asset_lightness": asset_lightness,
            "profit_stability": profit_stability,
            "contract_liability": contract_liability,
            "contract_liability_growth": contract_liability_growth,
            "contract_liability_growth_yoy": reported_contract_liability_growth,
            "contract_liability_growth_qoq": contract_liability_growth_qoq,
            "inventory_days": inventory_days,
            "inventory_days_change": inventory_days_change,
            "capex": capex,
            "capex_growth": capex_growth,
            "construction_in_progress": construction_in_progress,
            "construction_in_progress_growth": construction_in_progress_growth,
            "operating_cash_flow": operating_cash_flow,
            "operating_cash_flow_to_net_profit": operating_cash_flow_to_net_profit,
        }
    )
    raw_inputs = {
        "revenue_growth": (
            {
                "OPERATE_INCOME_YOY.current": reported_revenue_growth,
                "OPERATE_INCOME_YOY.previous": previous_reported_revenue_growth,
            }
            if reported_revenue_growth is not None and previous_reported_revenue_growth is not None
            else {
                "OPERATE_INCOME.current": revenue,
                "OPERATE_INCOME.previous": previous_revenue,
            }
        ),
        "gross_margin": {"OPERATE_INCOME.current": revenue, "OPERATE_COST.current": operating_cost},
        "gross_margin_change": {
            "OPERATE_INCOME.current": revenue,
            "OPERATE_COST.current": operating_cost,
            "OPERATE_INCOME.previous": previous_revenue,
            "OPERATE_COST.previous": previous_operating_cost,
        },
        "rd_ratio": {"RESEARCH_EXPENSE.current": research_expense, "OPERATE_INCOME.current": revenue},
        "research_expense_ratio": {"RESEARCH_EXPENSE.current": research_expense, "OPERATE_INCOME.current": revenue},
        "fixed_asset": {"FIXED_ASSET.current": fixed_asset},
        "total_asset": {"TOTAL_ASSETS.current": total_asset},
        "net_profit_parent": {"PARENT_NETPROFIT.current": net_profit},
        "roe": {"PARENT_NETPROFIT.current": net_profit, "TOTAL_PARENT_EQUITY.current": parent_equity},
        "debt_ratio": {"TOTAL_LIABILITIES.current": total_liabilities, "TOTAL_ASSETS.current": total_asset},
        "asset_lightness": {"FIXED_ASSET.current": fixed_asset, "TOTAL_ASSETS.current": total_asset},
        "profit_stability": {"PARENT_NETPROFIT.annual_3y": annual_net_profits},
        "contract_liability": {"CONTRACT_LIAB.current": contract_liability},
        "contract_liability_growth": {
            "CONTRACT_LIAB.current": contract_liability,
            "CONTRACT_LIAB.previous": previous_contract_liability,
        },
        "contract_liability_growth_yoy": {
            "CONTRACT_LIAB_YOY.current": reported_contract_liability_growth,
            "CONTRACT_LIAB_YOY.previous": previous_reported_contract_liability_growth,
        },
        "contract_liability_growth_qoq": {
            "CONTRACT_LIAB.current": contract_liability,
            "CONTRACT_LIAB.previous": previous_contract_liability,
        },
        "inventory_days": {"INVENTORY.current": inventory, "OPERATE_COST.current": operating_cost},
        "inventory_days_change": {
            "INVENTORY.current": inventory,
            "OPERATE_COST.current": operating_cost,
            "INVENTORY.previous": previous_inventory,
            "OPERATE_COST.previous": previous_operating_cost,
        },
        "capex": {"CONSTRUCT_LONG_ASSET.current": capex},
        "capex_growth": {"CONSTRUCT_LONG_ASSET.current": capex, "CONSTRUCT_LONG_ASSET.previous": previous_capex},
        "construction_in_progress": {"CONSTRUCTION_IN_PROGRESS.current": construction_in_progress},
        "construction_in_progress_growth": {
            "CONSTRUCTION_IN_PROGRESS.current": construction_in_progress,
            "CONSTRUCTION_IN_PROGRESS.previous": previous_cip,
        },
        "operating_cash_flow": {"NETCASH_OPERATE.current": operating_cash_flow},
        "operating_cash_flow_to_net_profit": {
            "NETCASH_OPERATE.current": operating_cash_flow,
            "PARENT_NETPROFIT.current": net_profit,
        },
    }
    comparison_operands = {
        "revenue_growth": _drop_none({
            "current": reported_revenue_growth,
            "previous": previous_reported_revenue_growth,
        }),
        "gross_margin_change": _drop_none({
            "current": gross_margin,
            "previous": previous_gross_margin,
        }),
        "contract_liability_growth": _drop_none({
            "current": contract_liability,
            "previous": previous_contract_liability,
        }),
        "contract_liability_growth_yoy": _drop_none({
            "current": reported_contract_liability_growth,
            "previous": previous_reported_contract_liability_growth,
        }),
        "contract_liability_growth_qoq": _drop_none({
            "current": contract_liability,
            "previous": previous_contract_liability,
        }),
        "inventory_days_change": _drop_none({
            "current": inventory_days,
            "previous": previous_inventory_days,
        }),
        "capex_growth": _drop_none({
            "current": capex,
            "previous": previous_capex,
        }),
        "construction_in_progress_growth": _drop_none({
            "current": construction_in_progress,
            "previous": previous_cip,
        }),
    }
    income_fields = {
        "revenue_growth", "gross_margin", "gross_margin_change", "rd_ratio",
        "research_expense_ratio", "net_profit_parent",
    }
    balance_fields = {
        "fixed_asset", "total_asset", "debt_ratio", "asset_lightness",
        "contract_liability", "contract_liability_growth",
        "contract_liability_growth_yoy", "contract_liability_growth_qoq",
        "construction_in_progress", "construction_in_progress_growth",
    }
    cashflow_fields = {"capex", "capex_growth", "operating_cash_flow"}
    field_periods = {field: income_periods for field in income_fields}
    field_periods.update({field: balance_periods for field in balance_fields})
    field_periods.update({field: cashflow_periods for field in cashflow_fields})
    field_periods["roe"] = _aligned_periods(income_periods, balance_periods)
    field_periods["inventory_days"] = _aligned_periods(income_periods, balance_periods)
    field_periods["inventory_days_change"] = _aligned_periods(income_periods, balance_periods)
    field_periods["operating_cash_flow_to_net_profit"] = _aligned_periods(income_periods, cashflow_periods)
    field_periods["profit_stability"] = (
        annual_periods[0] if annual_periods else "",
        annual_periods[1] if len(annual_periods) > 1 else "",
    )

    evidence = []
    for field_name, value in signals.items():
        field_report_period, field_previous_period = field_periods.get(field_name, ("", ""))
        if not field_report_period:
            continue
        evidence.append({
            "field_path": f"company_signals.{field_name}",
            "scope": "company",
            "source_level": "L1",
            "source_type": "financial_report",
            "source_title": f"{provider} 财务报表",
            "provider": provider,
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "report_period": field_report_period,
            "previous_report_period": field_previous_period,
            "as_of_date": field_report_period,
            "value": value,
            "raw_fields": list(raw_inputs.get(field_name, {})),
            "raw_values": _drop_none(raw_inputs.get(field_name, {})),
            "comparison_operands": comparison_operands.get(field_name, {}),
            "derivation_method": _company_derivation(field_name),
            "aggregation_method": None,
        })
    evidenced_fields = {
        str(item.get("field_path") or "").rsplit(".", 1)[-1]
        for item in evidence
    }
    signals = {
        field_name: value
        for field_name, value in signals.items()
        if field_name in evidenced_fields
    }
    return {
        "company_signals": signals,
        "evidence": evidence,
        "report_period": report_period,
        "previous_report_period": previous_report_period,
    }


def build_peer_basket(
    peer_financial_data: Mapping[str, Any],
    target_code: str,
    provider: str = "eastmoney",
    methodology_profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate comparable-company financials into controlled peer proxies."""
    built_members: List[Dict[str, Any]] = []
    for code, raw in dict(peer_financial_data or {}).items():
        if _clean_code(code) == _clean_code(target_code):
            continue
        wrapper = dict(raw or {})
        financial = wrapper.get("financial_data") if isinstance(wrapper.get("financial_data"), Mapping) else wrapper
        stock_name = str(wrapper.get("stock_name") or code)
        built = build_company_financial_signals(financial, code, stock_name, provider)
        if built["report_period"]:
            built_members.append(
                {
                    "stock_code": code,
                    "stock_name": stock_name,
                    **built,
                }
            )

    if not built_members:
        return {"peer_basket_signals": {}, "peer_basket_meta": {}, "evidence": []}

    period = _most_common(item["report_period"] for item in built_members)
    previous_period = _most_common(
        item["previous_report_period"]
        for item in built_members
        if item.get("previous_report_period")
    )
    aligned = [
        item for item in built_members
        if item["report_period"] == period
    ]
    total = len(aligned)
    if total == 0:
        return {"peer_basket_signals": {}, "peer_basket_meta": {}, "evidence": []}

    aggregate_fields = {
        "revenue_growth_median": ("revenue_growth", False),
        "gross_margin_median": ("gross_margin", False),
        "gross_margin_change_median": ("gross_margin_change", False),
        "contract_liability_growth_median": ("contract_liability_growth", False),
        "contract_liability_growth_yoy_median": ("contract_liability_growth_yoy", False),
        "contract_liability_growth_qoq_median": ("contract_liability_growth_qoq", False),
        "inventory_days_median": ("inventory_days", False),
        "inventory_days_change_median": ("inventory_days_change", True),
        "capex_growth_median": ("capex_growth", False),
        "construction_in_progress_growth_median": ("construction_in_progress_growth", False),
        "operating_cash_flow_to_net_profit_median": ("operating_cash_flow_to_net_profit", False),
    }
    signals: Dict[str, Any] = {}
    agreement: Dict[str, float] = {}
    directions: Dict[str, str] = {}
    coverage_by_field: Dict[str, float] = {}
    previous_period_by_field: Dict[str, str] = {}
    evidence: List[Dict[str, Any]] = []

    profile_comparisons = _profile_comparisons(methodology_profile)
    for peer_field, (company_field, invert_direction) in aggregate_fields.items():
        candidates: List[Tuple[Dict[str, Any], float, Dict[str, Any]]] = []
        for member in aligned:
            value = _number(member["company_signals"].get(company_field))
            member_evidence = next(
                (
                    item
                    for item in member.get("evidence") or []
                    if item.get("field_path") == f"company_signals.{company_field}"
                ),
                {},
            )
            if (
                value is not None
                and str(member_evidence.get("report_period") or "")[:10] == period
                and str(member_evidence.get("previous_report_period") or "")[:10]
            ):
                candidates.append((member, value, dict(member_evidence)))
        field_previous_period = _most_common(
            str(item[2].get("previous_report_period") or "")[:10]
            for item in candidates
        )
        values = [
            item for item in candidates
            if str(item[2].get("previous_report_period") or "")[:10] == field_previous_period
        ]
        if not values:
            continue
        numbers = [value for _, value, _ in values]
        aggregate = float(median(numbers))
        is_context = peer_field in {"gross_margin_median", "inventory_days_median"}
        member_directions = [
            _evidence_direction(value, member_evidence, invert_direction)
            for _, value, member_evidence in values
        ]
        positive = sum(1 for item in member_directions if item == "improving")
        negative = sum(1 for item in member_directions if item == "deteriorating")
        direction = (
            "context"
            if is_context
            else "improving" if positive > negative
            else "deteriorating" if negative > positive
            else "mixed"
        )
        denominator = max(len(numbers), 1)
        signals[peer_field] = aggregate
        agreement[peer_field] = 1.0 if is_context else max(positive, negative) / denominator
        directions[peer_field] = direction
        coverage_by_field[peer_field] = len(numbers) / total
        previous_period_by_field[peer_field] = field_previous_period
        for (member, value, member_evidence), member_direction in zip(values, member_directions):
            evidence.append(
                {
                    "field_path": f"peer_basket_signals.{peer_field}",
                    "scope": "peer_basket",
                    "source_level": "L1",
                    "source_type": "financial_report",
                    "source_title": f"{provider} 同业财报聚合",
                    "provider": provider,
                    "member_stock_code": member["stock_code"],
                    "member_stock_name": member["stock_name"],
                    "report_period": period,
                    "previous_report_period": field_previous_period,
                    "as_of_date": period,
                    "value": value,
                    "aggregate_value": aggregate,
                    "raw_fields": member_evidence.get("raw_fields") or [],
                    "raw_values": member_evidence.get("raw_values") or {},
                    "comparison": profile_comparisons.get(peer_field) or "",
                    "comparison_operands": member_evidence.get("comparison_operands") or {},
                    "member_direction": member_direction,
                    "derivation_method": member_evidence.get("derivation_method") or _company_derivation(company_field),
                    "aggregation_method": "median",
                    "derived_field": company_field,
                }
            )

    members = [
        {"stock_code": item["stock_code"], "stock_name": item["stock_name"]}
        for item in aligned
    ]
    coverage_ratio = min(coverage_by_field.values()) if coverage_by_field else 0.0
    return {
        "peer_basket_signals": signals,
        "peer_basket_meta": {
            "members": members,
            "sample_size": len(members),
            "report_period": period,
            "previous_report_period": previous_period,
            "previous_report_period_by_field": previous_period_by_field,
            "aggregation_method": "median",
            "coverage_ratio": coverage_ratio,
            "coverage_ratio_by_field": coverage_by_field,
            "agreement_ratio_by_field": agreement,
            "direction_by_field": directions,
            "comparison_by_field": profile_comparisons,
        },
        "evidence": evidence,
    }


def _statement_rows(statement: Any) -> List[Dict[str, Any]]:
    if isinstance(statement, list):
        rows = [dict(item) for item in statement if isinstance(item, Mapping)]
    elif isinstance(statement, Mapping):
        data = statement.get("data")
        if isinstance(data, list):
            rows = [dict(item) for item in data if isinstance(item, Mapping)]
        elif "data" not in statement:
            rows = [dict(statement)]
        else:
            rows = []
    else:
        rows = []
    return sorted(rows, key=lambda item: _row_period(item) or "", reverse=True)


def _latest_two(rows: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    return (rows[0] if rows else {}, rows[1] if len(rows) > 1 else {})


def _aligned_periods(*period_pairs: Tuple[str, str]) -> Tuple[str, str]:
    current = {pair[0] for pair in period_pairs if pair[0]}
    previous = {pair[1] for pair in period_pairs if pair[1]}
    if len(current) != 1 or len(previous) != 1:
        return "", ""
    return next(iter(current)), next(iter(previous))


def _profile_comparisons(profile: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """Map peer packet fields to the selected Profile comparison semantics."""
    result: Dict[str, str] = {}
    for indicators in dict((profile or {}).get("indicators") or {}).values():
        for indicator in indicators or []:
            if not isinstance(indicator, Mapping):
                continue
            path = str(indicator.get("field_path") or "")
            if path.startswith("peer_basket_signals."):
                result[path.split(".", 1)[1]] = str(indicator.get("comparison") or "")
    return result


def _evidence_direction(
    value: float,
    evidence: Mapping[str, Any],
    invert_direction: bool,
) -> str:
    """Vote on the actual cross-period operands, not merely the reported level."""
    operands = evidence.get("comparison_operands")
    if isinstance(operands, Mapping):
        current = _number(operands.get("current"))
        previous = _number(operands.get("previous"))
        if current is None or previous is None:
            return "unknown"
        delta = current - previous
    else:
        delta = value
    if delta == 0:
        return "neutral"
    improving = delta < 0 if invert_direction else delta > 0
    return "improving" if improving else "deteriorating"


def _row_period(row: Mapping[str, Any]) -> str:
    for key in ("REPORT_DATE", "REPORTDATE", "REPORT_PERIOD", "DATE", "NOTICE_DATE"):
        value = row.get(key)
        if value:
            return str(value)[:10]
    return ""


def _profit_stability(income_rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
    annual = []
    for row in income_rows:
        period = _row_period(row)
        if period.endswith("12-31"):
            value = _first_number(row, "PARENT_NETPROFIT", "PARENT_NET_PROFIT")
            if value is not None:
                annual.append(value)
        if len(annual) == 3:
            break
    if len(annual) < 3:
        return None
    mean_abs = sum(abs(value) for value in annual) / len(annual)
    if mean_abs == 0:
        return 0.0
    coefficient = pstdev(annual) / mean_abs
    return max(0.0, min(1.0, 1.0 - coefficient))


def _inventory_days(inventory: Optional[float], cost: Optional[float], period: str) -> Optional[float]:
    if inventory is None or cost is None or cost <= 0:
        return None
    days = _period_days(period)
    return inventory / cost * days


def _period_days(period: str) -> int:
    try:
        month = date.fromisoformat(period[:10]).month
    except (TypeError, ValueError):
        return 365
    return 90 if month <= 3 else 180 if month <= 6 else 270 if month <= 9 else 365


def _company_derivation(field_name: str) -> str:
    mapping = {
        "gross_margin": "(营业收入-营业成本)/营业收入",
        "rd_ratio": "研发费用/营业收入",
        "research_expense_ratio": "研发费用/营业收入",
        "roe": "归母净利润/归母权益",
        "debt_ratio": "负债合计/资产总计",
        "asset_lightness": "1-固定资产/资产总计",
        "profit_stability": "1-近三年归母净利润总体标准差/平均绝对值",
        "contract_liability_growth": "(本期合同负债-上期合同负债)/上期合同负债",
        "contract_liability_growth_yoy": "财报披露的合同负债同比增速",
        "contract_liability_growth_qoq": "(本期合同负债-上期合同负债)/上期合同负债",
        "operating_cash_flow_to_net_profit": "经营现金流净额/归母净利润",
    }
    return mapping.get(field_name, "财务报表字段或相邻报告期派生")


def _first_number(row: Mapping[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _difference(left: Optional[float], right: Optional[float]) -> Optional[float]:
    return left - right if left is not None and right is not None else None


def _growth_percent(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100.0


def _ratio(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _ratio_percent(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    value = _ratio(numerator, denominator)
    return value * 100.0 if value is not None else None


def _drop_none(values: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _most_common(values: Iterable[str]) -> str:
    counts: Dict[str, int] = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    return max(counts, key=lambda item: (counts[item], item)) if counts else ""


def _clean_code(value: str) -> str:
    return str(value).strip().upper().split(".", 1)[0]
