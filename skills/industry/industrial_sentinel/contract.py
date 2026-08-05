"""Industrial Sentinel v0.2 data packet and admission rules.

The data packet is the only external seam consumed by the analysis runtime.
Provider payloads and offline fixtures are normalized to this shape before
System A or System B sees them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import ceil
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple


PACKET_SCHEMA_VERSION = "industry-data/0.2"
MIN_PEER_SAMPLE_SIZE = 3
MIN_COVERAGE_RATIO = 2 / 3
MIN_AGREEMENT_RATIO = 2 / 3
DIRECT_SIGNAL_FRESHNESS_DAYS = 90
PEER_SIGNAL_FRESHNESS_DAYS = 180

READINESS_FRAMEWORK_ONLY = "framework_only"
READINESS_SYSTEM_B_ONLY = "system_b_only"
READINESS_PEER_PROXY = "peer_proxy_ready"
READINESS_INDUSTRY = "industry_ready"
READINESS_CONFLICTED = "conflicted"


DIRECT_DIMENSIONS: Dict[str, Set[str]] = {
    "demand": {
        "industry_market_growth",
        "industry_revenue_growth",
        "industry_demand_growth",
        "industry_end_demand_growth",
    },
    "order": {"industry_order_growth", "industry_order_backlog"},
    "supply": {
        "industry_capacity_utilization",
        "industry_capacity_util",
        "industry_capex_plan",
        "industry_capacity_expansion",
    },
    "price_margin": {"industry_price_yoy", "industry_price_trend"},
    "inventory": {"industry_inventory_days", "industry_inventory_change"},
    "policy": {"industry_policy_count", "industry_policy_score"},
    "lifecycle": {
        "industry_penetration_rate",
        "industry_5g_shipment_share",
        "industry_competition_score",
        "lifecycle_signals",
    },
    "qualitative": {"inflection_signals", "qualitative_signals"},
}

PEER_DIMENSIONS: Dict[str, Set[str]] = {
    "demand": {"revenue_growth_median", "peer_revenue_growth_median"},
    "order": {
        "contract_liability_growth_median",
        "contract_liability_growth_yoy_median",
        "contract_liability_growth_qoq_median",
    },
    "inventory": {
        "inventory_days_change_median",
        "inventory_days_median",
        "peer_inventory_days_median",
    },
    "supply": {
        "capex_growth_median",
        "construction_in_progress_growth_median",
        "capex_trend",
    },
    "price_margin": {
        "gross_margin_change_median",
        "gross_margin_median",
        "peer_gross_margin_median",
    },
    "cash_realization": {"operating_cash_flow_to_net_profit_median"},
}

LEADING_PEER_FIELDS = {
    "contract_liability_growth_median",
    "contract_liability_growth_yoy_median",
    "contract_liability_growth_qoq_median",
    "inventory_days_change_median",
    "capex_growth_median",
    "construction_in_progress_growth_median",
}
STATIC_PEER_LEVEL_FIELDS = {
    "gross_margin_median",
    "peer_gross_margin_median",
    "inventory_days_median",
    "peer_inventory_days_median",
}


@dataclass
class AdmissionDecision:
    readiness: str
    analysis_basis: str
    usable_for_system_a: bool
    system_b_ready: bool
    admissible_industry_signals: Dict[str, Any] = field(default_factory=dict)
    admissible_peer_signals: Dict[str, Any] = field(default_factory=dict)
    industry_dimensions: List[str] = field(default_factory=list)
    peer_dimensions: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    needs_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "readiness": self.readiness,
            "analysis_basis": self.analysis_basis,
            "usable_for_system_a": self.usable_for_system_a,
            "system_b_ready": self.system_b_ready,
            "admissible_industry_signals": self.admissible_industry_signals,
            "admissible_peer_signals": self.admissible_peer_signals,
            "industry_dimensions": self.industry_dimensions,
            "peer_dimensions": self.peer_dimensions,
            "uncertainties": self.uncertainties,
            "needs_human_review": self.needs_human_review,
        }


def normalize_industry_packet(
    target: str,
    packet: Optional[Mapping[str, Any]],
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a defensive, stable v0.2 packet without inventing data."""
    source = dict(packet or {})
    context = dict(context or {})
    target_block = dict(source.get("target") or {})

    target_block.setdefault("stock_code", source.get("stock_code") or target)
    target_block.setdefault("stock_name", source.get("stock_name") or context.get("stock_name") or target)
    target_block.setdefault("industry", source.get("industry") or source.get("industry_name") or "")
    target_block.setdefault("sub_sector", source.get("sub_sector") or "")
    target_block.setdefault("preset", source.get("preset") or context.get("preset") or "generic")
    target_block.setdefault("input_type", context.get("input_type") or source.get("input_type") or "stock_code")

    normalized = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "target": target_block,
        "industry_signals": _dict_or_empty(source.get("industry_signals")),
        "peer_basket_signals": _dict_or_empty(source.get("peer_basket_signals")),
        "peer_basket_meta": _dict_or_empty(source.get("peer_basket_meta")),
        "company_signals": _dict_or_empty(source.get("company_signals")),
        "product_industry_map": _list_of_dicts(source.get("product_industry_map")),
        "valuation_context": _dict_or_empty(source.get("valuation_context")),
        "market_context": _dict_or_empty(source.get("market_context")),
        "evidence": _list_of_dicts(source.get("evidence")),
        "needs_data": _normalize_needs_data(source.get("needs_data")),
        "as_of_date": source.get("as_of_date") or "",
        "data_quality": source.get("data_quality") or "",
        "provider_status": _dict_or_empty(source.get("provider_status")),
        "source_mode": source.get("source_mode") or context.get("source_mode") or "project",
        "fetched_at": source.get("fetched_at") or "",
        "data_hash": source.get("data_hash") or "",
        "profile_version": source.get("profile_version") or "",
        "profile_id": source.get("profile_id") or "",
        "cache_origin": _dict_or_empty(source.get("cache_origin")),
        "scope_provenance": _dict_or_empty(source.get("scope_provenance")),
        "route_evidence": _list_of_dicts(source.get("route_evidence")),
        "route_evidence_rejections": [
            str(item) for item in source.get("route_evidence_rejections") or []
        ],
    }
    for optional_block in ("routing", "methodology_profile", "collection_plan"):
        if optional_block in source:
            normalized[optional_block] = _dict_or_empty(source.get(optional_block))
    if source.get("status") == "preset_only" or source.get("_preset_only"):
        normalized["framework_only"] = True
    return normalized


def evaluate_packet_admission(
    packet: Mapping[str, Any],
    reference_date: Optional[Any] = None,
) -> AdmissionDecision:
    """Decide which data may cross the System A seam."""
    normalized = normalize_industry_packet(
        str((packet.get("target") or {}).get("stock_code") or packet.get("stock_code") or ""),
        packet,
    )
    reference = _parse_date(reference_date) or _parse_date(normalized.get("as_of_date")) or date.today()
    evidence = normalized["evidence"]
    uncertainties: List[str] = []

    direct, direct_dimensions = _admit_direct_signals(
        normalized["industry_signals"], evidence, reference, uncertainties
    )
    peer, peer_dimensions, peer_direction = _admit_peer_signals(
        normalized, evidence, reference, uncertainties
    )
    direct_direction = _consensus_direction(direct, "industry")

    direct_ready = len(direct) >= 3 and len(direct_dimensions) >= 2
    peer_ready = _peer_proxy_ready(normalized, peer, peer_dimensions, peer_direction)
    system_b_ready = is_system_b_ready(normalized["company_signals"])

    conflict = (
        direct_ready
        and peer_ready
        and direct_direction in {"improving", "deteriorating"}
        and peer_direction in {"improving", "deteriorating"}
        and direct_direction != peer_direction
    )

    if conflict:
        uncertainties.append("直接行业证据与同业代理方向冲突，禁止形成方向性行业结论。")
        return AdmissionDecision(
            readiness=READINESS_CONFLICTED,
            analysis_basis="industry_vs_peer_conflict",
            usable_for_system_a=False,
            system_b_ready=system_b_ready,
            admissible_industry_signals=direct,
            admissible_peer_signals=peer,
            industry_dimensions=sorted(direct_dimensions),
            peer_dimensions=sorted(peer_dimensions),
            uncertainties=_dedupe(uncertainties),
            needs_human_review=True,
        )

    if direct_ready:
        readiness = READINESS_INDUSTRY
        basis = "direct_industry_evidence"
        usable = True
    elif peer_ready:
        readiness = READINESS_PEER_PROXY
        basis = "controlled_peer_proxy"
        usable = True
    elif system_b_ready:
        readiness = READINESS_SYSTEM_B_ONLY
        basis = "company_financials_only"
        usable = False
        uncertainties.append("只有公司级财务数据，System A 行业判断不可用。")
    else:
        readiness = READINESS_FRAMEWORK_ONLY
        basis = "preset_framework_only"
        usable = False
        uncertainties.append("缺少通过准入的行业证据或同业代理，只能输出产业链框架。")

    return AdmissionDecision(
        readiness=readiness,
        analysis_basis=basis,
        usable_for_system_a=usable,
        system_b_ready=system_b_ready,
        admissible_industry_signals=direct,
        admissible_peer_signals=peer,
        industry_dimensions=sorted(direct_dimensions),
        peer_dimensions=sorted(peer_dimensions),
        uncertainties=_dedupe(uncertainties),
        needs_human_review=bool(normalized["needs_data"]),
    )


def is_system_b_ready(company_signals: Mapping[str, Any]) -> bool:
    """System B requires its real inputs; defaults must not manufacture a type."""
    company = dict(company_signals or {})
    revenue = _meaningful(company.get("revenue_growth"))
    rd_ratio = _meaningful(company.get("rd_ratio") or company.get("research_expense_ratio"))
    asset_lightness = _meaningful(company.get("asset_lightness")) or (
        _meaningful(company.get("fixed_asset")) and _meaningful(company.get("total_asset"))
    )
    profit_stability = _meaningful(company.get("profit_stability"))
    return bool(revenue and rd_ratio and asset_lightness and profit_stability)


def evaluate_evidence_records(
    packet: Mapping[str, Any],
    admission: AdmissionDecision,
    reference_date: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Classify every evidence record at the same public admission boundary."""
    normalized = normalize_industry_packet(
        str((packet.get("target") or {}).get("stock_code") or ""),
        packet,
    )
    reference = _parse_date(reference_date) or _parse_date(normalized.get("as_of_date")) or date.today()
    peer_meta = dict(normalized.get("peer_basket_meta") or {})
    report_period = str(peer_meta.get("report_period") or "")[:10]
    previous_report_period = str(peer_meta.get("previous_report_period") or "")[:10]
    previous_period_by_field = {
        str(key): str(value or "")[:10]
        for key, value in dict(peer_meta.get("previous_report_period_by_field") or {}).items()
    }
    aggregation_method = str(peer_meta.get("aggregation_method") or "")
    decisions: List[Dict[str, Any]] = []
    for index, item in enumerate(normalized.get("evidence") or []):
        evidence = dict(item)
        path = str(evidence.get("field_path") or "")
        reasons: List[str] = []
        if path.startswith("industry_signals."):
            if str(evidence.get("scope") or "") != "industry":
                reasons.append("直接行业 evidence scope 不是 industry")
            if not _valid_source_level(evidence, allow_l2_l3=True):
                reasons.append("直接行业 evidence 来源等级无效")
            if not _fresh(evidence, reference, DIRECT_SIGNAL_FRESHNESS_DAYS):
                reasons.append("直接行业 evidence 缺少有效日期或超过90天")
        elif path.startswith("peer_basket_signals."):
            if str(evidence.get("scope") or "") != "peer_basket":
                reasons.append("同行 evidence scope 不是 peer_basket")
            if not _valid_source_level(evidence, allow_l2_l3=False):
                reasons.append("同行 evidence 必须为 L1")
            if not _fresh(evidence, reference, PEER_SIGNAL_FRESHNESS_DAYS):
                reasons.append("同行 evidence 缺少有效日期或超过180天")
            if str(evidence.get("report_period") or "")[:10] != report_period:
                reasons.append("同行 evidence 当前报告期不一致")
            expected_previous = previous_period_by_field.get(
                path.rsplit(".", 1)[-1],
                previous_report_period,
            )
            if str(evidence.get("previous_report_period") or "")[:10] != expected_previous:
                reasons.append("同行 evidence 前一报告期不一致")
            if not evidence.get("raw_fields") or not evidence.get("raw_values"):
                reasons.append("同行 evidence 缺少原始字段或原始值")
            if not evidence.get("derivation_method"):
                reasons.append("同行 evidence 缺少派生方法")
            if str(evidence.get("aggregation_method") or "") != aggregation_method:
                reasons.append("同行 evidence 聚合方法不一致")
        else:
            reasons.append("evidence field_path 不属于行业或同行信号")

        if not reasons and not _path_is_admitted(path, admission):
            reasons.append(_field_rejection_reason(path, admission.uncertainties))
        decisions.append(
            {
                "evidence_ref": evidence.get("evidence_id") or f"evidence:{index + 1}",
                "evidence_index": index,
                "field_path": path,
                "admission_status": "admitted" if not reasons else "rejected",
                "rejection_reason": "；".join(_dedupe(reasons)),
                "source_level": evidence.get("source_level") or "",
                "source_type": evidence.get("source_type") or "",
                "source_title": evidence.get("source_title") or "",
                "source_url": evidence.get("source_url") or evidence.get("url") or "",
                "as_of_date": evidence.get("as_of_date") or evidence.get("source_date") or "",
                "report_period": evidence.get("report_period") or "",
                "previous_report_period": evidence.get("previous_report_period") or "",
                "report_periods": list(evidence.get("report_periods") or []),
                "member_stock_code": evidence.get("member_stock_code") or evidence.get("stock_code") or "",
                "raw_fields": list(evidence.get("raw_fields") or []),
                "raw_values": dict(evidence.get("raw_values") or {}),
                "comparison": evidence.get("comparison") or "",
                "comparison_operands": (
                    dict(evidence.get("comparison_operands") or {})
                    if "comparison_operands" in evidence
                    else None
                ),
                "member_direction": evidence.get("member_direction") or "",
                "derivation_method": evidence.get("derivation_method") or "",
                "aggregation_method": evidence.get("aggregation_method") or "",
            }
        )
    return decisions


def _path_is_admitted(path: str, admission: AdmissionDecision) -> bool:
    root, _, field = path.partition(".")
    if root == "industry_signals":
        return field in admission.admissible_industry_signals
    if root == "peer_basket_signals":
        return field in admission.admissible_peer_signals
    return False


def _field_rejection_reason(path: str, uncertainties: Iterable[str]) -> str:
    values = list(uncertainties)
    for uncertainty in values:
        if path in uncertainty:
            return uncertainty
    structural_markers = (
        "混合报告期",
        "样本少于",
        "包含目标公司",
        "覆盖率低于",
        "缺少当前或前一报告期",
        "聚合方法",
    )
    structural = [
        uncertainty
        for uncertainty in values
        if any(marker in uncertainty for marker in structural_markers)
    ]
    if structural:
        return "；".join(_dedupe(structural))
    return "字段级样本、覆盖率、一致率或结构校验未通过"


def _admit_direct_signals(
    signals: Mapping[str, Any],
    evidence: List[Dict[str, Any]],
    reference: date,
    uncertainties: List[str],
) -> Tuple[Dict[str, Any], Set[str]]:
    admitted: Dict[str, Any] = {}
    dimensions: Set[str] = set()
    for key, value in dict(signals or {}).items():
        dimension = _dimension_for(key, DIRECT_DIMENSIONS)
        if not dimension or not _meaningful(value):
            continue
        path = f"industry_signals.{key}"
        matching = [item for item in evidence if item.get("field_path") == path]
        valid = [
            item for item in matching
            if str(item.get("scope") or "") == "industry"
            and _valid_source_level(item, allow_l2_l3=True)
            and _fresh(item, reference, DIRECT_SIGNAL_FRESHNESS_DAYS)
        ]
        if not valid:
            uncertainties.append(f"{path} 缺少有效且在90天内的行业证据，未进入 System A。")
            continue
        admitted[key] = value
        dimensions.add(dimension)
    return admitted, dimensions


def _admit_peer_signals(
    packet: Mapping[str, Any],
    evidence: List[Dict[str, Any]],
    reference: date,
    uncertainties: List[str],
) -> Tuple[Dict[str, Any], Set[str], str]:
    signals = dict(packet.get("peer_basket_signals") or {})
    meta = dict(packet.get("peer_basket_meta") or {})
    members = _member_codes(meta.get("members"))
    declared_size = _safe_int(meta.get("sample_size"))
    sample_size = declared_size if declared_size is not None else len(members)
    target_code = _clean_code(str((packet.get("target") or {}).get("stock_code") or ""))
    coverage = _safe_float(meta.get("coverage_ratio"))
    coverage_by_field = dict(meta.get("coverage_ratio_by_field") or {})
    agreement = dict(meta.get("agreement_ratio_by_field") or {})
    aggregation_method = str(meta.get("aggregation_method") or "")
    report_period = str(meta.get("report_period") or "")[:10]
    previous_report_period = str(meta.get("previous_report_period") or "")[:10]
    previous_period_by_field = {
        str(key): str(value or "")[:10]
        for key, value in dict(meta.get("previous_report_period_by_field") or {}).items()
    }
    peer_evidence = [
        item for item in evidence
        if str(item.get("scope") or "") == "peer_basket"
    ]
    if not signals and not meta and not peer_evidence:
        return {}, set(), "unknown"

    structural_errors = []
    if sample_size < MIN_PEER_SAMPLE_SIZE or len(members) < MIN_PEER_SAMPLE_SIZE:
        structural_errors.append("同业样本少于3家")
    if target_code and target_code in members:
        structural_errors.append("同业样本包含目标公司")
    if not report_period or not previous_report_period:
        structural_errors.append("同业代理缺少当前或前一报告期")
    elif report_period == previous_report_period:
        structural_errors.append("同业代理当前与前一报告期相同")
    if coverage is None and not coverage_by_field:
        structural_errors.append("同业代理缺少字段覆盖率")
    if not aggregation_method:
        structural_errors.append("同业代理缺少聚合方法")
    if peer_evidence and any(
        str(item.get("report_period") or "")[:10] != report_period
        or str(item.get("previous_report_period") or "")[:10]
        != previous_period_by_field.get(
            str(item.get("field_path") or "").rsplit(".", 1)[-1],
            previous_report_period,
        )
        for item in peer_evidence
    ):
        structural_errors.append("同业证据存在混合报告期")
    if structural_errors:
        uncertainties.extend(f"{message}，同业代理未准入。" for message in structural_errors)
        return {}, set(), "unknown"

    admitted: Dict[str, Any] = {}
    dimensions: Set[str] = set()
    directions_by_dimension: Dict[str, List[str]] = {}
    required_member_evidence = max(MIN_PEER_SAMPLE_SIZE, ceil(sample_size * MIN_COVERAGE_RATIO))
    explicit_directions = dict(meta.get("direction_by_field") or {})

    for key, value in signals.items():
        dimension = _dimension_for(key, PEER_DIMENSIONS)
        if not dimension or not _meaningful(value):
            continue
        field_coverage = _safe_float(coverage_by_field.get(key))
        if field_coverage is None:
            field_coverage = coverage
        if field_coverage is None or field_coverage < MIN_COVERAGE_RATIO:
            uncertainties.append(f"peer_basket_signals.{key} 字段覆盖率低于2/3。")
            continue
        ratio = _safe_float(agreement.get(key))
        if ratio is None or ratio < MIN_AGREEMENT_RATIO:
            uncertainties.append(f"peer_basket_signals.{key} 方向一致率低于2/3。")
            continue
        path = f"peer_basket_signals.{key}"
        expected_previous_period = previous_period_by_field.get(key, previous_report_period)
        matching = [
            item for item in evidence
            if item.get("field_path") == path
            and str(item.get("scope") or "") == "peer_basket"
            and _valid_source_level(item, allow_l2_l3=False)
            and _fresh(item, reference, PEER_SIGNAL_FRESHNESS_DAYS)
            and str(item.get("report_period") or "")[:10] == report_period
            and str(item.get("previous_report_period") or "")[:10] == expected_previous_period
            and bool(item.get("raw_fields"))
            and bool(item.get("raw_values"))
            and bool(item.get("derivation_method"))
            and str(item.get("aggregation_method") or "") == aggregation_method
        ]
        evidence_members = {
            _clean_code(str(item.get("member_stock_code") or item.get("stock_code") or ""))
            for item in matching
            if item.get("member_stock_code") or item.get("stock_code")
        }
        if len(evidence_members) < required_member_evidence:
            uncertainties.append(
                f"{path} 只有{len(evidence_members)}家公司L1证据，"
                f"至少需要{required_member_evidence}家。"
            )
            continue
        if key in STATIC_PEER_LEVEL_FIELDS:
            admitted[key] = value
            continue
        direction = str(explicit_directions.get(key) or _direction_for_peer_value(key, value))
        if direction not in {"improving", "deteriorating"}:
            uncertainties.append(f"{path} 缺少可验证的跨期方向。")
            continue
        admitted[key] = value
        dimensions.add(dimension)
        if not _is_compat_peer_alias(key, signals):
            directions_by_dimension.setdefault(dimension, []).append(direction)

    dimension_votes = [
        _single_dimension_direction(values)
        for values in directions_by_dimension.values()
    ]
    return admitted, dimensions, _majority_direction(dimension_votes)


def _peer_proxy_ready(
    packet: Mapping[str, Any],
    admitted: Mapping[str, Any],
    dimensions: Set[str],
    consensus: str,
) -> bool:
    if len(admitted) < 2 or len(dimensions) < 2:
        return False
    if not LEADING_PEER_FIELDS.intersection(admitted):
        return False
    if consensus not in {"improving", "deteriorating"}:
        return False
    direction_by_field = dict((packet.get("peer_basket_meta") or {}).get("direction_by_field") or {})
    directions_by_dimension: Dict[str, List[str]] = {}
    for key, value in admitted.items():
        if key in STATIC_PEER_LEVEL_FIELDS:
            continue
        dimension = _dimension_for(key, PEER_DIMENSIONS)
        direction = direction_by_field.get(key) or _direction_for_peer_value(key, value)
        if (
            dimension
            and direction in {"improving", "deteriorating"}
            and not _is_compat_peer_alias(key, admitted)
        ):
            directions_by_dimension.setdefault(dimension, []).append(direction)
    agreeing = sum(
        1
        for values in directions_by_dimension.values()
        if _single_dimension_direction(values) == consensus
    )
    return agreeing >= 2


def _consensus_direction(signals: Mapping[str, Any], scope: str) -> str:
    directions: List[str] = []
    for key, value in signals.items():
        if isinstance(value, (list, dict)):
            continue
        direction = _direction_for_direct_value(key, value) if scope == "industry" else _direction_for_peer_value(key, value)
        if direction in {"improving", "deteriorating"}:
            directions.append(direction)
    return _majority_direction(directions)


def _majority_direction(directions: Iterable[str]) -> str:
    values = [item for item in directions if item in {"improving", "deteriorating"}]
    improving = values.count("improving")
    deteriorating = values.count("deteriorating")
    if improving >= 2 and improving > deteriorating:
        return "improving"
    if deteriorating >= 2 and deteriorating > improving:
        return "deteriorating"
    return "mixed" if values else "unknown"


def _single_dimension_direction(directions: Iterable[str]) -> str:
    values = [item for item in directions if item in {"improving", "deteriorating"}]
    improving = values.count("improving")
    deteriorating = values.count("deteriorating")
    if improving > deteriorating:
        return "improving"
    if deteriorating > improving:
        return "deteriorating"
    return "mixed" if values else "unknown"


def _is_compat_peer_alias(key: str, signals: Mapping[str, Any]) -> bool:
    return key == "contract_liability_growth_median" and any(
        explicit in signals
        for explicit in (
            "contract_liability_growth_yoy_median",
            "contract_liability_growth_qoq_median",
        )
    )


def _direction_for_direct_value(key: str, value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        text = str(value).lower()
        if any(word in text for word in ("改善", "上升", "增长", "紧张", "回暖", "进行中")):
            return "improving"
        if any(word in text for word in ("恶化", "下降", "收缩", "过剩", "下滑")):
            return "deteriorating"
        return "unknown"
    if "inventory" in key:
        return "improving" if number < 0 else "deteriorating" if number > 0 else "unknown"
    return "improving" if number > 0 else "deteriorating" if number < 0 else "unknown"


def _direction_for_peer_value(key: str, value: Any) -> str:
    if key in STATIC_PEER_LEVEL_FIELDS:
        return "unknown"
    return _direction_for_direct_value(key, value)


def _dimension_for(key: str, mapping: Mapping[str, Set[str]]) -> Optional[str]:
    for dimension, keys in mapping.items():
        if key in keys:
            return dimension
    return None


def _valid_source_level(item: Mapping[str, Any], allow_l2_l3: bool) -> bool:
    level = str(item.get("source_level") or "").upper()
    allowed = {"L1", "L2", "L3"} if allow_l2_l3 else {"L1"}
    return level in allowed


def _fresh(item: Mapping[str, Any], reference: date, max_age_days: int) -> bool:
    value = (
        item.get("as_of_date")
        or item.get("source_date")
        or item.get("date")
        or item.get("published_at")
    )
    parsed = _parse_date(value)
    if parsed is None:
        return False
    age = (reference - parsed).days
    return -7 <= age <= max_age_days


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _member_codes(value: Any) -> Set[str]:
    result: Set[str] = set()
    for item in value if isinstance(value, list) else []:
        code = item.get("stock_code") if isinstance(item, dict) else item
        if code:
            result.add(_clean_code(str(code)))
    return result


def _clean_code(value: str) -> str:
    return value.strip().upper().split(".", 1)[0]


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _meaningful(value: Any) -> bool:
    return value not in (None, "", [], {}, "数据缺失", "待补充")


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    return [dict(item) for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _normalize_needs_data(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if not isinstance(value, list):
        return [{"field_path": str(value), "reason": "upstream_needs_data"}] if value else []
    result = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(dict(item))
        elif item:
            result.append({"field_path": str(item), "reason": "upstream_needs_data"})
    return result


def _dedupe(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
