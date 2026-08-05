"""Profile-driven routing and collection planning for Industrial Sentinel.

This module plans facts to collect. It never fetches data and never produces an
industry direction, readiness, confidence or lifecycle conclusion.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


COLLECTION_PLAN_SCHEMA_VERSION = "industry-collection-plan/0.1"
SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = SKILL_DIR / "data"
PRESET_DIR = SKILL_DIR / "references" / "preset-chains"
CONCLUSION_FIELDS = {
    "direction", "confidence", "weight", "readiness",
    "structural_lifecycle", "cyclical_phase", "inflection_state",
}
PROFILE_ROLES = ("barometer", "mid_axis", "ebb_warning", "structural")
SOURCE_LEVELS = {"L1", "L2", "L3"}
SUPPORTED_COMPARISONS = {
    "reported_period_change", "same_period_yoy", "reported_growth",
    "level_and_trend", "reported_change", "long_horizon_trend",
}
CONCLUSION_STATES = {
    "cyclical_phase": {"recovery", "expansion", "overheat", "contraction"},
    "inflection_state": {"pre", "early", "confirmed", "late", "downtrend_confirmed"},
}
STRUCTURAL_STATES = {"introduction", "growth", "maturity", "decline"}
SIGNAL_DIRECTIONS = {"bullish", "bearish", "neutral"}
OBSERVATION_DIRECTIONS = {"improving", "deteriorating", "neutral"}
STRATEGIC_ROUTE_TARGETS = {
    "optical_module_equipment": {
        "effective_preset": "optical-module",
        "target_peer_group": "optical_module_related",
        "scenario": "second_growth_curve",
    },
}


def build_execution_plan(
    target: str,
    packet: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
    reference_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic route and bounded collection plan."""
    source = dict(packet or {})
    config = dict(context or {})
    anchor = (
        reference_date
        or config.get("reference_date")
        or config.get("analysis_reference_date")
        or source.get("as_of_date")
        or date.today().isoformat()
    )
    target_block = _resolve_target(target, source, config)
    route_evidence, route_evidence_errors = _admit_route_evidence(
        target_block,
        source,
        str(anchor),
    )
    if route_evidence:
        target_block["preset"] = route_evidence[0]["effective_preset"]
    preset_data = _load_preset(target_block["preset"])
    raw_profile = (
        deepcopy(source.get("methodology_profile"))
        if "methodology_profile" in source
        else deepcopy((preset_data or {}).get("methodology_profile"))
    )
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    route, route_errors = _resolve_route(target_block, profile, route_evidence)
    selected_methodology = _selected_methodology(profile, route)
    errors = _dedupe(_validate_profile(profile, route) + route_errors)
    profile_valid = not errors
    report_periods = _report_periods(str(anchor))
    required_tasks: List[Dict[str, Any]] = []
    optional_tasks: List[Dict[str, Any]] = []
    if profile_valid:
        required_tasks, optional_tasks = _build_tasks(selected_methodology, route, report_periods)
    methodology = _normalize_profile(selected_methodology, route, profile_valid, errors)
    data_availability, availability_observed = _data_availability(source)
    checks = [
        _check("target_resolved", bool(target_block.get("stock_code")), target_block.get("stock_code")),
        _check("preset_resolved", target_block.get("preset") not in {None, "", "generic"}, target_block.get("preset")),
        _check("methodology_profile_valid", profile_valid, errors or methodology.get("version")),
        _check("peer_group_resolved", bool(route.get("target_peer_group")), route.get("target_peer_group")),
        _check("peer_candidates_sufficient", len(route.get("peer_candidates") or []) >= 3, len(route.get("peer_candidates") or [])),
        _check("required_tasks_present", bool(required_tasks), len(required_tasks)),
        _check("report_periods_resolved", bool(report_periods.get("report_period")), report_periods),
        _check(
            "provider_or_cache_available",
            data_availability != "unavailable",
            availability_observed,
            blocking=False,
        ),
    ]
    preflight_status = "passed" if all(item["passed"] for item in checks if item["blocking"]) else "failed"
    task_ids = [task["task_id"] for task in required_tasks + optional_tasks]
    return {
        "schema_version": COLLECTION_PLAN_SCHEMA_VERSION,
        "reference_date": str(anchor),
        "report_periods": report_periods,
        "scenario": route.get("scenario") or "preset_static_route",
        "target": target_block,
        "route": route,
        "route_evidence": route_evidence,
        "route_evidence_rejections": route_evidence_errors,
        "methodology_profile": methodology,
        "required_tasks": required_tasks,
        "optional_tasks": optional_tasks,
        "preflight": {
            "status": preflight_status,
            "data_availability": data_availability,
            "checks": checks,
            "errors": errors,
        },
        "ceiling": {
            "allowed_task_ids": task_ids,
            "peer_candidates": list(route.get("peer_candidates") or []),
            "peer_scope_ladder": list(route.get("peer_scope_ladder") or []),
            "peer_scope_candidates": _peer_scope_candidates(
                profile,
                route,
                target_block.get("stock_code") or "",
            ),
            "indicator_ids": [
                indicator.get("id")
                for role in PROFILE_ROLES
                for indicator in ((methodology.get("indicators") or {}).get(role) or [])
                if indicator.get("id")
            ],
        },
        "needs_data": _planning_needs_data(
            preflight_status,
            errors,
            required_tasks,
            source,
        ),
    }


def _resolve_target(target: str, source: Mapping[str, Any], context: Mapping[str, Any]) -> Dict[str, Any]:
    from .core.auto_detect_preset import auto_detect_preset, resolve_stock_identity

    provided = dict(source.get("target") or {})
    normalized_code, resolved_name = resolve_stock_identity(str(target))
    if not _looks_like_stock_code(normalized_code):
        normalized_code = str(provided.get("stock_code") or normalized_code)
    normalized_code, code_name = resolve_stock_identity(normalized_code)
    stock_name = code_name if code_name != normalized_code else resolved_name
    stock_name = provided.get("stock_name") or context.get("stock_name") or stock_name
    preset = provided.get("preset") or context.get("preset")
    if not preset or preset == "generic":
        preset = auto_detect_preset(normalized_code, DATA_DIR, allow_provider_lookup=False) or "generic"
    return {
        "stock_code": normalized_code,
        "stock_name": stock_name,
        "preset": preset,
        "industry": provided.get("industry") or "",
        "sub_sector": provided.get("sub_sector") or "",
        "input_type": provided.get("input_type") or context.get("input_type") or "stock_code",
    }


def _resolve_route(
    target: Mapping[str, Any],
    profile: Mapping[str, Any],
    route_evidence: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    peer_groups = profile.get("peer_groups") if isinstance(profile.get("peer_groups"), dict) else {}
    routes = profile.get("stock_routes") if isinstance(profile.get("stock_routes"), dict) else {}
    code = str(target.get("stock_code") or "")
    route_config = routes.get(code) if isinstance(routes.get(code), dict) else {}
    strategic = dict(route_evidence[0]) if route_evidence else {}
    raw_group_id = (
        strategic.get("target_peer_group")
        or route_config.get("peer_group")
        or profile.get("default_peer_group")
        or ""
    )
    group_id = raw_group_id if _nonempty_string(raw_group_id) else ""
    group = peer_groups.get(group_id) if isinstance(peer_groups.get(group_id), dict) else {}
    if not group_id:
        errors.append("methodology_profile 缺少 default_peer_group 或股票路由。")
    elif not group:
        errors.append(f"methodology_profile 未定义同行组 {group_id}。")
    candidates = [str(item) for item in _list_value(group.get("peer_candidates")) if item and str(item) != code]
    route_mode = "evidence_backed_strategic" if strategic else route_config.get("route_mode") or "preset_static"
    return {
        "target_peer_group": group_id,
        "target_peer_group_name": group.get("name") or group_id,
        "evidence_scope": group_id,
        "evidence_scope_name": group.get("name") or group_id,
        "peer_scope_mode": "bounded_parent" if strategic else "exact",
        "route_mode": route_mode,
        "scenario": strategic.get("scenario") or route_config.get("scenario") or "normal_business",
        "route_evidence_refs": (
            [str(item.get("evidence_id")) for item in route_evidence]
            if strategic
            else list(_list_value(route_config.get("evidence_refs")))
        ),
        "peer_candidates": candidates,
        "peer_scope_ladder": [str(item) for item in _list_value(group.get("peer_scope_ladder")) if item],
        "needs_human_review": route_mode == "preset_static" or bool(strategic),
    }, errors


def _admit_route_evidence(
    target: Mapping[str, Any],
    source: Mapping[str, Any],
    reference_date: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Admit L1 commercial facts for routing only, never for System A votes."""
    raw_items = source.get("route_evidence")
    if not isinstance(raw_items, list):
        return [], []
    target_code = str(target.get("stock_code") or "").upper()
    admitted: List[Dict[str, Any]] = []
    errors: List[str] = []
    required = {
        "evidence_id", "stock_code", "trigger_type", "order_status",
        "business_scope", "effective_preset", "target_peer_group",
        "source_level", "source_type", "source_title", "source_url",
        "report_period", "as_of_date", "raw_fields", "raw_values",
        "derivation_method",
    }
    allowed_sources = {
        "company_annual_report", "company_announcement", "regulatory_filing",
    }
    try:
        reference = date.fromisoformat(str(reference_date)[:10])
    except ValueError:
        reference = date.today()
    for index, raw in enumerate(raw_items):
        item = dict(raw) if isinstance(raw, Mapping) else {}
        missing = sorted(field for field in required if not item.get(field))
        prefix = f"route_evidence[{index}]"
        if missing:
            errors.append(f"{prefix} 缺少字段：{', '.join(missing)}。")
            continue
        if str(item.get("stock_code") or "").upper() != target_code:
            errors.append(f"{prefix} 与目标股票不一致。")
            continue
        if item.get("source_level") != "L1" or item.get("source_type") not in allowed_sources:
            errors.append(f"{prefix} 不是可验证的 L1 公司/监管披露。")
            continue
        if item.get("trigger_type") != "confirmed_order" or item.get("order_status") not in {"confirmed", "delivered"}:
            errors.append(f"{prefix} 未达到已确认订单或交付的战略路由条件。")
            continue
        strategic_target = STRATEGIC_ROUTE_TARGETS.get(str(item.get("business_scope") or ""))
        if not strategic_target or any(
            item.get(field) != expected
            for field, expected in strategic_target.items()
            if field != "scenario"
        ):
            errors.append(f"{prefix} 超出预定义战略路由边界。")
            continue
        item["scenario"] = strategic_target["scenario"]
        try:
            evidence_date = date.fromisoformat(str(item.get("as_of_date") or "")[:10])
        except ValueError:
            errors.append(f"{prefix} as_of_date 无效。")
            continue
        age_days = (reference - evidence_date).days
        if age_days < -7 or age_days > 450:
            errors.append(f"{prefix} 超出 450 天战略路由有效期。")
            continue
        admitted.append(item)
    admitted.sort(
        key=lambda item: (str(item.get("as_of_date") or ""), str(item.get("evidence_id") or "")),
        reverse=True,
    )
    return admitted[:1], errors


def _validate_profile(profile: Mapping[str, Any], route: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in ("version", "default_peer_group", "peer_groups"):
        if not profile.get(field):
            errors.append(f"methodology_profile 缺少 {field}。")
    if len(route.get("peer_candidates") or []) < 3:
        errors.append("目标同行组排除标的后少于三家固定候选。")
    peer_groups = profile.get("peer_groups") if isinstance(profile.get("peer_groups"), dict) else {}
    stock_routes = profile.get("stock_routes") if isinstance(profile.get("stock_routes"), dict) else {}
    for stock_code, route_value in stock_routes.items():
        if not isinstance(route_value, dict):
            errors.append(f"股票路由 {stock_code} 必须为映射。")
            continue
        if "evidence_refs" in route_value and not isinstance(route_value.get("evidence_refs"), list):
            errors.append(f"股票路由 {stock_code} 的 evidence_refs 必须为列表。")
        elif not all(_nonempty_string(item) for item in route_value.get("evidence_refs") or []):
            errors.append(f"股票路由 {stock_code} 的 evidence_refs 必须为非空字符串列表。")
        if "peer_group" in route_value and not _nonempty_string(route_value.get("peer_group")):
            errors.append(f"股票路由 {stock_code} 的 peer_group 必须为非空字符串。")
    for group_id, raw_group in peer_groups.items():
        group = raw_group if isinstance(raw_group, dict) else {}
        candidates = group.get("peer_candidates")
        if not isinstance(candidates, list) or not candidates:
            errors.append(f"同行组 {group_id} 缺少固定候选集。")
        elif len(candidates) > 8:
            errors.append(f"同行组 {group_id} 固定候选超过八家上限。")
        elif not all(_nonempty_string(item) for item in candidates):
            errors.append(f"同行组 {group_id} 固定候选必须为非空字符串。")
        scope_ladder = group.get("peer_scope_ladder")
        if not isinstance(scope_ladder, list):
            errors.append(f"同行组 {group_id} 的 peer_scope_ladder 必须为列表。")
        for scope in _list_value(scope_ladder):
            if not _nonempty_string(scope):
                errors.append(f"同行组 {group_id} 的 peer_scope_ladder 元素必须为非空字符串。")
            elif scope not in peer_groups:
                errors.append(f"peer_scope_ladder 引用了未定义同行组 {scope}。")
        errors.extend(_validate_group_methodology(group_id, group.get("methodology_profile")))
    return _dedupe(errors)


def _validate_group_methodology(group_id: str, value: Any) -> List[str]:
    methodology = value if isinstance(value, dict) else {}
    errors: List[str] = []
    for field in (
        "version", "profile_id", "reference_series", "indicators",
        "observation_windows", "thresholds", "minimum_decision_sets",
        "state_transition_rules", "source_citations",
    ):
        if not methodology.get(field):
            errors.append(f"同行组 {group_id} 的 methodology_profile 缺少 {field}。")
    indicators = methodology.get("indicators") if isinstance(methodology.get("indicators"), dict) else {}
    windows = methodology.get("observation_windows") if isinstance(methodology.get("observation_windows"), dict) else {}
    thresholds = methodology.get("thresholds") if isinstance(methodology.get("thresholds"), dict) else {}
    transitions = methodology.get("state_transition_rules") if isinstance(methodology.get("state_transition_rules"), dict) else {}
    minimum_sets = methodology.get("minimum_decision_sets") if isinstance(methodology.get("minimum_decision_sets"), dict) else {}
    if methodology.get("observation_windows") and not isinstance(methodology.get("observation_windows"), dict):
        errors.append(f"同行组 {group_id} 的 observation_windows 必须为映射。")
    if methodology.get("thresholds") and not isinstance(methodology.get("thresholds"), dict):
        errors.append(f"同行组 {group_id} 的 thresholds 必须为映射。")
    for field in ("minimum_periods", "default_freshness_days"):
        if not _positive_int(windows.get(field)):
            errors.append(f"同行组 {group_id} 的 observation_windows.{field} 必须为正整数。")
    if not _positive_int(thresholds.get("minimum_peer_sample")):
        errors.append(f"同行组 {group_id} 的 thresholds.minimum_peer_sample 必须为正整数。")
    for field in ("minimum_coverage_ratio", "minimum_agreement_ratio"):
        if not _unit_ratio(thresholds.get(field)):
            errors.append(f"同行组 {group_id} 的 thresholds.{field} 必须在 (0, 1]。")
    for conclusion in ("cyclical_phase", "inflection_state", "structural_lifecycle", "signal_direction"):
        if not isinstance(transitions.get(conclusion), dict):
            errors.append(f"同行组 {group_id} 的 state_transition_rules 缺少 {conclusion}。")
    for role in PROFILE_ROLES:
        if not isinstance(indicators.get(role), list):
            errors.append(f"同行组 {group_id} 的 indicators.{role} 必须为列表。")
        elif role in {"barometer", "mid_axis", "ebb_warning"} and not indicators.get(role):
            errors.append(f"同行组 {group_id} 的 indicators 缺少 {role}。")
    for role in PROFILE_ROLES:
        for indicator in _list_value(indicators.get(role)):
            if (
                not isinstance(indicator, dict)
                or not _nonempty_string(indicator.get("id"))
                or not _nonempty_string(indicator.get("field_path"))
            ):
                errors.append(f"同行组 {group_id} 的 {role} 指标缺少 id 或 field_path。")
                continue
            source_levels = indicator.get("source_levels")
            if not isinstance(source_levels, list) or not source_levels:
                errors.append(f"同行组 {group_id} 的 {role}.{indicator.get('id')} 缺少 source_levels。")
            elif not {str(item).upper() for item in source_levels}.issubset(SOURCE_LEVELS):
                errors.append(f"同行组 {group_id} 的 {role}.{indicator.get('id')} source_levels 非法。")
            if not _nonempty_string(indicator.get("comparison")) or indicator.get("comparison") not in SUPPORTED_COMPARISONS:
                errors.append(f"同行组 {group_id} 的 {role}.{indicator.get('id')} comparison 不受支持。")
            if not isinstance(indicator.get("periods"), int) or indicator.get("periods", 0) <= 0:
                errors.append(f"同行组 {group_id} 的 {role}.{indicator.get('id')} periods 必须为正整数。")
            freshness = indicator.get("freshness_days", windows.get("default_freshness_days"))
            if not _positive_int(freshness):
                errors.append(f"同行组 {group_id} 的 {role}.{indicator.get('id')} 缺少 freshness 规则。")
            if CONCLUSION_FIELDS.intersection(indicator):
                errors.append(f"{role}.{indicator.get('id')} 不得包含结论字段。")
    indicator_ids = {
        indicator.get("id")
        for role in PROFILE_ROLES
        for indicator in _list_value(indicators.get(role))
        if isinstance(indicator, dict) and _nonempty_string(indicator.get("id"))
    }
    for readiness in ("peer_proxy_ready", "industry_ready"):
        decision_set = minimum_sets.get(readiness) if isinstance(minimum_sets.get(readiness), dict) else {}
        required_ids = decision_set.get("required_indicator_ids") or []
        required_roles = decision_set.get("required_roles") or []
        if (
            not isinstance(required_ids, list)
            or not isinstance(required_roles, list)
            or not required_ids
            or not required_roles
            or not all(_nonempty_string(item) for item in required_ids + required_roles)
        ):
            errors.append(f"同行组 {group_id} 的 minimum_decision_sets.{readiness} 不完整。")
            continue
        if not set(required_ids).issubset(indicator_ids):
            errors.append(f"同行组 {group_id} 的 minimum_decision_sets.{readiness} 引用了未知指标。")
        if not set(required_roles).issubset(PROFILE_ROLES):
            errors.append(f"同行组 {group_id} 的 minimum_decision_sets.{readiness} 引用了未知角色。")
    errors.extend(_validate_state_rules(group_id, transitions))
    return errors


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _unit_ratio(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < float(value) <= 1


def _list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_state_rules(group_id: str, transitions: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for conclusion, allowed_states in CONCLUSION_STATES.items():
        block = transitions.get(conclusion) if isinstance(transitions.get(conclusion), dict) else {}
        if block.get("fallback") != "undetermined":
            errors.append(f"同行组 {group_id} 的 {conclusion}.fallback 必须为 undetermined。")
        rule_values = block.get("rules")
        if not isinstance(rule_values, list):
            errors.append(f"同行组 {group_id} 的 {conclusion}.rules 必须为列表。")
        for rule in _list_value(rule_values):
            if not isinstance(rule, dict) or not _nonempty_string(rule.get("state")) or rule.get("state") not in allowed_states:
                errors.append(f"同行组 {group_id} 的 {conclusion} 包含非法 state。")
                continue
            conditions = rule.get("all")
            if not isinstance(conditions, list) or not conditions:
                errors.append(f"同行组 {group_id} 的 {conclusion}.{rule.get('state')} 缺少 all 条件。")
                continue
            for condition in conditions:
                if (
                    not isinstance(condition, dict)
                    or condition.get("role") not in PROFILE_ROLES
                    or not _nonempty_string(condition.get("direction"))
                    or condition.get("direction") not in OBSERVATION_DIRECTIONS
                    or not isinstance(condition.get("min_count"), int)
                    or condition.get("min_count", 0) <= 0
                ):
                    errors.append(f"同行组 {group_id} 的 {conclusion}.{rule.get('state')} 条件非法。")
    structural = transitions.get("structural_lifecycle") if isinstance(transitions.get("structural_lifecycle"), dict) else {}
    if structural.get("fallback") != "undetermined":
        errors.append(f"同行组 {group_id} 的 structural_lifecycle.fallback 必须为 undetermined。")
    bands = structural.get("bands")
    if not isinstance(bands, list):
        errors.append(f"同行组 {group_id} 的 structural_lifecycle.bands 必须为列表。")
    for band in _list_value(bands):
        if not isinstance(band, dict) or not _nonempty_string(band.get("state")) or band.get("state") not in STRUCTURAL_STATES:
            errors.append(f"同行组 {group_id} 的 structural_lifecycle 包含非法 band。")
            continue
        for bound in ("min_inclusive", "max_exclusive"):
            if bound in band and not isinstance(band[bound], (int, float)):
                errors.append(f"同行组 {group_id} 的 structural_lifecycle.{bound} 必须为数值。")
    signal = transitions.get("signal_direction") if isinstance(transitions.get("signal_direction"), dict) else {}
    if signal.get("fallback") != "neutral":
        errors.append(f"同行组 {group_id} 的 signal_direction.fallback 必须为 neutral。")
    signal_rules = signal.get("rules")
    if not isinstance(signal_rules, list):
        errors.append(f"同行组 {group_id} 的 signal_direction.rules 必须为列表。")
    for rule in _list_value(signal_rules):
        if not isinstance(rule, dict) or not _nonempty_string(rule.get("direction")) or rule.get("direction") not in SIGNAL_DIRECTIONS:
            errors.append(f"同行组 {group_id} 的 signal_direction 包含非法 direction。")
            continue
        conditions = rule.get("all")
        if not isinstance(conditions, list) or not conditions:
            errors.append(f"同行组 {group_id} 的 signal_direction.{rule.get('direction')} 缺少 all 条件。")
            continue
        for condition in conditions:
            conclusion = condition.get("conclusion") if isinstance(condition, dict) else None
            states = condition.get("states") if isinstance(condition, dict) else None
            if (
                not _nonempty_string(conclusion)
                or conclusion not in CONCLUSION_STATES
                or not isinstance(states, list)
                or not states
                or not all(isinstance(state, str) and state in CONCLUSION_STATES.get(conclusion, set()) for state in states)
            ):
                errors.append(f"同行组 {group_id} 的 signal_direction.{rule.get('direction')} 条件非法。")
    return errors


def _selected_methodology(profile: Mapping[str, Any], route: Mapping[str, Any]) -> Dict[str, Any]:
    peer_groups = profile.get("peer_groups") if isinstance(profile.get("peer_groups"), dict) else {}
    group = peer_groups.get(route.get("target_peer_group"))
    if not isinstance(group, dict) or not isinstance(group.get("methodology_profile"), dict):
        return {}
    return deepcopy(group["methodology_profile"])


def _normalize_profile(profile: Mapping[str, Any], route: Mapping[str, Any], valid: bool, errors: List[str]) -> Dict[str, Any]:
    result = {
        field: deepcopy(profile.get(field))
        for field in (
            "version", "profile_id", "reference_series", "indicators",
            "observation_windows", "thresholds", "minimum_decision_sets",
            "state_transition_rules", "source_citations",
        )
    }
    if not valid:
        for field in (
            "indicators", "observation_windows", "thresholds",
            "minimum_decision_sets", "state_transition_rules",
        ):
            result[field] = {}
    result.update({"valid": valid, "errors": list(errors), "target_peer_group": route.get("target_peer_group") or ""})
    return result


def _build_tasks(
    profile: Mapping[str, Any],
    route: Mapping[str, Any],
    report_periods: Mapping[str, str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    required: List[Dict[str, Any]] = []
    optional: List[Dict[str, Any]] = []
    indicators = profile.get("indicators") or {}
    windows = profile.get("observation_windows") or {}
    candidates = list(route.get("peer_candidates") or [])
    for role in PROFILE_ROLES:
        for indicator in _list_value(indicators.get(role)):
            scope = indicator.get("scope") or "peer_basket"
            item = {
                "task_id": f"{role}:{indicator['id']}",
                "role": role,
                "indicator_id": indicator["id"],
                "field_path": indicator["field_path"],
                "scope": scope,
                "peer_candidates": candidates if scope == "peer_basket" else [],
                "periods": int(indicator.get("periods") or windows.get("minimum_periods") or 2),
                "report_period": report_periods.get("report_period"),
                "comparison_report_period": report_periods.get("comparison_report_period"),
                "previous_balance_report_period": report_periods.get("previous_balance_report_period"),
                "comparison": indicator.get("comparison") or "same_period_yoy",
                "source_levels": list(indicator.get("source_levels") or ["L1"]),
                "freshness_days": int(indicator.get("freshness_days") or windows.get("default_freshness_days") or 180),
                "conclusion_fields": [],
            }
            (required if indicator.get("required") else optional).append(item)
    return required, optional


def _report_periods(reference_date: str) -> Dict[str, str]:
    """Resolve the latest quarterly report guaranteed public by statutory deadline."""
    try:
        anchor = datetime.strptime(reference_date[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {}
    if anchor >= date(anchor.year, 10, 31):
        report = date(anchor.year, 9, 30)
    elif anchor >= date(anchor.year, 8, 31):
        report = date(anchor.year, 6, 30)
    elif anchor >= date(anchor.year, 4, 30):
        report = date(anchor.year, 3, 31)
    else:
        report = date(anchor.year - 1, 9, 30)
    comparison = date(report.year - 1, report.month, report.day)
    previous_quarter = {
        (3, 31): date(report.year - 1, 12, 31),
        (6, 30): date(report.year, 3, 31),
        (9, 30): date(report.year, 6, 30),
        (12, 31): date(report.year, 9, 30),
    }[(report.month, report.day)]
    return {
        "report_period": report.isoformat(),
        "comparison_report_period": comparison.isoformat(),
        "previous_balance_report_period": previous_quarter.isoformat(),
        "availability_policy": "statutory_deadline",
    }


def _data_availability(source: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    statuses = dict(source.get("provider_status") or {})
    source_mode = str(source.get("source_mode") or "missing")
    values = {str(value).lower() for value in statuses.values()}
    if source_mode in {"stale_cache"} or "stale" in values:
        status = "degraded"
    elif source_mode in {"live", "cache", "mixed_cache", "offline_harness"} or values.intersection({"live", "cache", "success"}):
        status = "available"
    else:
        status = "unavailable"
    return status, {"source_mode": source_mode, "provider_status": statuses}


def _peer_scope_candidates(
    profile: Mapping[str, Any],
    route: Mapping[str, Any],
    target_code: str,
) -> Dict[str, List[str]]:
    peer_groups = profile.get("peer_groups") if isinstance(profile.get("peer_groups"), dict) else {}
    result: Dict[str, List[str]] = {}
    for scope in _list_value(route.get("peer_scope_ladder")):
        group = peer_groups.get(scope) if isinstance(peer_groups.get(scope), dict) else {}
        if group:
            result[scope] = [
                str(item)
                for item in _list_value(group.get("peer_candidates"))
                if item and str(item) != target_code
            ]
    return result


def _load_preset(preset: str) -> Dict[str, Any]:
    if not preset or preset == "generic":
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    for path in sorted(PRESET_DIR.rglob(f"{preset}.yaml")):
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError, yaml.YAMLError):
            return {}
    return {}


def _planning_needs_data(
    status: str,
    errors: List[str],
    required_tasks: List[Dict[str, Any]],
    source: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if status == "failed":
        return [{"field_path": "methodology_profile", "reason": "；".join(errors) or "采集计划前置校验失败。", "required": True}]
    return [
        {"field_path": task["field_path"], "task_id": task["task_id"], "reason": "required collection task pending", "required": True}
        for task in required_tasks
        if not _path_has_value(source or {}, str(task.get("field_path") or ""))
    ]


def _path_has_value(source: Mapping[str, Any], field_path: str) -> bool:
    value: Any = source
    for part in field_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return False
        value = value[part]
    return value is not None and value != "" and value != [] and value != {}


def _check(name: str, passed: bool, observed: Any, blocking: bool = True) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "blocking": blocking, "observed": observed}


def _looks_like_stock_code(value: str) -> bool:
    return len("".join(char for char in value if char.isdigit())) >= 6


def _dedupe(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))
