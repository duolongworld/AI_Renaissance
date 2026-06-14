"""Runtime adapter for the company evolution analysis technical skill."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple


def run_company_evolution_analysis(stock_code: str, config: Optional[Dict[str, Any]] = None, cninfo_source_cls: Any = None) -> Dict[str, Any]:
    """Build a Signal-like auxiliary result from injected profile or cninfo disclosures."""
    config = config or {}
    payload = config.get("company_evolution") or config.get("company_profile")
    payload_source = "config:company_evolution" if config.get("company_evolution") else "config:company_profile"
    source = config.get("company_profile_source")
    if payload is None and source is not None:
        payload = _load_company_profile(source, stock_code)
        payload_source = "config:company_profile_source"
    if payload is None and config.get("use_cninfo_company_data", True):
        payload = _load_company_profile_from_cninfo(stock_code, config, cninfo_source_cls)
        payload_source = "data_sources.cninfo"

    if not payload:
        return _neutral_skill_result(
            "公司发展沿革 Skill 已加载；未取得注入画像或 cninfo 公告数据，故仅作为中性背景约束。",
            weight=float(config.get("company_evolution_analysis_weight", 0.10)),
            confidence=0.2,
            meta={
                "skill_name": "company_evolution_analysis",
                "requires_web_search_for_full_report": True,
                "needs_human_review": True,
                "uncertainties": ["未注入公司节点叙事，且未取得 cninfo 公告数据，避免凭空生成公司发展结论。"],
            },
        )

    direction = str(payload.get("direction") or payload.get("technical_bias") or "neutral")
    if direction not in {"bullish", "bearish", "neutral"}:
        direction = "neutral"
    confidence = _clamp(float(payload.get("confidence", 0.35) or 0.35))
    nodes = list(payload.get("nodes") or payload.get("key_nodes") or [])
    catalysts = list(payload.get("catalysts") or payload.get("growth_drivers") or [])
    risks = list(payload.get("risks") or payload.get("risk_notes") or [])
    signals = list(payload.get("signals") or [])
    if not signals:
        if catalysts:
            signals.append("公司节点叙事：存在可验证增长催化，作为技术信号背景加分项")
        if risks:
            signals.append("公司节点叙事：存在可验证发展风险，作为技术信号风险约束")
        if not signals:
            signals.append("公司节点叙事：已注入背景资料，但未形成明确方向约束")

    return {
        "skill_name": "company_evolution_analysis",
        "direction": direction,
        "confidence": confidence,
        "reasoning": str(payload.get("reasoning") or "基于注入的公司发展节点事实形成背景约束。"),
        "signals": signals,
        "weight": float(config.get("company_evolution_analysis_weight", 0.10)),
        "meta": {
            "skill_name": "company_evolution_analysis",
            "nodes": nodes,
            "catalysts": catalysts,
            "risks": risks,
            "current_position": list(payload.get("current_position") or []),
            "future_outlook": list(payload.get("future_outlook") or []),
            "evidence": list(payload.get("evidence") or []),
            "data_source_meta": dict(payload.get("data_source_meta") or {}),
            "source": str(payload.get("source") or payload_source),
            "requires_web_search_for_full_report": bool(payload.get("requires_web_search_for_full_report", True)),
            "needs_human_review": bool(payload.get("needs_human_review", False)),
            "uncertainties": list(payload.get("uncertainties") or []),
        },
    }


def _load_company_profile(source: Any, stock_code: str) -> Dict[str, Any]:
    if callable(source):
        data = source(stock_code)
    elif isinstance(source, dict):
        data = source.get(stock_code) or source.get("default") or source
    elif hasattr(source, "get_company_evolution"):
        data = source.get_company_evolution(stock_code)
    elif hasattr(source, "get_company_profile"):
        data = source.get_company_profile(stock_code)
    else:
        data = {}
    return dict(data or {}) if isinstance(data, dict) else {}


def _load_company_profile_from_cninfo(stock_code: str, config: Dict[str, Any], cninfo_source_cls: Any) -> Dict[str, Any]:
    source = config.get("cninfo_data_source")
    if source is None:
        if cninfo_source_cls is None:
            return {
                "source": "data_sources.cninfo",
                "direction": "neutral",
                "confidence": 0.2,
                "reasoning": "cninfo 数据源模块不可用，无法基于法定公告生成公司发展路径分析。",
                "signals": ["公司节点叙事：cninfo 数据源不可用，保持中性背景约束"],
                "uncertainties": ["data_sources.cninfo 导入失败；请检查 cninfo 数据源依赖。"],
                "requires_web_search_for_full_report": True,
                "needs_human_review": True,
                "data_source_meta": {"provider": "cninfo", "status": "error", "error": "data_sources.cninfo import failed"},
            }
        source = cninfo_source_cls()

    until = str(config.get("cninfo_until") or date.today().isoformat())
    since = str(config.get("cninfo_since") or (date.today() - timedelta(days=int(config.get("cninfo_lookback_days", 730) or 730))).isoformat())
    announcements_result = _call_cninfo_announcements(source, stock_code, since, until)
    announcements = _dedupe_cninfo_announcements(announcements_result.get("announcements") or []) if announcements_result.get("status") == "success" else []
    periodic_reports = _load_cninfo_periodic_reports(source, stock_code, config) if config.get("cninfo_fetch_periodic_report", False) else []
    return _build_company_profile_from_cninfo_announcements(stock_code, since, until, announcements, periodic_reports, announcements_result, config)


def _call_cninfo_announcements(source: Any, stock_code: str, since: str, until: str) -> Dict[str, Any]:
    try:
        if hasattr(source, "get_announcements"):
            return dict(source.get_announcements(stock_code, since=since, until=until, download=False) or {})
        if callable(source):
            data = source(stock_code, since=since, until=until)
            return dict(data or {}) if isinstance(data, dict) else {"status": "success", "announcements": list(data or [])}
    except Exception as exc:
        return {"status": "error", "stock_code": stock_code, "error": f"cninfo 公告调用失败：{type(exc).__name__}: {exc}"}
    return {"status": "error", "stock_code": stock_code, "error": "cninfo 数据源不支持 get_announcements 接口。"}


def _load_cninfo_periodic_reports(source: Any, stock_code: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not hasattr(source, "get_periodic_report"):
        return []
    today = date.today()
    candidates: List[Tuple[int, str]] = [(today.year, "q1"), (today.year - 1, "annual")] if today.month >= 5 else [(today.year - 1, "annual"), (today.year - 1, "q3")]
    reports: List[Dict[str, Any]] = []
    for year, kind in candidates[: int(config.get("cninfo_periodic_report_limit", 2) or 2)]:
        try:
            result = source.get_periodic_report(stock_code, year=year, kind=kind)
        except Exception as exc:
            reports.append({"status": "error", "year": year, "kind": kind, "error": str(exc)})
            continue
        report = dict((result or {}).get("report") or {}) if isinstance(result, dict) else {}
        if report:
            report["year"] = year
            report["kind"] = kind
            reports.append(report)
    return reports


def _build_company_profile_from_cninfo_announcements(stock_code: str, since: str, until: str, announcements: List[Dict[str, Any]], periodic_reports: List[Dict[str, Any]], announcements_result: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    if announcements_result.get("status") != "success":
        error = str(announcements_result.get("error") or "unknown error")
        return {"source": "data_sources.cninfo", "direction": "neutral", "confidence": 0.2, "reasoning": f"未能从 cninfo 获取公司公告：{error}", "signals": ["公司节点叙事：cninfo 公告获取失败，保持中性背景约束"], "uncertainties": [f"cninfo 公告获取失败：{error}"], "requires_web_search_for_full_report": True, "needs_human_review": True, "data_source_meta": {"provider": "cninfo", "status": announcements_result.get("status"), "since": since, "until": until, "error": error}}
    classified = [_classify_cninfo_announcement(item) for item in announcements]
    nodes = [item for item in classified if item.get("node_type") in {"capital_action", "strategy_change", "major_transaction", "governance_change"}][: int(config.get("cninfo_company_nodes_limit", 10) or 10)]
    catalysts = [item for item in classified if item.get("node_type") in {"growth_catalyst", "positive_performance", "shareholder_return"}][: int(config.get("cninfo_company_catalysts_limit", 8) or 8)]
    risks = [item for item in classified if item.get("node_type") == "risk_event"][: int(config.get("cninfo_company_risks_limit", 8) or 8)]
    current_position = [item for item in classified if item.get("node_type") == "periodic_report"][:6]
    for report in periodic_reports:
        title = str(report.get("title") or "定期报告")
        current_position.append({"date": _format_cninfo_date(report.get("ann_date")), "title": title, "node_type": "periodic_report", "interpretation": "已获取 cninfo 定期报告元数据，可作为后续深读管理层讨论、财务指标和订单线索的入口。", "source": "cninfo_periodic_report", "evidence": title, "md_path": report.get("md_path"), "pdf_url": report.get("pdf_url")})
    evidence = [{"date": item.get("date"), "title": item.get("title"), "node_type": item.get("node_type"), "source": item.get("source")} for item in (nodes + catalysts + risks + current_position)[:20]]
    score = len(catalysts) - len(risks)
    direction = "bullish" if score >= 2 else "bearish" if score <= -2 else "neutral"
    reasoning = f"基于 cninfo 法定披露公告（{since} 至 {until}，去重后 {len(announcements)} 条）抽取公司发展节点；识别关键节点 {len(nodes)} 条、增长/回报线索 {len(catalysts)} 条、风险事件 {len(risks)} 条。" if announcements else f"cninfo 在 {since} 至 {until} 窗口未返回公告，暂无法形成公司发展路径节点叙事。"
    signals = []
    if catalysts:
        signals.append(f"公司节点叙事：cninfo 披露中存在 {len(catalysts)} 条增长/股东回报线索")
    if risks:
        signals.append(f"公司节点叙事：cninfo 披露中存在 {len(risks)} 条风险事件，需约束技术信号")
    if nodes:
        signals.append(f"公司节点叙事：识别 {len(nodes)} 条资本运作/治理/战略节点")
    if not signals:
        signals.append("公司节点叙事：cninfo 公告未识别出明确方向约束")
    return {"source": "data_sources.cninfo", "direction": direction, "confidence": _clamp(0.25 + min(len(evidence), 12) * 0.02), "reasoning": reasoning, "signals": signals, "nodes": nodes, "catalysts": catalysts, "risks": risks, "current_position": [_cninfo_item_to_sentence(item) for item in current_position[:8]], "future_outlook": _build_cninfo_future_outlook(nodes, catalysts, risks), "evidence": evidence, "requires_web_search_for_full_report": False, "needs_human_review": True, "uncertainties": _dedupe_strings(["公司发展路径分析基于 cninfo 公告标题和可选定期报告元数据，未默认下载 PDF 全文；交易金额、客户、产能和财务科目仍需深读公告/年报正文验证。", "公告标题可识别方向性节点，但不能替代完整的公司发展史、行业格局和财务环比分析。"] + ([] if announcements else ["cninfo 公告列表为空，当前报告只保留结构化空状态。"])), "data_source_meta": {"provider": "cninfo", "status": "success", "since": since, "until": until, "announcements_total": len(announcements), "periodic_reports_total": len(periodic_reports), "download_reports": bool(config.get("cninfo_fetch_periodic_report", False))}}


def _classify_cninfo_announcement(item: Dict[str, Any]) -> Dict[str, Any]:
    title = str(item.get("title") or item.get("announcementTitle") or "")
    text = title.replace(" ", "")
    date_text = _format_cninfo_date(item.get("ann_date") or item.get("announcementTime"))
    node_type = "other_disclosure"
    interpretation = "法定披露公告，可作为公司发展路径分析的事实锚。"
    rules = [
        (["年度报告", "半年度报告", "季度报告", "一季报", "三季报"], "periodic_report", "定期报告披露，是验证主营业务、财务质量、订单和战略展望的核心入口。"),
        (["重大资产重组", "购买资产", "出售资产", "收购", "并购", "吸收合并", "对外投资", "投资建设", "设立子公司"], "major_transaction", "资本开支/并购/资产交易类公告，可能改变公司能力边界或版图结构。"),
        (["非公开发行", "定向增发", "向特定对象发行", "可转换公司债券", "配股", "上市", "募集资金"], "capital_action", "融资或资本市场动作，可能影响资本结构、扩张节奏和战略资源。"),
        (["控制权", "实际控制人", "控股股东", "权益变动", "董事会换届", "高级管理人员", "总经理", "董事长"], "governance_change", "控制权/治理结构变化，可能改变公司的战略定力、资源导入和风险偏好。"),
        (["战略合作", "重大合同", "中标", "项目合同", "订单", "产能", "投产", "扩产", "新产品", "获得认证"], "growth_catalyst", "订单、产能、产品或战略合作线索，可能构成当前增长点。"),
        (["业绩预增", "扭亏", "利润分配", "现金分红", "股份回购", "回购股份"], "positive_performance", "业绩改善或股东回报线索，可作为基本面/市场预期的正向事实锚。"),
        (["减持", "立案", "处罚", "监管函", "问询函", "诉讼", "仲裁", "冻结", "质押", "终止", "延期", "亏损", "预亏", "业绩下降", "业绩预减", "退市风险"], "risk_event", "风险类公告，需要作为技术信号的背景约束和人工复核重点。"),
    ]
    for keywords, kind, note in rules:
        if _contains_any(text, keywords):
            node_type, interpretation = kind, note
    return {"date": date_text, "title": title, "node_type": node_type, "interpretation": interpretation, "source": "cninfo_announcement", "ann_id": item.get("ann_id") or item.get("announcementId"), "evidence": title}


def _dedupe_cninfo_announcements(announcements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    rows: List[Dict[str, Any]] = []
    for item in announcements:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("ann_date") or item.get("announcementTime") or "")[:8], str(item.get("title") or item.get("announcementTitle") or ""))
        if key not in seen:
            seen.add(key)
            rows.append(item)
    rows.sort(key=lambda row: str(row.get("ann_date") or row.get("announcementTime") or ""), reverse=True)
    return rows


def _build_cninfo_future_outlook(nodes: List[Dict[str, Any]], catalysts: List[Dict[str, Any]], risks: List[Dict[str, Any]]) -> List[str]:
    outlook = []
    if catalysts:
        outlook.append("短期看，需跟踪公告中的订单/产能/新产品线索是否继续在后续定期报告中兑现为收入、合同负债和现金流。")
    if nodes:
        outlook.append("中期看，资本运作、治理或资产交易节点是否形成真实协同，是判断公司版图扩张质量的关键。")
    if risks:
        outlook.append("风险侧，减持、问询、诉讼、处罚、项目终止或业绩下修类公告需要优先人工复核。")
    return outlook or ["当前 cninfo 公告未给出明确新增节点，未来走向需等待更多法定披露和财务正文验证。"]


def _cninfo_item_to_sentence(item: Dict[str, Any]) -> str:
    return f"{item.get('date') or '日期未知'}：{item.get('title') or '公告标题未知'}。{item.get('interpretation') or '法定披露事实锚。'}"


def _format_cninfo_date(value: Any) -> str:
    text = str(value or "").strip()
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) >= 8 and text[:8].isdigit() else text


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _dedupe_strings(values: List[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _neutral_skill_result(reasoning: str, weight: float, confidence: float, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"skill_name": "company_evolution_analysis", "direction": "neutral", "confidence": _clamp(confidence), "reasoning": reasoning, "signals": [reasoning], "weight": weight, "meta": {"skill_name": "company_evolution_analysis", **(meta or {})}}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))
