"""Deterministic meso-methodology evaluation for admitted industry facts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .contract import (
    READINESS_CONFLICTED,
    READINESS_FRAMEWORK_ONLY,
    READINESS_INDUSTRY,
    READINESS_PEER_PROXY,
    READINESS_SYSTEM_B_ONLY,
    AdmissionDecision,
    evaluate_evidence_records,
)


ROLE_NAMES = {
    "barometer": "晴雨表",
    "mid_axis": "中轴确认",
    "ebb_warning": "退潮预警",
    "structural": "结构性生命周期",
    "unmapped": "未映射",
}
SUPPORTED_COMPARISONS = {
    "reported_period_change",
    "same_period_yoy",
    "reported_growth",
    "level_and_trend",
    "reported_change",
    "long_horizon_trend",
}
STATE_LABELS = {
    "structural_lifecycle": {
        "undetermined": "未判定",
        "introduction": "导入期",
        "growth": "成长期",
        "maturity": "成熟期",
        "decline": "衰退期",
    },
    "cyclical_phase": {
        "undetermined": "未判定",
        "recovery": "复苏",
        "expansion": "扩张",
        "overheat": "过热",
        "contraction": "收缩",
    },
    "inflection_state": {
        "undetermined": "未判定",
        "pre": "拐点前",
        "early": "早期",
        "confirmed": "已确认",
        "late": "后期",
        "downtrend_confirmed": "下行确认",
    },
}


def evaluate_meso_methodology(
    packet: Mapping[str, Any],
    admission: AdmissionDecision,
) -> Dict[str, Any]:
    """Evaluate one selected peer-group methodology without inventing facts."""
    profile = dict(packet.get("methodology_profile") or {})
    evidence_decisions = evaluate_evidence_records(
        packet,
        admission,
        reference_date=packet.get("as_of_date"),
    )
    nodes = _build_trace_nodes(packet, admission, profile, evidence_decisions)
    summary = _summarize_nodes(nodes, admission.readiness == READINESS_CONFLICTED)
    profile_admission = _profile_admission(nodes, admission, profile)
    rules = dict(profile.get("state_transition_rules") or {})
    structural_state = _structural_state(nodes, rules.get("structural_lifecycle") or {})
    cyclical_state = _select_profile_state(rules.get("cyclical_phase") or {}, summary)
    inflection_state = _select_profile_state(rules.get("inflection_state") or {}, summary)
    if not profile_admission["usable_for_system_a"]:
        structural_state = cyclical_state = inflection_state = "undetermined"

    effective_readiness = profile_admission["readiness"]
    direction = _direction_from_profile(
        rules.get("signal_direction") or {},
        cyclical_state,
        inflection_state,
        effective_readiness,
    )
    confidence, weight = _confidence_and_weight(effective_readiness, direction)
    structural = _conclusion("structural_lifecycle", structural_state, nodes)
    cyclical = _conclusion("cyclical_phase", cyclical_state, nodes)
    inflection = _conclusion("inflection_state", inflection_state, nodes)
    matched = (
        list(
            dict.fromkeys(
                node["indicator_id"]
                for node in nodes
                if node["admission_status"] == "admitted"
                and node["role"] in {"barometer", "mid_axis", "ebb_warning"}
                and node["cross_period"]
                and node["contribution"] in {"support", "oppose", "warning"}
            )
        )
        if profile_admission["usable_for_system_a"]
        else []
    )
    reasoning = _render_reasoning(
        structural,
        cyclical,
        inflection,
        summary,
        admission,
        profile_admission,
    )
    return {
        "structural_lifecycle": structural,
        "cyclical_phase": cyclical,
        "inflection_state": inflection,
        "direction": direction,
        "confidence": confidence,
        "weight": weight,
        "effective_readiness": effective_readiness,
        "usable_for_system_a": profile_admission["usable_for_system_a"],
        "profile_admission": profile_admission,
        "reasoning": reasoning,
        "signals": [
            f"结构性生命周期: {structural['label']}",
            f"周期景气阶段: {cyclical['label']}",
            f"拐点状态: {inflection['label']}",
        ],
        "matched_signals": matched,
        "reasoning_trace": {
            "schema_version": "industry-reasoning-trace/0.1",
            "profile_id": profile.get("profile_id") or "",
            "profile_version": profile.get("version") or "",
            "reference_series": deepcopy(profile.get("reference_series") or {}),
            "state_transition_rules": deepcopy(rules),
            "nodes": nodes,
            "summary": summary,
            "profile_admission": profile_admission,
            "decision_path": [
                "comparability_gate",
                "barometer",
                "independent_mid_axis",
                "ebb_warning",
                "three_conclusions",
            ],
        },
    }


def evaluate_admitted_trace_subset(
    reasoning_trace: Mapping[str, Any],
    evidence_refs: Iterable[str],
    profile_admission: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recompute System A for one industry unit from admitted trace nodes.

    Unit-level callers may identify the evidence records belonging to a
    product/industry unit, but they may not supply conclusion labels.  This
    helper reuses the selected Methodology Profile's transition rules and
    minimum decision set so arbitrary external labels cannot bypass System A.
    """
    allowed_refs = {str(item) for item in evidence_refs if item}
    nodes = [
        deepcopy(node)
        for node in reasoning_trace.get("nodes") or []
        if isinstance(node, Mapping)
        and node.get("admission_status") == "admitted"
        and str(node.get("evidence_ref") or "") in allowed_refs
    ]
    qualified_nodes = [
        node
        for node in nodes
        if node.get("cross_period")
        and node.get("role") in {"barometer", "mid_axis", "ebb_warning", "structural"}
    ]
    observed_indicators = {str(node.get("indicator_id") or "") for node in qualified_nodes}
    observed_roles = {str(node.get("role") or "") for node in qualified_nodes}
    required_indicators = {
        str(item) for item in profile_admission.get("required_indicator_ids") or []
    }
    required_roles = {str(item) for item in profile_admission.get("required_roles") or []}
    minimum_set_passed = bool(required_indicators or required_roles) and (
        required_indicators.issubset(observed_indicators)
        and required_roles.issubset(observed_roles)
    )
    summary = _summarize_nodes(nodes, conflicted=False)
    rules = dict(reasoning_trace.get("state_transition_rules") or {})
    structural_state = _structural_state(nodes, rules.get("structural_lifecycle") or {})
    cyclical_state = _select_profile_state(rules.get("cyclical_phase") or {}, summary)
    inflection_state = _select_profile_state(rules.get("inflection_state") or {}, summary)
    usable = bool(nodes) and minimum_set_passed and not summary.get("conflicted")
    if not usable:
        structural_state = cyclical_state = inflection_state = "undetermined"
    return {
        "usable_for_system_a": usable,
        "structural_lifecycle": _conclusion("structural_lifecycle", structural_state, nodes),
        "cyclical_phase": _conclusion("cyclical_phase", cyclical_state, nodes),
        "inflection_state": _conclusion("inflection_state", inflection_state, nodes),
        "observed_indicator_ids": sorted(observed_indicators),
        "observed_roles": sorted(observed_roles),
        "missing_indicator_ids": sorted(required_indicators - observed_indicators),
        "missing_roles": sorted(required_roles - observed_roles),
    }


def _build_trace_nodes(
    packet: Mapping[str, Any],
    admission: AdmissionDecision,
    profile: Mapping[str, Any],
    evidence_decisions: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    definitions: Dict[str, Dict[str, Any]] = {}
    state_rules = dict(profile.get("state_transition_rules") or {})
    default_freshness = int(
        dict(profile.get("observation_windows") or {}).get("default_freshness_days") or 180
    )
    for role, indicators in dict(profile.get("indicators") or {}).items():
        for indicator in indicators or []:
            if isinstance(indicator, dict) and indicator.get("field_path"):
                definitions[indicator["field_path"]] = {
                    **indicator,
                    "role": role,
                    "freshness_days": int(indicator.get("freshness_days") or default_freshness),
                }

    raw_paths = {
        **{f"industry_signals.{key}": value for key, value in dict(packet.get("industry_signals") or {}).items()},
        **{f"peer_basket_signals.{key}": value for key, value in dict(packet.get("peer_basket_signals") or {}).items()},
    }
    paths = list(definitions)
    paths.extend(path for path in raw_paths if path not in definitions)
    nodes: List[Dict[str, Any]] = []
    for path in paths:
        definition = definitions.get(path) or {}
        role = definition.get("role") or "unmapped"
        value = raw_paths.get(path)
        matching = [item for item in evidence_decisions if item.get("field_path") == path]
        if not matching:
            status = "missing" if path not in raw_paths else "rejected"
            reason = (
                "采集计划中的指标尚未回填。"
                if status == "missing"
                else _rejection_reason(path, admission.uncertainties)
            )
            nodes.append(
                _trace_node(
                    path, definition, role, value, "unknown", status, False,
                    reason, None, {}, state_rules,
                )
            )
            continue
        for evidence in matching:
            status = str(evidence.get("admission_status") or "rejected")
            comparison_result = _comparison_result(path, definition, evidence, packet)
            direction = comparison_result.get("direction") or "unknown"
            profile_rejection = _profile_evidence_rejection(
                definition,
                evidence,
                packet,
                profile,
            )
            if status == "admitted" and profile_rejection:
                status = "rejected"
            if status == "admitted" and not comparison_result.get("valid"):
                status = "rejected"
                profile_rejection = comparison_result.get("reason") or "comparison 无法执行。"
            cross_period = status == "admitted" and _cross_period_ready(definition, evidence)
            reason = str(evidence.get("rejection_reason") or profile_rejection or "")
            if status == "admitted" and not cross_period and role in {"barometer", "mid_axis", "ebb_warning"}:
                reason = "evidence 未满足 Profile 配置的跨期数量要求，仅作为 context。"
            nodes.append(
                _trace_node(
                    path, definition, role, value, direction, status,
                    cross_period, reason, evidence, comparison_result, state_rules,
                )
            )
    return nodes


def _trace_node(
    path: str,
    definition: Mapping[str, Any],
    role: str,
    value: Any,
    direction: str,
    status: str,
    cross_period: bool,
    rejection_reason: str,
    evidence: Optional[Mapping[str, Any]],
    comparison_result: Mapping[str, Any],
    state_rules: Mapping[str, Any],
) -> Dict[str, Any]:
    contribution = _contribution(role, direction, status, cross_period)
    evidence_ref = evidence.get("evidence_ref") if evidence else None
    return {
        "indicator_id": definition.get("id") or path.split(".", 1)[-1],
        "field_path": path,
        "role": role,
        "role_name": ROLE_NAMES.get(role, role),
        "value": deepcopy(value),
        "comparison": definition.get("comparison") or "",
        "required_periods": int(definition.get("periods") or 1),
        "observation": direction,
        "admission_status": status,
        "cross_period": cross_period,
        "contribution": contribution,
        "supports_state": _profile_supported_states(role, direction, state_rules),
        "comparison_result": dict(comparison_result),
        "evidence_ref": evidence_ref,
        "evidence_refs": [evidence_ref] if evidence_ref else [],
        "source_level": evidence.get("source_level") if evidence else "",
        "source_type": evidence.get("source_type") if evidence else "",
        "source_title": evidence.get("source_title") if evidence else "",
        "source_url": evidence.get("source_url") if evidence else "",
        "as_of_date": evidence.get("as_of_date") if evidence else "",
        "report_period": evidence.get("report_period") if evidence else "",
        "previous_report_period": evidence.get("previous_report_period") if evidence else "",
        "member_stock_code": evidence.get("member_stock_code") if evidence else "",
        "raw_fields": list(evidence.get("raw_fields") or []) if evidence else [],
        "raw_values": dict(evidence.get("raw_values") or {}) if evidence else {},
        "derivation_method": evidence.get("derivation_method") if evidence else "",
        "aggregation_method": evidence.get("aggregation_method") if evidence else "",
        "rejection_reason": rejection_reason,
    }


def _comparison_result(
    path: str,
    definition: Mapping[str, Any],
    evidence: Mapping[str, Any],
    packet: Mapping[str, Any],
) -> Dict[str, Any]:
    field = path.split(".", 1)[-1]
    comparison = str(definition.get("comparison") or "")
    raw_values = dict(evidence.get("raw_values") or {})
    operands = evidence.get("comparison_operands")
    if isinstance(operands, Mapping):
        current = _number(operands.get("current"))
        previous = _number(operands.get("previous"))
    else:
        current = _raw_operand(raw_values, ("current", "latest", "report"), first=True)
        previous = _raw_operand(raw_values, ("previous", "prior", "comparison"), first=False)
    if current is None or previous is None:
        return {
            "valid": False,
            "comparison": comparison,
            "current": current,
            "previous": previous,
            "delta": None,
            "direction": "unknown",
            "reason": "raw_values 缺少可识别的 current/previous 比较操作数。",
        }
    delta = current - previous
    if "inventory" in field and "change" in field:
        member_direction = "deteriorating" if delta > 0 else "improving" if delta < 0 else "neutral"
    else:
        member_direction = "improving" if delta > 0 else "deteriorating" if delta < 0 else "neutral"
    aggregate_direction = (
        dict(packet.get("peer_basket_meta") or {}).get("direction_by_field") or {}
    ).get(field) if path.startswith("peer_basket_signals.") else None
    direction = aggregate_direction or member_direction
    return {
        "valid": comparison in SUPPORTED_COMPARISONS,
        "comparison": comparison,
        "current": current,
        "previous": previous,
        "delta": delta,
        "direction": direction,
        "member_direction": member_direction,
        "aggregate_direction": aggregate_direction,
        "reason": "" if comparison in SUPPORTED_COMPARISONS else f"comparison {comparison} 不受支持。",
    }


def _raw_operand(
    raw_values: Mapping[str, Any],
    tokens: tuple[str, ...],
    first: bool,
) -> Optional[float]:
    for key, raw in raw_values.items():
        if any(token in str(key).lower() for token in tokens):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
    values = list(raw_values.values())
    index = 0 if first else 1
    if len(values) <= index:
        return None
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _cross_period_ready(definition: Mapping[str, Any], evidence: Mapping[str, Any]) -> bool:
    required = int(definition.get("periods") or 1)
    periods = {
        str(value)[:10]
        for value in (
            evidence.get("report_period"),
            evidence.get("previous_report_period"),
            *(evidence.get("report_periods") or []),
        )
        if value
    }
    operands = evidence.get("comparison_operands")
    comparable = (
        _number(operands.get("current")) is not None
        and _number(operands.get("previous")) is not None
        if isinstance(operands, Mapping)
        else bool(evidence.get("raw_values"))
    )
    return len(periods) >= required and comparable


def _profile_evidence_rejection(
    definition: Mapping[str, Any],
    evidence: Mapping[str, Any],
    packet: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> str:
    if not definition:
        return "field_path 未在所选同行组 Methodology Profile 中定义。"
    allowed_levels = {str(level).upper() for level in definition.get("source_levels") or []}
    if str(evidence.get("source_level") or "").upper() not in allowed_levels:
        return "evidence 来源等级不满足 Profile。"
    comparison = str(definition.get("comparison") or "")
    if comparison not in SUPPORTED_COMPARISONS:
        return f"Profile comparison {comparison or 'missing'} 不受支持。"
    reference = _parse_iso_date(packet.get("as_of_date"))
    evidence_date = _parse_iso_date(evidence.get("as_of_date"))
    freshness = int(definition.get("freshness_days") or 0)
    if not reference or not evidence_date or not (-7 <= (reference - evidence_date).days <= freshness):
        return f"evidence 不满足 Profile 的 {freshness} 天 freshness。"
    if str(evidence.get("field_path") or "").startswith("peer_basket_signals."):
        meta = dict(packet.get("peer_basket_meta") or {})
        thresholds = dict(profile.get("thresholds") or {})
        field = str(evidence.get("field_path") or "").split(".", 1)[-1]
        if int(meta.get("sample_size") or 0) < int(thresholds.get("minimum_peer_sample") or 0):
            return "同行样本数低于 Profile 阈值。"
        coverage = dict(meta.get("coverage_ratio_by_field") or {}).get(
            field,
            meta.get("coverage_ratio"),
        )
        if round(float(coverage or 0), 4) < float(thresholds.get("minimum_coverage_ratio") or 0):
            return "同行覆盖率低于 Profile 阈值。"
        agreement = dict(meta.get("agreement_ratio_by_field") or {}).get(field)
        if round(float(agreement or 0), 4) < float(thresholds.get("minimum_agreement_ratio") or 0):
            return "同行方向一致率低于 Profile 阈值。"
    return ""


def _parse_iso_date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _contribution(role: str, direction: str, status: str, cross_period: bool) -> str:
    if status != "admitted" or role == "unmapped":
        return "none"
    if role in {"barometer", "mid_axis", "ebb_warning"} and not cross_period:
        return "context_only"
    if role == "ebb_warning" and direction == "deteriorating":
        return "warning"
    if direction == "improving":
        return "support"
    if direction == "deteriorating":
        return "oppose"
    return "neutral"


def _profile_supported_states(
    role: str,
    direction: str,
    state_rules: Mapping[str, Any],
) -> List[str]:
    supported: List[str] = []
    for conclusion in ("cyclical_phase", "inflection_state"):
        for rule in dict(state_rules.get(conclusion) or {}).get("rules") or []:
            if any(
                condition.get("role") == role and condition.get("direction") == direction
                for condition in rule.get("all") or []
            ):
                supported.append(f"{conclusion}:{rule.get('state')}")
    return list(dict.fromkeys(supported))


def _summarize_nodes(nodes: Iterable[Mapping[str, Any]], conflicted: bool) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        role: {"improving": 0, "deteriorating": 0, "neutral": 0}
        for role in ("barometer", "mid_axis", "ebb_warning", "structural")
    }
    counted = set()
    for node in nodes:
        role = node.get("role")
        direction = node.get("observation")
        if role not in summary or direction not in summary[role]:
            continue
        if node.get("admission_status") != "admitted":
            continue
        if role in {"barometer", "mid_axis", "ebb_warning"} and not node.get("cross_period"):
            continue
        vote = (role, node.get("indicator_id"), direction)
        if vote in counted:
            continue
        counted.add(vote)
        summary[role][direction] += 1
    role_conflicts = [
        role
        for role in ("barometer", "mid_axis", "ebb_warning")
        if summary[role]["improving"] and summary[role]["deteriorating"]
    ]
    summary["role_conflicts"] = role_conflicts
    summary["conflicted"] = conflicted or bool(role_conflicts)
    return summary


def _profile_admission(
    nodes: Iterable[Mapping[str, Any]],
    admission: AdmissionDecision,
    profile: Mapping[str, Any],
) -> Dict[str, Any]:
    if admission.readiness == READINESS_CONFLICTED:
        return {
            "readiness": READINESS_CONFLICTED,
            "usable_for_system_a": False,
            "analysis_basis": "industry_vs_peer_conflict",
            "passed": False,
            "reasons": ["直接行业证据与同行代理冲突。"],
        }
    qualified_nodes = [
        node
        for node in nodes
        if node.get("admission_status") == "admitted"
        and node.get("role") in {"barometer", "mid_axis", "ebb_warning", "structural"}
        and node.get("cross_period")
    ]
    observed_indicators = sorted({str(node.get("indicator_id")) for node in qualified_nodes})
    observed_roles = sorted({str(node.get("role")) for node in qualified_nodes})
    configured = dict(profile.get("minimum_decision_sets") or {}).get(admission.readiness) or {}
    required_indicators = [str(item) for item in configured.get("required_indicator_ids") or []]
    required_roles = [str(item) for item in configured.get("required_roles") or []]
    missing_indicators = sorted(set(required_indicators) - set(observed_indicators))
    missing_roles = sorted(set(required_roles) - set(observed_roles))
    minimum_set_passed = bool(configured) and not missing_indicators and not missing_roles
    diagnostics = {
        "required_indicator_ids": required_indicators,
        "required_roles": required_roles,
        "observed_indicator_ids": observed_indicators,
        "observed_roles": observed_roles,
        "missing_indicator_ids": missing_indicators,
        "missing_roles": missing_roles,
    }
    if admission.usable_for_system_a and qualified_nodes and minimum_set_passed:
        return {
            "readiness": admission.readiness,
            "usable_for_system_a": True,
            "analysis_basis": admission.analysis_basis,
            "passed": True,
            "reasons": [],
            **diagnostics,
        }
    if admission.readiness in {READINESS_PEER_PROXY, READINESS_INDUSTRY}:
        reasons = list(
            dict.fromkeys(
                str(node.get("rejection_reason"))
                for node in nodes
                if node.get("admission_status") == "rejected"
                and node.get("role") != "unmapped"
                and node.get("rejection_reason")
            )
        )
        fallback = READINESS_SYSTEM_B_ONLY if admission.system_b_ready else READINESS_FRAMEWORK_ONLY
        reasons.extend(f"最小决策集缺少指标 {item}。" for item in missing_indicators)
        reasons.extend(f"最小决策集缺少角色 {item}。" for item in missing_roles)
        if not configured:
            reasons.append(f"Profile 未配置 {admission.readiness} 的 minimum_decision_sets。")
        return {
            "readiness": fallback,
            "usable_for_system_a": False,
            "analysis_basis": "methodology_profile_rejected",
            "passed": False,
            "reasons": list(dict.fromkeys(reasons)) or ["没有 evidence 通过所选同行组 Methodology Profile。"],
            **diagnostics,
        }
    return {
        "readiness": admission.readiness,
        "usable_for_system_a": False,
        "analysis_basis": admission.analysis_basis,
        "passed": False,
        "reasons": [],
    }


def _structural_state(nodes: Iterable[Mapping[str, Any]], rules: Mapping[str, Any]) -> str:
    indicator_id = rules.get("indicator_id")
    bands = list(rules.get("bands") or [])
    for node in nodes:
        if (
            node.get("role") != "structural"
            or node.get("admission_status") != "admitted"
            or not node.get("cross_period")
            or node.get("indicator_id") != indicator_id
        ):
            continue
        value = node.get("value")
        if not isinstance(value, (int, float)):
            continue
        for band in bands:
            minimum = band.get("min_inclusive")
            maximum = band.get("max_exclusive")
            if minimum is not None and value < float(minimum):
                continue
            if maximum is not None and value >= float(maximum):
                continue
            return str(band.get("state") or "undetermined")
    return str(rules.get("fallback") or "undetermined")


def _select_profile_state(rules: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    if summary.get("conflicted"):
        return "undetermined"
    for rule in rules.get("rules") or []:
        conditions = rule.get("all") or []
        if conditions and all(_role_condition_matches(condition, summary) for condition in conditions):
            return str(rule.get("state") or "undetermined")
    return str(rules.get("fallback") or "undetermined")


def _role_condition_matches(condition: Mapping[str, Any], summary: Mapping[str, Any]) -> bool:
    role = str(condition.get("role") or "")
    direction = str(condition.get("direction") or "")
    minimum = int(condition.get("min_count") or 1)
    return int((summary.get(role) or {}).get(direction) or 0) >= minimum


def _direction_from_profile(
    rules: Mapping[str, Any],
    cyclical: str,
    inflection: str,
    readiness: str,
) -> str:
    if readiness in {READINESS_FRAMEWORK_ONLY, READINESS_SYSTEM_B_ONLY, READINESS_CONFLICTED}:
        return "neutral"
    conclusions = {"cyclical_phase": cyclical, "inflection_state": inflection}
    for rule in rules.get("rules") or []:
        conditions = rule.get("all") or []
        if conditions and all(
            conclusions.get(condition.get("conclusion")) in set(condition.get("states") or [])
            for condition in conditions
        ):
            return str(rule.get("direction") or "neutral")
    return str(rules.get("fallback") or "neutral")


def _confidence_and_weight(readiness: str, direction: str) -> tuple[float, float]:
    if readiness == READINESS_FRAMEWORK_ONLY:
        return 0.2, 0.0
    if readiness == READINESS_SYSTEM_B_ONLY:
        return 0.25, 0.0
    if readiness == READINESS_CONFLICTED:
        return 0.4, 0.0
    if readiness == READINESS_PEER_PROXY:
        return (0.6, 0.45) if direction != "neutral" else (0.4, 0.0)
    if readiness == READINESS_INDUSTRY:
        return (0.75, 0.65) if direction != "neutral" else (0.5, 0.0)
    return 0.2, 0.0


def _conclusion(kind: str, state: str, nodes: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    relevant_roles = {
        "structural_lifecycle": {"structural"},
        "cyclical_phase": {"barometer", "mid_axis", "ebb_warning"},
        "inflection_state": {"barometer", "mid_axis", "ebb_warning"},
    }[kind]
    refs = (
        [
            ref
            for node in nodes
            if node.get("role") in relevant_roles and node.get("admission_status") == "admitted"
            for ref in node.get("evidence_refs") or []
        ]
        if state != "undetermined"
        else []
    )
    return {
        "state": state,
        "label": STATE_LABELS[kind][state],
        "evidence_refs": list(dict.fromkeys(refs)),
        "determined": state != "undetermined",
    }


def _rejection_reason(path: str, uncertainties: Iterable[str]) -> str:
    for uncertainty in uncertainties:
        if path in uncertainty:
            return uncertainty
    return "数据未通过 System A 准入；请检查 evidence、报告期、样本和时效。"


def _render_reasoning(
    structural: Mapping[str, Any],
    cyclical: Mapping[str, Any],
    inflection: Mapping[str, Any],
    summary: Mapping[str, Any],
    admission: AdmissionDecision,
    profile_admission: Mapping[str, Any],
) -> str:
    if admission.readiness == READINESS_CONFLICTED:
        return "直接行业证据与同行代理冲突，三类行业结论均保持未判定。"
    if (
        admission.readiness in {READINESS_PEER_PROXY, READINESS_INDUSTRY}
        and not profile_admission.get("usable_for_system_a")
    ):
        reasons = "；".join(
            str(reason).rstrip("。；")
            for reason in profile_admission.get("reasons") or []
        )
        detail = f"{reasons}；" if reasons else ""
        return f"数据通过基础准入，但未通过所选同行组 Profile：{detail}三类行业结论均保持未判定。"
    if summary.get("role_conflicts") and not profile_admission.get("usable_for_system_a"):
        roles = "、".join(ROLE_NAMES.get(role, role) for role in summary["role_conflicts"])
        return f"同行证据有单项通过，但在{roles}内部方向冲突，未形成 System A 最小共识，三类结论保持未判定。"
    if summary.get("role_conflicts"):
        roles = "、".join(ROLE_NAMES.get(role, role) for role in summary["role_conflicts"])
        return f"合格同行证据在{roles}内部方向冲突，周期与拐点保持未判定。"
    return (
        f"周期景气阶段为{cyclical['label']}，拐点状态为{inflection['label']}，"
        f"结构性生命周期为{structural['label']}。"
        f"晴雨表改善{summary['barometer']['improving']}项，"
        f"中轴改善{summary['mid_axis']['improving']}项，"
        f"退潮预警{summary['ebb_warning']['deteriorating']}项。"
    )
