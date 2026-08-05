"""Executable project-level harness for Industrial Sentinel.

Only the data adapter is fake. IndustryAgent, the Skill runtime, Signal,
AgentScope message bridge, OrchestratorAgent and ArbitrationEngine are real.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4
import json
import os
import re
import tempfile


REFERENCE_DATE = "2026-07-10"
FIXTURE_NAMES = ("framework_only", "peer_proxy_ready", "industry_ready")


class FixtureDataAdapter:
    """Offline adapter satisfying the production data-source seam."""

    def __init__(self, packet: Dict[str, Any]):
        self.packet = packet
        self.calls: List[str] = []

    def get_data(self, stock_code: str) -> Dict[str, Any]:
        self.calls.append(stock_code)
        return {
            "packet": self.packet,
            "industry_result": None,
            "financial_data": None,
            "industry_from_cache": False,
            "financial_from_cache": False,
            "industry_status": "offline_harness",
            "financial_status": "offline_harness",
            "degradation_reasons": [],
        }


def run_project_harness(
    stock_code: str = "300782",
    fixture: str = "all",
    output_dir: Optional[Path] = None,
    reference_date: str = REFERENCE_DATE,
    live_smoke: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Run one or all mandatory fixtures and optionally persist JSON/HTML."""
    selected = list(FIXTURE_NAMES) if fixture == "all" else [fixture]
    unknown = [name for name in selected if name not in FIXTURE_NAMES]
    if unknown:
        raise ValueError(f"unknown fixture: {', '.join(unknown)}")

    run_id = f"industrial_sentinel_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    cases = [
        _run_case(stock_code, name, reference_date)
        for name in selected
    ]
    for case in cases:
        _attach_report_gates(case)
    report: Dict[str, Any] = {
        "run_id": run_id,
        "status": "passed" if all(case["status"] == "passed" for case in cases) else "failed",
        "stock_code": stock_code,
        "reference_date": reference_date,
        "environment": "offline_harness",
        "pipeline": [
            "FixtureDataAdapter",
            "IndustryAgent",
            "industrial_sentinel runtime",
            "Signal / AgentScope message bridge",
            "OrchestratorAgent / ArbitrationEngine",
        ],
        "live_smoke": _normalize_live_smoke(live_smoke),
        "cases": cases,
        "artifacts": {},
    }

    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / f"{run_id}.json"
        html_path = output_path / f"{run_id}.html"
        report_paths: Dict[str, str] = {}
        for case in cases:
            fixture_name = str(case.get("fixture") or "case")
            case_path = output_path / f"{run_id}_{fixture_name}_report.html"
            report_paths[fixture_name] = str(case_path)
            _atomic_write(case_path, str(case.pop("_report_html", "")))
        report["artifacts"] = {
            "json": str(json_path),
            "html": str(html_path),
            "analysis_reports": report_paths,
        }
        _atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, default=str))
        _atomic_write(html_path, render_harness_html(report))
    else:
        for case in cases:
            case.pop("_report_html", None)
    return report


def run_live_project_harness(
    stock_code: str = "300782",
    output_dir: Optional[Path] = None,
    reference_date: Optional[str] = None,
    data_source: Optional[Any] = None,
    agent_timeout_seconds: float = 90.0,
    peer_fetch_workers: int = 4,
) -> Dict[str, Any]:
    """Run the production industry data source through the real project path.

    Unlike ``run_project_harness``, this entry does not construct fixtures.  A
    data source may only be injected for deterministic contract tests; the CLI
    leaves it unset so IndustryAgent creates the production source.
    """
    from agents.industry.agent import IndustryAgent
    from agents.orchestrator.agent import OrchestratorAgent

    anchor = reference_date or date.today().isoformat()
    agent_config: Dict[str, Any] = {
        "analysis_reference_date": anchor,
        "industry_peer_fetch_workers": peer_fetch_workers,
    }
    if data_source is not None:
        agent_config["data_source"] = data_source
    agent = IndustryAgent(config=agent_config)
    orchestrator = OrchestratorAgent(
        config={
            "confidence_threshold": 0.5,
            "auto_select_scenario": False,
            "agent_timeout_seconds": float(agent_timeout_seconds),
            "arbitration": {"mode": "rule"},
        }
    )
    orchestrator.register_expert(agent)

    started_at = datetime.now()
    arbitration = orchestrator.analyze(stock_code)
    finished_at = datetime.now()
    arbitration_data = _serialize(arbitration)
    trace = dict(arbitration_data.get("scope_trace") or {})
    executions = trace.get("execution_results") or []
    signal = executions[0].get("signal") if executions else None
    packet = deepcopy(agent.last_data_packet or {})
    assertions = _live_case_assertions(packet, signal, arbitration_data, trace)
    case = {
        "fixture": "live",
        "status": "passed" if all(item["passed"] for item in assertions) else "failed",
        "input_mode": "live",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "packet": packet,
        "skill_result": agent.last_skill_result,
        "adapter_calls": [],
        "industry_signal": signal,
        "arbitration_result": arbitration_data,
        "assertions": assertions,
    }
    _attach_report_gates(case)
    run_id = f"industrial_sentinel_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    report: Dict[str, Any] = {
        "run_id": run_id,
        "status": case["status"],
        "stock_code": stock_code,
        "reference_date": anchor,
        "environment": "live",
        "pipeline": [
            "IndustrialSentinelDataSource",
            "IndustryAgent",
            "industrial_sentinel runtime",
            "Signal / AgentScope message bridge",
            "OrchestratorAgent / ArbitrationEngine",
        ],
        "live_smoke": _normalize_live_smoke(None),
        "cases": [case],
        "artifacts": {},
    }
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / f"{run_id}.json"
        html_path = output_path / f"{run_id}.html"
        analysis_path = output_path / f"{run_id}_analysis_report.html"
        _atomic_write(analysis_path, str(case.pop("_report_html", "")))
        report["artifacts"] = {
            "json": str(json_path),
            "html": str(html_path),
            "analysis_reports": {"live": str(analysis_path)},
        }
        _atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, default=str))
        _atomic_write(html_path, render_harness_html(report))
    else:
        case.pop("_report_html", None)
    return report


def _live_case_assertions(
    packet: Mapping[str, Any],
    signal: Optional[Mapping[str, Any]],
    arbitration: Mapping[str, Any],
    trace: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    summary = dict(trace.get("summary") or {})
    meta = dict((signal or {}).get("meta") or {})
    conclusions = [
        dict(meta.get(name) or {})
        for name in ("structural_lifecycle", "cyclical_phase", "inflection_state")
    ]
    system_a_consistent = bool(meta.get("usable_for_system_a")) or all(
        conclusion.get("state") == "undetermined"
        and not conclusion.get("evidence_refs")
        for conclusion in conclusions
    )
    return [
        _assertion("production_packet_returned", packet.get("schema_version") == "industry-data/0.2", packet.get("schema_version")),
        _assertion("not_offline_fixture", packet.get("source_mode") != "offline_harness", packet.get("source_mode")),
        _assertion("real_signal_returned", bool(signal and signal.get("signal_type") == "industry"), (signal or {}).get("signal_type")),
        _assertion("agentscope_success", summary.get("success_count") == 1, summary),
        _assertion("no_agent_failure", all(summary.get(key, 0) == 0 for key in ("failed_count", "timeout_count", "invalid_count")), summary),
        _assertion("system_a_conclusions_consistent", system_a_consistent, conclusions),
        _assertion("arbitration_result", arbitration.get("decision") in {"buy", "hold", "sell", "wait"}, arbitration.get("decision")),
    ]


def _run_case(stock_code: str, fixture_name: str, reference_date: str) -> Dict[str, Any]:
    from agents.industry.agent import IndustryAgent
    from agents.orchestrator.agent import OrchestratorAgent

    packet = build_fixture_packet(fixture_name, stock_code, reference_date)
    adapter = FixtureDataAdapter(packet)
    agent = IndustryAgent(
        config={
            "data_source": adapter,
            "analysis_reference_date": reference_date,
        }
    )
    orchestrator = OrchestratorAgent(
        config={
            "confidence_threshold": 0.5,
            "auto_select_scenario": False,
            "agent_timeout_seconds": 5,
            "arbitration": {"mode": "rule"},
        }
    )
    orchestrator.register_expert(agent)
    arbitration = orchestrator.analyze(stock_code)
    arbitration_data = _serialize(arbitration)
    trace = arbitration_data.get("scope_trace") or {}
    executions = trace.get("execution_results") or []
    signal = executions[0].get("signal") if executions else None

    assertions = _case_assertions(
        fixture_name=fixture_name,
        adapter=adapter,
        signal=signal,
        arbitration=arbitration_data,
        trace=trace,
    )
    return {
        "fixture": fixture_name,
        "status": "passed" if all(item["passed"] for item in assertions) else "failed",
        "input_mode": "offline_harness",
        "packet": packet,
        "skill_result": agent.last_skill_result,
        "adapter_calls": adapter.calls,
        "industry_signal": signal,
        "arbitration_result": arbitration_data,
        "assertions": assertions,
    }


def _case_assertions(
    fixture_name: str,
    adapter: FixtureDataAdapter,
    signal: Optional[Mapping[str, Any]],
    arbitration: Mapping[str, Any],
    trace: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    summary = dict(trace.get("summary") or {})
    meta = dict((signal or {}).get("meta") or {})
    signal_text = " ".join((signal or {}).get("signals") or [])
    results = [
        _assertion("adapter_called", bool(adapter.calls), adapter.calls),
        _assertion(
            "real_signal_returned",
            bool(signal and signal.get("signal_type") == "industry"),
            {
                "direction": (signal or {}).get("direction"),
                "confidence": (signal or {}).get("confidence"),
                "readiness": meta.get("readiness"),
            },
        ),
        _assertion("agentscope_success", summary.get("success_count") == 1, summary),
        _assertion("no_agent_failure", all(summary.get(key, 0) == 0 for key in ("failed_count", "timeout_count", "invalid_count")), summary),
        _assertion("arbitration_result", arbitration.get("decision") in {"buy", "hold", "sell", "wait"}, arbitration.get("decision")),
    ]
    if fixture_name == "framework_only":
        results.extend(
            [
                _assertion("framework_readiness", meta.get("readiness") == "framework_only", meta.get("readiness")),
                _assertion("framework_neutral", (signal or {}).get("direction") == "neutral", (signal or {}).get("direction")),
                _assertion("framework_zero_weight", (signal or {}).get("weight") == 0.0, (signal or {}).get("weight")),
                _assertion("no_fake_state", "拐点前" not in signal_text and "成熟期" not in signal_text, signal_text),
                _assertion("framework_filtered", arbitration.get("signals_summary", {}).get("total") == 0, arbitration.get("signals_summary")),
                _assertion("framework_wait", arbitration.get("decision") == "wait", arbitration.get("decision")),
            ]
        )
    else:
        expected = "peer_proxy_ready" if fixture_name == "peer_proxy_ready" else "industry_ready"
        results.extend(
            [
                _assertion("qualified_readiness", meta.get("readiness") == expected, meta.get("readiness")),
                _assertion("qualified_system_a", meta.get("usable_for_system_a") is True, meta.get("usable_for_system_a")),
                _assertion("qualified_consumed", arbitration.get("signals_summary", {}).get("total") == 1, arbitration.get("signals_summary")),
                _assertion("single_agent_hold", arbitration.get("decision") == "hold", arbitration.get("decision")),
                _assertion("evidence_preserved", bool(meta.get("evidence")), len(meta.get("evidence") or [])),
            ]
        )
    return results


def _assertion(name: str, passed: bool, observed: Any) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "observed": observed}


def _normalized_claim(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "")).lower()


def _report_quality_issues(
    html: str,
    result: Mapping[str, Any],
    required_ids: Iterable[str],
) -> List[str]:
    """Return deterministic report defects; an empty list is the release gate."""
    meta = dict(result.get("meta") or {})
    combined = dict(meta.get("combined_conclusion") or {})
    system_b = dict(meta.get("system_b") or {})
    thesis = (
        combined.get("short_status")
        or system_b.get("core_contradiction")
        or ""
    )
    summary = combined.get("summary") or ""
    issues: List[str] = []
    for item in required_ids:
        if len(re.findall(rf'\bid="{re.escape(item)}"', html)) != 1:
            issues.append(f"html_id:{item}")
    if "<script src=" in html or "<link " in html:
        issues.append("external_asset")
    th_counts = [
        len(re.findall(r"<th\b", block))
        for block in re.findall(r"<thead\b.*?</thead>", html, flags=re.DOTALL)
    ]
    if th_counts and max(th_counts) > 5:
        issues.append("table_over_5_columns")
    required_css = (
        "@media print",
        ":focus-visible",
        "@media(max-width:700px)",
        "mobile-ledger",
        "overflow-x:hidden",
        "@media(prefers-reduced-motion:reduce)",
    )
    issues.extend(
        f"missing_css:{token}"
        for token in required_css
        if token not in html
    )
    if thesis and summary and _normalized_claim(thesis) == _normalized_claim(summary):
        issues.append("duplicate_thesis_and_a_x_b")
    return list(dict.fromkeys(issues))


def _attach_report_gates(case: Dict[str, Any]) -> None:
    """Run one bounded quality loop, then attach observable G1-G14 checks."""
    from .core.pipeline import render_analysis_report

    packet = dict(case.get("packet") or {})
    result = dict(case.get("skill_result") or {})
    meta = dict(result.get("meta") or {})
    product_map = list(
        meta.get("product_industry_map")
        or packet.get("product_industry_map")
        or []
    )
    system_a = dict(meta.get("system_a") or {})
    system_b = dict(meta.get("system_b") or {})
    combined = dict(meta.get("combined_conclusion") or {})
    trace = dict(meta.get("reasoning_trace") or {})
    evidence = list(meta.get("evidence") or packet.get("evidence") or [])
    company_branch = (
        bool(meta.get("company_branch"))
        if "company_branch" in meta
        else bool(
            meta.get("system_b_ready")
            or product_map
            or system_b.get("business_exposure")
        )
    )
    required_ids = [
        "report-header",
        "industry-thesis",
        "chain-map",
        "system-a",
        "prosperity-dashboard",
        "inflection-dashboard",
        "industry-signals",
        "risks",
        "evidence-ledger",
    ]
    if company_branch:
        required_ids.extend(
            ["system-b", "valuation-drivers", "combined-conclusion"]
        )
    html = render_analysis_report(packet, result)
    issues_before = _report_quality_issues(html, result, required_ids)
    refinement_attempts = 0
    if "duplicate_thesis_and_a_x_b" in issues_before:
        refined = deepcopy(result)
        refined_meta = dict(refined.get("meta") or {})
        refined_combined = dict(refined_meta.get("combined_conclusion") or {})
        refined_combined["short_status"] = (
            f"A×B {refined_combined.get('status') or '待验证'} · "
            f"readiness {refined_meta.get('readiness') or 'unknown'}"
        )
        refined_meta["combined_conclusion"] = refined_combined
        refined["meta"] = refined_meta
        result = refined
        meta = refined_meta
        combined = refined_combined
        html = render_analysis_report(packet, result)
        refinement_attempts = 1
    issues_after = _report_quality_issues(html, result, required_ids)
    report_quality = {
        "content_map_checked": True,
        "quality_check_attempts": 1,
        "refinement_attempts": refinement_attempts,
        "max_refinement_attempts": 1,
        "issues_before": issues_before,
        "issues_after": issues_after,
        "unresolved": issues_after,
    }
    meta["report_quality"] = report_quality
    result["meta"] = meta
    case["skill_result"] = result
    id_counts = {
        item: len(re.findall(rf'\bid="{re.escape(item)}"', html))
        for item in required_ids
    }
    forbidden_ids = [] if company_branch else [
        "system-b", "valuation-drivers", "combined-conclusion",
    ]
    forbidden_id_counts = {
        item: len(re.findall(rf'\bid="{re.escape(item)}"', html))
        for item in forbidden_ids
    }
    map_required = {
        "product", "industry_unit", "company_position", "direct_customer",
        "downstream_system", "end_demand", "status",
    }
    complete_map = bool(product_map) and all(
        map_required.issubset(item)
        and all(item.get(field) not in (None, "") for field in map_required)
        for item in product_map
        if isinstance(item, Mapping)
    )
    evidence_complete = all(
        isinstance(item, Mapping)
        and item.get("field_path")
        and (item.get("report_period") or item.get("as_of_date"))
        and (item.get("source_level") or item.get("source_type"))
        for item in evidence
    )
    system_a_complete = all(
        key in system_a for key in ("prosperity", "inflection", "lifecycle")
    )
    admitted_paths = [
        str(item.get("field_path") or "")
        for item in trace.get("nodes") or []
        if item.get("admission_status") == "admitted"
    ]
    company_leak = any(path.startswith("company_signals.") for path in admitted_paths)
    th_counts = [
        len(re.findall(r"<th\b", block))
        for block in re.findall(r"<thead\b.*?</thead>", html, flags=re.DOTALL)
    ]
    claim_ids = re.findall(r'data-claim-id="([^"]+)"', html)
    thesis_value = (
        combined.get("short_status")
        or system_b.get("core_contradiction")
        or ""
    )
    semantic_duplicate = bool(
        thesis_value
        and combined.get("summary")
        and _normalized_claim(thesis_value)
        == _normalized_claim(combined.get("summary"))
    )
    gates = [
        _assertion(
            "G1_route_and_period",
            bool((packet.get("target") or {}).get("stock_code") and packet.get("as_of_date")),
            {
                "target": (packet.get("target") or {}).get("stock_code"),
                "as_of_date": packet.get("as_of_date"),
            },
        ),
        _assertion(
            "G2_product_industry_boundary",
            complete_map or not product_map,
            "complete" if complete_map else "explicit_gap",
        ),
        _assertion(
            "G3_bounded_collection_scope",
            bool(meta.get("collection_plan") or packet.get("collection_plan")),
            bool(meta.get("collection_plan") or packet.get("collection_plan")),
        ),
        _assertion(
            "G4_data_route",
            bool(evidence) or not meta.get("usable_for_system_a"),
            {"evidence": len(evidence), "readiness": meta.get("readiness")},
        ),
        _assertion(
            "G5_evidence_quality",
            evidence_complete or not meta.get("usable_for_system_a"),
            {"records": len(evidence), "complete": evidence_complete},
        ),
        _assertion(
            "G6_system_a_separation",
            system_a_complete,
            list(system_a),
        ),
        _assertion(
            "G7_scope_firewall",
            not company_leak,
            admitted_paths,
        ),
        _assertion(
            "G8_system_b_boundary",
            (
                (not company_branch and not system_b)
                or (
                    company_branch
                    and all(
                        key in system_b
                        for key in (
                            "business_exposure", "revenue_driver",
                            "profit_driver", "valuation_driver",
                        )
                    )
                )
            ),
            list(system_b),
        ),
        _assertion(
            "G9_a_x_b",
            (
                not company_branch and not combined
            ) or (
                company_branch
                and bool(combined.get("summary"))
                and bool(combined.get("next_confirmation"))
                and bool(combined.get("invalidation"))
            ),
            combined.get("status"),
        ),
        _assertion(
            "G10_html_contract",
            all(count == 1 for count in id_counts.values())
            and all(count == 0 for count in forbidden_id_counts.values())
            and "<title>" in html
            and 'name="viewport"' in html
            and "<script src=" not in html
            and "<link " not in html,
            {"required": id_counts, "forbidden": forbidden_id_counts},
        ),
        _assertion(
            "G11_desktop_print",
            (not th_counts or max(th_counts) <= 5)
            and "@media print" in html
            and ":focus-visible" in html,
            {"table_columns": th_counts, "print": "@media print" in html},
        ),
        _assertion(
            "G12_content_ownership",
            len(claim_ids) == len(set(claim_ids)) and not semantic_duplicate,
            {"claim_ids": claim_ids, "semantic_duplicate": semantic_duplicate},
        ),
        _assertion(
            "G13_mobile_390",
            "@media(max-width:700px)" in html
            and "mobile-ledger" in html
            and "overflow-x:hidden" in html,
            {
                "mobile_cards": "mobile-ledger" in html,
                "overflow_guard": "overflow-x:hidden" in html,
            },
        ),
        _assertion(
            "G14_bounded_refinement",
            report_quality["content_map_checked"]
            and report_quality["quality_check_attempts"] == 1
            and report_quality["refinement_attempts"] <= 1
            and not report_quality["unresolved"]
            and "@media(prefers-reduced-motion:reduce)" in html,
            report_quality,
        ),
    ]
    case["report_gates"] = gates
    case["assertions"] = list(case.get("assertions") or []) + gates
    case["status"] = (
        "passed"
        if all(item.get("passed") for item in case["assertions"])
        else "failed"
    )
    case["_report_html"] = html


def build_fixture_packet(
    fixture_name: str,
    target: str = "300782",
    reference_date: str = REFERENCE_DATE,
) -> Dict[str, Any]:
    from .planning import build_execution_plan

    route_evidence = _fixture_route_evidence(target)
    plan = build_execution_plan(
        target,
        {"route_evidence": route_evidence},
        reference_date=reference_date,
    )
    planned_target = dict(plan.get("target") or {})
    base = {
        "schema_version": "industry-data/0.2",
        "target": {
            "stock_code": planned_target.get("stock_code") or str(target),
            "stock_name": planned_target.get("stock_name") or str(target),
            "industry": planned_target.get("industry") or "",
            "sub_sector": planned_target.get("sub_sector") or "",
            "preset": planned_target.get("preset") or "generic",
            "input_type": "stock_code",
        },
        "industry_signals": {},
        "peer_basket_signals": {},
        "peer_basket_meta": {},
        "company_signals": _complete_company_signals(),
        "product_industry_map": [
            {
                "product": "射频前端芯片",
                "material_or_technology": "RF CMOS / SOI",
                "form_and_function": "移动终端射频信号的开关、接收与调谐",
                "industry_unit": "射频前端模拟芯片",
                "company_position": "Fabless 芯片设计",
                "direct_customer": "终端品牌、ODM 与模组厂",
                "downstream_system": "移动终端射频前端",
                "end_demand": "智能手机与物联网终端",
                "status": "批量",
                "mapping_evidence": ["offline-product-map-1"],
            }
        ],
        "valuation_context": {
            "revenue_driver": "射频前端新品放量与国产替代",
            "profit_driver": "高集成度产品结构与毛利兑现",
            "valuation_driver": "射频前端国产替代与品类扩张",
            "next_confirmation": "下一报告期新品收入、毛利和客户扩散",
        },
        "market_context": {
            "status": "offline_harness",
            "usage": "market_context_only",
        },
        "evidence": [],
        "needs_data": [],
        "as_of_date": reference_date,
        "source_mode": "offline_harness",
        "routing": dict(plan.get("route") or {}),
        "route_evidence": list(plan.get("route_evidence") or []),
        "route_evidence_rejections": list(plan.get("route_evidence_rejections") or []),
        "profile_version": dict(plan.get("methodology_profile") or {}).get("version") or "",
        "profile_id": dict(plan.get("methodology_profile") or {}).get("profile_id") or "",
        "collection_plan": plan,
    }
    if fixture_name == "framework_only":
        base["company_signals"] = {}
        base["needs_data"] = [
            {"field_path": "industry_signals", "reason": "offline framework fixture"}
        ]
        base["framework_only"] = True
        return base

    if fixture_name == "peer_proxy_ready":
        peer_signals = {
            "revenue_growth_median": 28.0,
            "gross_margin_median": 35.0,
            "contract_liability_growth_median": 22.0,
        }
        members = [
            {"stock_code": "PEER001.SZ", "stock_name": "离线同业一"},
            {"stock_code": "PEER002.SH", "stock_name": "离线同业二"},
            {"stock_code": "PEER003.SZ", "stock_name": "离线同业三"},
        ]
        base["peer_basket_signals"] = peer_signals
        base["peer_basket_meta"] = {
            "members": members,
            "sample_size": 3,
            "report_period": "2026-03-31",
            "previous_report_period": "2025-03-31",
            "aggregation_method": "median",
            "coverage_ratio": 1.0,
            "agreement_ratio_by_field": {key: 1.0 for key in peer_signals},
            "direction_by_field": {key: "improving" for key in peer_signals},
        }
        base["evidence"] = [
            {
                "field_path": f"peer_basket_signals.{field}",
                "scope": "peer_basket",
                "source_level": "L1",
                "source_type": "financial_report",
                "source_title": "offline_harness 同业财报",
                "member_stock_code": member["stock_code"],
                "member_stock_name": member["stock_name"],
                "report_period": "2026-03-31",
                "previous_report_period": "2025-03-31",
                "as_of_date": reference_date,
                "raw_fields": [f"{field}.current", f"{field}.previous"],
                "raw_values": {f"{field}.current": peer_signals[field], f"{field}.previous": 0.0},
                "derivation_method": "offline_harness 同口径同比派生",
                "aggregation_method": "median",
                "environment": "offline_harness",
            }
            for field in peer_signals
            for member in members
        ]
        return base

    if fixture_name == "industry_ready":
        direct = {
            "industry_market_growth": 24.0,
            "industry_order_growth": 18.0,
            "industry_capacity_utilization": 87.0,
            "industry_price_yoy": 6.0,
        }
        base["industry_signals"] = direct
        base["evidence"] = [
            {
                "field_path": f"industry_signals.{field}",
                "scope": "industry",
                "source_level": "L2",
                "source_type": "research_report",
                "source_title": "offline_harness 行业跟踪资料",
                "as_of_date": reference_date,
                "report_period": "2026-03-31",
                "previous_report_period": "2025-03-31",
                "raw_fields": [f"{field}.current", f"{field}.previous"],
                "raw_values": {
                    f"{field}.current": direct[field],
                    f"{field}.previous": {
                        "industry_market_growth": 10.0,
                        "industry_order_growth": 5.0,
                        "industry_capacity_utilization": 80.0,
                        "industry_price_yoy": 1.0,
                    }[field],
                },
                "derivation_method": "offline_harness 同口径跨期行业比较",
                "environment": "offline_harness",
            }
            for field in direct
        ]
        return base
    raise ValueError(f"unknown fixture: {fixture_name}")


def _fixture_route_evidence(target: str) -> List[Dict[str, Any]]:
    """Load only source facts needed to exercise target-specific routing."""
    from .core.auto_detect_preset import resolve_stock_identity

    code, _ = resolve_stock_identity(str(target))
    path = Path(__file__).resolve().parents[3] / "data_sources" / "industrial_sentinel_route_evidence.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if payload.get("schema_version") != "industry-route-evidence/0.1":
        return []
    return [
        dict(item)
        for item in payload.get("records") or []
        if isinstance(item, Mapping)
        and str(item.get("stock_code") or "").upper() == str(code).upper()
    ]


def _complete_company_signals() -> Dict[str, Any]:
    return {
        "revenue_growth": 32.0,
        "gross_margin": 42.0,
        "rd_ratio": 12.0,
        "fixed_asset": 1_000_000_000,
        "total_asset": 5_000_000_000,
        "asset_lightness": 0.8,
        "net_profit_parent": 500_000_000,
        "profit_stability": 0.76,
        "roe": 0.12,
        "debt_ratio": 0.35,
    }


def render_harness_html(report: Mapping[str, Any]) -> str:
    cases_html = "".join(_render_case(case) for case in report.get("cases") or [])
    live_smoke_html = _render_live_smoke(report.get("live_smoke") or {})
    status_class = "ok" if report.get("status") == "passed" else "bad"
    case_nav = "".join(
        f'<a href="#case-{escape(str(case.get("fixture")))}">{escape(str(case.get("fixture")))}</a>'
        for case in report.get("cases") or []
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Industrial Sentinel · 行业推理审计报告</title>
<style>
*{{box-sizing:border-box}} :root{{--ink:#14243a;--muted:#68798e;--paper:#f4f7fb;--panel:#fff;--line:#d9e2ed;--blue:#175cd3;--teal:#087f8c;--green:#16845b;--amber:#b66a08;--red:#c43e4f;--wash:#eaf2ff;--mono:"SFMono-Regular",Consolas,"Liberation Mono",monospace}}
html{{scroll-behavior:smooth}} body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:1440px;margin:0 auto;padding:28px 36px 72px}} h1,h2,h3,h4,p{{margin-top:0}} h1{{font-size:clamp(30px,4vw,54px);line-height:1.04;letter-spacing:-.045em;margin:12px 0}} h2{{font-size:25px;letter-spacing:-.02em}} h3{{font-size:15px}} .muted{{color:var(--muted)}}
.masthead{{position:relative;overflow:hidden;background:linear-gradient(120deg,#102a4c 0%,#164d73 58%,#0b727c 100%);color:#fff;border-radius:24px;padding:32px 36px;box-shadow:0 18px 45px rgba(20,57,91,.18)}}
.masthead:after{{content:"";position:absolute;right:-70px;top:-110px;width:360px;height:360px;border:56px solid rgba(255,255,255,.08);border-radius:50%}} .masthead>*{{position:relative;z-index:1}} .masthead .muted{{color:#c9d9e9}} .eyebrow,.kicker{{font:700 11px/1.2 var(--mono);letter-spacing:.13em;text-transform:uppercase}}
.runline{{display:flex;flex-wrap:wrap;gap:18px;margin-top:22px;font-family:var(--mono);font-size:12px}} .runline span{{padding-right:18px;border-right:1px solid rgba(255,255,255,.24)}}
.nav{{position:sticky;top:0;z-index:20;display:flex;gap:7px;align-items:center;margin:16px 0 22px;padding:9px;background:rgba(244,247,251,.9);backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:14px}} .nav a{{color:#36506c;text-decoration:none;padding:7px 11px;border-radius:9px;font:650 12px var(--mono)}} .nav a:hover,.nav a:focus-visible{{background:var(--wash);color:var(--blue);outline:none}}
.case{{background:var(--panel);border:1px solid var(--line);border-radius:20px;margin:22px 0;box-shadow:0 8px 26px rgba(38,68,98,.07);overflow:hidden;scroll-margin-top:72px}}
.case-head{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;padding:26px 28px;border-bottom:1px solid var(--line);background:linear-gradient(90deg,#fff,#f7faff)}} .case-title{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}} .case-title h2{{margin:0}} .verdict{{text-align:right}} .verdict strong{{display:block;font-size:26px;letter-spacing:-.04em}}
.section{{padding:24px 28px;border-bottom:1px solid var(--line)}} .section:last-child{{border-bottom:0}} .section-head{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:15px}} .section-head h3{{font-size:18px;margin:0}} .section-head p{{margin:0;max-width:700px;text-align:right}}
.pill,.tag{{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 9px;font:700 11px var(--mono);background:#e9eef5;color:#4b5f74}} .tag.ok,.pill.ok{{background:#e2f5ec;color:#0d7049}} .tag.warn,.pill.warn{{background:#fff0d8;color:#915307}} .tag.bad,.pill.bad{{background:#fee8eb;color:#a82d3e}} .tag.info{{background:#e5efff;color:#1455b8}}
.ok{{color:var(--green)}} .warn{{color:var(--amber)}} .bad{{color:var(--red)}}
.rail{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:0}} .rail-step{{position:relative;padding:14px 14px 14px 18px;background:#f6f9fc;border:1px solid var(--line);border-right:0;min-height:108px}} .rail-step:first-child{{border-radius:12px 0 0 12px}} .rail-step:last-child{{border-right:1px solid var(--line);border-radius:0 12px 12px 0}} .rail-step:not(:last-child):after{{content:"";position:absolute;right:-6px;top:48px;width:10px;height:10px;background:#f6f9fc;border-top:1px solid var(--line);border-right:1px solid var(--line);transform:rotate(45deg);z-index:2}} .rail-step b{{display:block;margin:8px 0 3px;font-size:14px}} .rail-step small{{color:var(--muted)}}
.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}} .metric{{border:1px solid var(--line);border-top:4px solid var(--blue);border-radius:12px;padding:16px;background:#fff}} .metric:nth-child(2){{border-top-color:var(--teal)}} .metric:nth-child(3){{border-top-color:var(--amber)}} .metric strong{{display:block;font-size:24px;margin:7px 0}} .metric small{{color:var(--muted)}}
.gate-grid{{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.6fr);gap:18px}} .gate{{border:1px solid var(--line);border-radius:12px;padding:16px;background:#f8fafc}} .check-list{{list-style:none;margin:10px 0 0;padding:0}} .check-list li{{display:flex;gap:9px;padding:6px 0;border-bottom:1px dashed var(--line)}} .check-list li:last-child{{border:0}}
.role-strip{{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:14px}} .role{{padding:12px;border:1px solid var(--line);border-radius:10px;background:#f8fafc}} .role b{{display:block;margin-bottom:5px}} .votes{{display:flex;gap:9px;font:12px var(--mono)}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:12px}} table{{width:100%;border-collapse:collapse;min-width:880px}} th{{position:sticky;top:0;background:#edf3f9;color:#53677e;font:700 11px var(--mono);letter-spacing:.04em}} th,td{{border-bottom:1px solid var(--line);padding:10px 11px;text-align:left;vertical-align:top}} tbody tr:last-child td{{border-bottom:0}} tbody tr:hover{{background:#f8fbff}} td code{{font:11px var(--mono);color:#36506c}} .raw{{font:11px/1.5 var(--mono);white-space:nowrap}} .reason{{max-width:310px;color:var(--muted)}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .info-card{{border:1px solid var(--line);border-radius:12px;padding:16px}} .info-card h4{{font-size:14px;margin-bottom:10px}} .kv{{display:grid;grid-template-columns:130px 1fr;gap:7px 12px}} .kv dt{{color:var(--muted)}} .kv dd{{margin:0;font-family:var(--mono);word-break:break-word}}
.gaps{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:9px}} .gap{{padding:12px;border-left:4px solid var(--amber);background:#fff8eb;border-radius:8px}} .gap code{{display:block;font:11px var(--mono);margin-bottom:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
details{{border:1px solid var(--line);border-radius:10px;margin-top:9px;background:#fbfcfe}} summary{{cursor:pointer;padding:12px 14px;font-weight:700}} pre{{margin:0;white-space:pre-wrap;word-break:break-word;background:#0f2136;color:#d9e6f2;padding:15px;max-height:440px;overflow:auto;font:11px/1.55 var(--mono)}}
.smoke{{background:#fff;border:1px solid var(--line);border-radius:18px;padding:22px 26px;margin-top:22px}} .assertions table{{min-width:640px}}
@media(max-width:1000px){{.rail{{grid-template-columns:repeat(3,1fr);gap:8px}} .rail-step,.rail-step:first-child,.rail-step:last-child{{border:1px solid var(--line);border-radius:10px}} .rail-step:after{{display:none}} .gate-grid,.two-col{{grid-template-columns:1fr}}}}
@media(max-width:680px){{.wrap{{padding:16px 12px 48px}} .masthead{{padding:25px 21px;border-radius:18px}} .case-head{{grid-template-columns:1fr;padding:20px}} .verdict{{text-align:left}} .section{{padding:20px}} .section-head{{display:block}} .section-head p{{text-align:left;margin-top:5px}} .rail{{grid-template-columns:1fr}} .metrics,.role-strip{{grid-template-columns:1fr 1fr}} .nav{{overflow:auto}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><main class="wrap">
<header class="masthead"><div class="eyebrow">Industry group · reasoning audit</div><h1>行业判断不是一句结论，<br>而是一条可复核的证据链。</h1>
<p class="muted">从数据准入、同行聚合与中观方法论，到真实 IndustryAgent、AgentScope、Orchestrator 和仲裁风控。本报告把每一步为何成立、为何降级完整展开。</p>
<div class="runline"><span>STATUS <b class="{status_class}">{escape(str(report.get('status')))}</b></span><span>MODE offline_harness</span><span>STOCK {escape(str(report.get('stock_code')))}</span><span>ANCHOR {escape(str(report.get('reference_date')))}</span><span>RUN {escape(str(report.get('run_id')))}</span><span><a href="./{escape(str(report.get('run_id')))}.json" style="color:#fff">完整 JSON ↗</a></span></div></header>
<nav class="nav"><span class="pill warn">fixture ≠ live</span>{case_nav}<a href="#live-smoke">7 Agent smoke</a></nav>
	{cases_html}
	{live_smoke_html}
	</main></body></html>"""


def _normalize_live_smoke(value: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not value:
        return {
            "status": "not_run",
            "blocking": False,
            "note": "完整 7 Agent live smoke 尚未附加；它是第二层非阻塞检查。",
        }
    result = dict(value)
    result.setdefault("blocking", False)
    result.setdefault("environment", "live")
    return result


def _render_live_smoke(smoke: Mapping[str, Any]) -> str:
    status = str(smoke.get("status") or "not_run")
    status_class = "ok" if status in {"passed", "completed"} and not smoke.get("timeouts") else "warn"
    return f"""<section class="smoke" id="live-smoke"><h2>完整 7 Agent live smoke · <span class="{status_class}">{escape(status)}</span></h2>
<p><span class="pill">live / non-blocking</span> 本区块与 offline fixture 分离，不参与行业组 Harness 退出码。</p>
<div class="grid"><div><h3>Scope trace</h3><p>registered {escape(str(smoke.get('registered', '—')))} / success {escape(str(smoke.get('success', '—')))} / failed {escape(str(smoke.get('failed', '—')))} / timeout {escape(str(smoke.get('timeouts', '—')))} / invalid {escape(str(smoke.get('invalid', '—')))}</p></div>
<div><h3>行业 Agent</h3><p>{escape(str(smoke.get('industry_signal', '—')))}</p></div>
<div><h3>最终仲裁</h3><p>{escape(str(smoke.get('arbitration', '—')))}</p></div>
<div><h3>外部依赖/其他专家</h3><p>{escape(str(smoke.get('note', '—')))}</p></div></div>
<details><summary>Live smoke 摘要</summary><pre>{escape(json.dumps(smoke, ensure_ascii=False, indent=2, default=str))}</pre></details></section>"""


def _render_case(case: Mapping[str, Any]) -> str:
    packet = dict(case.get("packet") or {})
    target = dict(packet.get("target") or {})
    peer_meta = dict(packet.get("peer_basket_meta") or {})
    skill_result = dict(case.get("skill_result") or {})
    signal = dict(case.get("industry_signal") or {})
    meta = dict(signal.get("meta") or {})
    arbitration = dict(case.get("arbitration_result") or {})
    trace = dict(meta.get("reasoning_trace") or {})
    plan = dict(meta.get("collection_plan") or {})
    routing = dict(meta.get("routing") or {})
    scope = dict(arbitration.get("scope_trace") or {})
    readiness = str(meta.get("readiness") or "unknown")
    direction = str(signal.get("direction") or "neutral")
    status_tone = "ok" if case.get("status") == "passed" else "bad"
    signal_tone = "ok" if direction == "bullish" else "bad" if direction == "bearish" else "warn"
    confidence = _format_percent(signal.get("confidence"))
    return f"""<article class="case" id="case-{escape(str(case.get('fixture')))}">
<header class="case-head"><div><div class="kicker">Scenario · {escape(str(case.get('fixture')))}</div><div class="case-title"><h2>{escape(str(target.get('stock_name') or target.get('stock_code')))}</h2><span class="tag {status_tone}">{escape(str(case.get('status')))}</span><span class="tag info">{escape(readiness)}</span></div><p class="muted">{escape(str(routing.get('target_peer_group_name') or '同行组未解析'))} · {escape(str(routing.get('peer_scope_mode') or '—'))} scope · {escape(str(packet.get('source_mode') or 'unknown'))}</p></div>
<div class="verdict"><span class="kicker">Industry Signal</span><strong class="{signal_tone}">{escape(direction)} · {confidence}</strong><small>weight {escape(str(signal.get('weight')))} · 仲裁 {escape(str(arbitration.get('decision')))}</small></div></header>
<section class="section"><div class="section-head"><h3>从输入到仲裁</h3><p class="muted">这条链路中的结果均来自真实 Skill、IndustryAgent、AgentScope 与仲裁引擎。</p></div>{_render_decision_rail(case, target, meta, arbitration)}</section>
<section class="section"><div class="section-head"><h3>三个必须分开的行业判断</h3><p class="muted">短期同行财务可确认周期与拐点，但不能替代长期渗透率对结构生命周期的判断。</p></div>{_render_conclusions(meta)}</section>
<section class="section"><div class="section-head"><h3>System A 最小决策集</h3><p class="muted">先检查晴雨表与独立中轴是否齐全，再允许状态规则投票。</p></div>{_render_admission_gate(trace, routing, peer_meta)}</section>
<section class="section"><div class="section-head"><h3>中观推理 · Reasoning Trace</h3><p class="muted">每条 evidence 单独展示 raw 比较、准入结果与对最终状态的贡献。</p></div>{_render_role_summary(trace)}{_render_evidence_ledger(trace)}</section>
<section class="section"><div class="section-head"><h3>数据缺口与 CollectionPlan</h3><p class="muted">required_tasks / optional_tasks 只定义待采集事实，不提前生成结论。</p></div>{_render_gaps(meta)}{_render_collection_plan(plan)}</section>
<section class="section"><div class="section-head"><h3>AgentScope 与仲裁解释</h3><p class="muted">方向判断与交易动作分离：单一专家方向有效，仍会因覆盖不足触发 hold。</p></div>{_render_arbitration(arbitration, scope)}</section>
<section class="section assertions"><div class="section-head"><h3>分阶段断言</h3><p class="muted">Harness 对数据、Skill、Agent、消息桥和仲裁逐段验收。</p></div>{_render_assertions(case.get('assertions') or [])}</section>
<section class="section">{_render_technical_appendix(packet, skill_result, signal, arbitration)}</section></article>"""


def _render_decision_rail(
    case: Mapping[str, Any],
    target: Mapping[str, Any],
    meta: Mapping[str, Any],
    arbitration: Mapping[str, Any],
) -> str:
    scope_summary = dict((arbitration.get("scope_trace") or {}).get("summary") or {})
    consumed = int((arbitration.get("signals_summary") or {}).get("total") or 0)
    skill_result = dict(case.get("skill_result") or {})
    industry_signal = dict(case.get("industry_signal") or {})
    steps = [
        ("01 · 输入", f"{target.get('stock_code')} · {target.get('stock_name')}", f"preset {target.get('preset')}"),
        ("02 · 数据准入", str(meta.get("readiness")), str(meta.get("analysis_basis"))),
        ("03 · Skill", str(skill_result.get("direction")), _format_percent(skill_result.get("confidence"))),
        ("04 · IndustryAgent", str(industry_signal.get("direction")), "标准 Signal"),
        ("05 · AgentScope", f"success {scope_summary.get('success_count', 0)}", f"failed {scope_summary.get('failed_count', 0)} · timeout {scope_summary.get('timeout_count', 0)}"),
        ("06 · 仲裁", str(arbitration.get("decision")), f"{arbitration.get('direction')} · consumed {consumed}"),
    ]
    return '<div class="rail">' + "".join(
        f'<div class="rail-step"><span class="kicker">{escape(label)}</span><b>{escape(value)}</b><small>{escape(note)}</small></div>'
        for label, value, note in steps
    ) + "</div>"


def _render_conclusions(meta: Mapping[str, Any]) -> str:
    items = [
        ("结构性生命周期", meta.get("structural_lifecycle") or {}, "长期渗透率与产业结构"),
        ("周期景气阶段", meta.get("cyclical_phase") or {}, "晴雨表 + 中轴确认"),
        ("拐点状态", meta.get("inflection_state") or {}, "跨期领先代理 + 独立确认"),
    ]
    return '<div class="metrics">' + "".join(
        f'<div class="metric"><span class="kicker">{escape(title)}</span><strong>{escape(str(value.get("label") or "未判定"))}</strong><small>{escape(note)} · evidence {len(value.get("evidence_refs") or [])}</small></div>'
        for title, value, note in items
    ) + "</div>"


def _render_admission_gate(
    trace: Mapping[str, Any],
    routing: Mapping[str, Any],
    peer_meta: Mapping[str, Any],
) -> str:
    gate = dict(trace.get("profile_admission") or {})
    required_ids = list(gate.get("required_indicator_ids") or [])
    observed_ids = set(gate.get("observed_indicator_ids") or [])
    required_roles = list(gate.get("required_roles") or [])
    observed_roles = set(gate.get("observed_roles") or [])
    checks = [(item, item in observed_ids) for item in required_ids] + [(f"role:{item}", item in observed_roles) for item in required_roles]
    if not checks:
        checks = [("System A 暂无可执行最小集", False)]
    check_html = "".join(
        f'<li><span class="tag {"ok" if passed else "warn"}">{"PASS" if passed else "MISS"}</span><code>{escape(str(label))}</code></li>'
        for label, passed in checks
    )
    meta_rows = [
        ("目标同行组", routing.get("target_peer_group_name") or routing.get("target_peer_group")),
        ("证据范围", routing.get("evidence_scope_name") or routing.get("evidence_scope")),
        ("样本 / 覆盖", f"{peer_meta.get('sample_size', '—')} / {peer_meta.get('coverage_ratio', '—')}"),
        ("报告期", f"{peer_meta.get('previous_report_period', '—')} → {peer_meta.get('report_period', '—')}"),
        ("聚合方法", peer_meta.get("aggregation_method") or "—"),
    ]
    return f'<div class="gate-grid"><div class="gate"><span class="tag {"ok" if gate.get("passed") else "warn"}">{"ADMITTED" if gate.get("passed") else "NOT ADMITTED"}</span><h4>{escape(str(gate.get("readiness") or "unknown"))}</h4><p class="muted">{escape(str(gate.get("analysis_basis") or "—"))}</p><ul class="check-list">{check_html}</ul></div><div class="info-card"><h4>可比性与路由范围</h4><dl class="kv">' + "".join(f"<dt>{escape(str(k))}</dt><dd>{escape(str(v))}</dd>" for k, v in meta_rows) + "</dl></div></div>"


def _render_role_summary(trace: Mapping[str, Any]) -> str:
    summary = dict(trace.get("summary") or {})
    labels = (("barometer", "晴雨表"), ("mid_axis", "中轴确认"), ("ebb_warning", "退潮预警"), ("structural", "结构生命周期"))
    return '<div class="role-strip">' + "".join(
        f'<div class="role"><b>{label}</b><div class="votes"><span class="ok">↑ {int((summary.get(key) or {}).get("improving") or 0)}</span><span class="bad">↓ {int((summary.get(key) or {}).get("deteriorating") or 0)}</span><span class="muted">— {int((summary.get(key) or {}).get("neutral") or 0)}</span></div></div>'
        for key, label in labels
    ) + "</div>"


def _render_evidence_ledger(trace: Mapping[str, Any]) -> str:
    rows = []
    for node in trace.get("nodes") or []:
        comparison = dict(node.get("comparison_result") or {})
        status = str(node.get("admission_status") or "unknown")
        tone = "ok" if status == "admitted" else "bad" if status == "rejected" else "warn"
        observation = str(node.get("observation") or "unknown")
        obs_tone = "ok" if observation == "improving" else "bad" if observation == "deteriorating" else "muted"
        raw = f"{_format_number(comparison.get('previous'))} → {_format_number(comparison.get('current'))} (Δ {_format_number(comparison.get('delta'))})" if comparison else "—"
        if comparison.get("aggregate_direction"):
            raw += f" | member {comparison.get('member_direction')} / aggregate {comparison.get('aggregate_direction')}"
        identity = node.get("member_stock_code") or node.get("source_type") or "—"
        source = " · ".join(str(item) for item in (node.get("source_level"), node.get("source_title")) if item) or "—"
        reason = node.get("rejection_reason") or node.get("derivation_method") or "—"
        previous_period = node.get("previous_report_period") or "—"
        report_period = node.get("report_period") or "—"
        rows.append(f'<tr><td><b>{escape(str(node.get("role_name") or node.get("role")))}</b><br><code>{escape(str(node.get("indicator_id")))}</code><br><span class="muted">{escape(str(identity))} · {escape(str(node.get("field_path")))}</span></td><td class="raw">{escape(raw)}<br><span class="{obs_tone}">{escape(observation)}</span> · <span class="tag {tone}">{escape(status)}</span></td><td>{escape(str(previous_period))}<br>→ {escape(str(report_period))}</td><td>{escape(source)}</td><td class="reason">{escape(str(reason))}<br><span class="muted">cross-period {escape(str(bool(node.get("cross_period"))).lower())}</span></td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>角色 / 指标 / 样本</th><th>Raw comparison / 准入</th><th>报告期</th><th>来源</th><th>派生或拒绝原因</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"


def _render_gaps(meta: Mapping[str, Any]) -> str:
    items = list(meta.get("needs_data_items") or [])
    uncertainties = list(meta.get("uncertainties") or [])
    gaps_html = '<p><span class="tag ok">NO BLOCKING GAP</span></p>' if not items else '<div class="gaps">' + "".join(
        f'<div class="gap"><code>{escape(str(item.get("field_path") or item.get("task_id") or "unknown"))}</code>{escape(str(item.get("reason") or "待回填"))}</div>'
        for item in items
    ) + "</div>"
    uncertainty_html = "".join(f"<li>{escape(str(item))}</li>" for item in uncertainties) or "<li>无额外不确定性</li>"
    return gaps_html + f'<details><summary>推理不确定性 · {len(uncertainties)}</summary><ul class="check-list" style="padding:0 14px 12px">{uncertainty_html}</ul></details>'


def _render_collection_plan(plan: Mapping[str, Any]) -> str:
    tasks = [("required", task) for task in plan.get("required_tasks") or []] + [("optional", task) for task in plan.get("optional_tasks") or []]
    rows = "".join(
        f'<tr><td><span class="tag {"warn" if kind == "required" else "info"}">{kind}</span></td><td><code>{escape(str(task.get("task_id")))}</code><br>{escape(str(task.get("field_path")))}</td><td>{escape(str(task.get("comparison")))}</td><td>{escape(str(task.get("report_period")))}<br><span class="muted">vs {escape(str(task.get("comparison_report_period")))}</span></td><td>{escape(", ".join(str(item) for item in task.get("source_levels") or []))}</td></tr>'
        for kind, task in tasks
    )
    preflight = dict(plan.get("preflight") or {})
    return f'<p><span class="tag {"ok" if preflight.get("status") == "passed" else "bad"}">PREFLIGHT {escape(str(preflight.get("status") or "unknown"))}</span> <span class="muted">reference {escape(str(plan.get("reference_date") or "—"))} · {len(tasks)} bounded tasks</span></p><div class="table-wrap"><table><thead><tr><th>优先级</th><th>任务 / 回填路径</th><th>比较口径</th><th>报告期</th><th>来源等级</th></tr></thead><tbody>{rows}</tbody></table></div>'


def _render_arbitration(arbitration: Mapping[str, Any], scope: Mapping[str, Any]) -> str:
    summary = dict(scope.get("summary") or {})
    risks = list(arbitration.get("risks") or [])
    risk_html = "".join(f"<li>{escape(str(risk))}</li>" for risk in risks) or "<li>无显式风险</li>"
    facts = [
        ("AgentScope", f"success {summary.get('success_count', 0)} / failed {summary.get('failed_count', 0)} / timeout {summary.get('timeout_count', 0)} / invalid {summary.get('invalid_count', 0)}"),
        ("Signal consumed", (arbitration.get("signals_summary") or {}).get("total", 0)),
        ("仲裁方向", arbitration.get("direction")),
        ("最终动作", arbitration.get("decision")),
        ("真实原因", arbitration.get("reasoning")),
    ]
    return '<div class="two-col"><div class="info-card"><h4>执行与消费</h4><dl class="kv">' + "".join(f"<dt>{escape(str(k))}</dt><dd>{escape(str(v))}</dd>" for k, v in facts) + f'</dl></div><div class="info-card"><h4>风控与不确定性</h4><ul class="check-list">{risk_html}</ul></div></div>'


def _render_assertions(assertions: List[Mapping[str, Any]]) -> str:
    rows = "".join(
        f'<tr><td>{escape(str(item.get("name")))}</td><td><span class="tag {"ok" if item.get("passed") else "bad"}">{"PASS" if item.get("passed") else "FAIL"}</span></td><td>{escape(str(item.get("observed")))}</td></tr>'
        for item in assertions
    )
    return '<div class="table-wrap"><table><thead><tr><th>检查</th><th>结果</th><th>观测值</th></tr></thead><tbody>' + rows + "</tbody></table></div>"


def _render_technical_appendix(
    packet: Mapping[str, Any],
    skill_result: Mapping[str, Any],
    signal: Mapping[str, Any],
    arbitration: Mapping[str, Any],
) -> str:
    packet_view = {
        key: packet.get(key)
        for key in (
            "schema_version", "target", "industry_signals", "peer_basket_signals",
            "peer_basket_meta", "company_signals", "evidence", "needs_data",
            "as_of_date", "fetched_at", "data_hash", "profile_version",
            "provider_status", "source_mode", "cache_origin", "scope_provenance",
        )
    }
    skill_view = {
        key: skill_result.get(key)
        for key in ("direction", "confidence", "weight", "reasoning", "signals", "source", "signal_type")
    }
    signal_view = {
        key: signal.get(key)
        for key in ("direction", "confidence", "weight", "reasoning", "signals", "source", "signal_type", "stock_code")
    }
    signal_meta = dict(signal.get("meta") or {})
    signal_view["meta"] = {
        key: signal_meta.get(key)
        for key in (
            "source_mode", "provider_status", "fetched_at", "data_hash",
            "data_profile_version", "cache_origin", "scope_provenance",
        )
    }
    scope = dict(arbitration.get("scope_trace") or {})
    execution_results = [
        {
            key: item.get(key)
            for key in ("agent_name", "signal_type", "status", "duration_seconds", "error")
        }
        for item in scope.get("execution_results") or []
    ]
    arbitration_view = {
        key: arbitration.get(key)
        for key in (
            "decision", "direction", "confidence", "position_ratio", "reasoning",
            "signals_summary", "risks", "reasoning_chain", "uncertainties",
        )
    }
    arbitration_view["scope_trace"] = {
        key: scope.get(key)
        for key in ("run_id", "framework", "duration_seconds", "summary")
    }
    arbitration_view["scope_trace"]["execution_results"] = execution_results
    items = (
        ("IndustryDataPacket · 事实与 evidence", packet_view),
        ("Skill output · 标准结果", skill_view),
        ("Agent Signal · 消息桥载荷", signal_view),
        ("ArbitrationResult / Scope trace · 精简审计", arbitration_view),
    )
    return '<div class="section-head"><h3>技术附录</h3><p class="muted">页面仅保留关键载荷，完整无损数据见报告顶部同名 JSON。</p></div>' + "".join(
        f'<details><summary>{escape(title)}</summary><pre>{escape(json.dumps(value, ensure_ascii=False, indent=2, default=str))}</pre></details>'
        for title, value in items
    )


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "—"


def _format_number(value: Any) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if hasattr(value, "to_dict"):
        return _serialize(value.to_dict())
    return value


def _atomic_write(path: Path, content: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
