#!/usr/bin/env python3
"""运行固定样本池的 FinancialAgent 回测并生成 Markdown 报告。"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from agents.financial import FINANCIAL_AGENT_VERSION, FinancialAgent
from data_sources import EastMoneyDataSource


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_POOL_PATH = Path(__file__).with_name("sample_pool_v1.csv")
DEFAULT_OUTPUT_DIR = REPO_ROOT / "output" / "financial_backtest"
DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "records" / "financial_agent_backtest_latest.md"
DEFAULT_EXECUTED_BY = "简简简水粽"
SIGNAL_DATES = [
    "2024-03-31",
    "2024-06-30",
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
]


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)
ALL_DATA_DATES = [
    "2023-03-31",
    "2023-06-30",
    "2023-09-30",
    "2023-12-31",
    "2024-03-31",
    "2024-06-30",
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
    "2026-03-31",
]


def cache_key(ticker: str, report_date: str) -> str:
    return f"{clean_ticker(ticker)}|{report_date}"


def clean_ticker(ticker: str) -> str:
    return ticker.split(".", 1)[0].replace("SH", "").replace("SZ", "")


def statement_row(statement: Any) -> dict[str, Any]:
    if isinstance(statement, dict):
        rows = statement.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        if "data" not in statement:
            return statement
    if isinstance(statement, list) and statement and isinstance(statement[0], dict):
        return statement[0]
    return {}


def cached_payload(statements: dict[Any, Any], ticker: str, report_date: str) -> dict[str, Any]:
    return (
        statements.get((clean_ticker(ticker), report_date))
        or statements.get(cache_key(ticker, report_date))
        or {}
    )


def previous_quarter(report_date: str) -> str:
    year, month, _ = (int(part) for part in report_date.split("-"))
    mapping = {
        3: (year - 1, 12, 31),
        6: (year, 3, 31),
        9: (year, 6, 30),
        12: (year, 9, 30),
    }
    previous_year, previous_month, previous_day = mapping[month]
    return f"{previous_year:04d}-{previous_month:02d}-{previous_day:02d}"


def next_quarter(report_date: str) -> str:
    year, month, _ = (int(part) for part in report_date.split("-"))
    mapping = {
        3: (year, 6, 30),
        6: (year, 9, 30),
        9: (year, 12, 31),
        12: (year + 1, 3, 31),
    }
    next_year, next_month, next_day = mapping[month]
    return f"{next_year:04d}-{next_month:02d}-{next_day:02d}"


def prior_year(report_date: str) -> str:
    year, month, day = (int(part) for part in report_date.split("-"))
    return f"{year - 1:04d}-{month:02d}-{day:02d}"


def standalone_quarter_value(
    statements: dict[Any, Any],
    ticker: str,
    report_date: str,
    sheet_name: str,
    field_name: str,
) -> float | None:
    current = statement_row(cached_payload(statements, ticker, report_date).get(sheet_name))
    raw_value = current.get(field_name)
    if raw_value in (None, ""):
        return None
    current_value = float(raw_value)
    month = int(report_date[5:7])
    if month == 3:
        return current_value

    previous_date = previous_quarter(report_date)
    previous = statement_row(cached_payload(statements, ticker, previous_date).get(sheet_name))
    previous_raw = previous.get(field_name)
    if previous_raw in (None, ""):
        return None
    return current_value - float(previous_raw)


def actual_direction(
    next_quarter_net_profit: float | None,
    prior_year_same_quarter_net_profit: float | None,
    next_quarter_revenue: float | None,
    *,
    threshold: float = 0.10,
    currency_epsilon: float = 1.0,
) -> dict[str, Any]:
    if None in (
        next_quarter_net_profit,
        prior_year_same_quarter_net_profit,
        next_quarter_revenue,
    ):
        return {
            "evaluable": False,
            "direction": None,
            "normalized_change": None,
            "reason": "下一季度或去年同期的单季归母净利润/营业收入缺失",
        }

    delta = float(next_quarter_net_profit) - float(prior_year_same_quarter_net_profit)
    scale = max(
        abs(float(prior_year_same_quarter_net_profit)),
        abs(float(next_quarter_revenue)) * 0.01,
        currency_epsilon,
    )
    normalized_change = delta / scale
    if normalized_change > threshold:
        direction = "bullish"
    elif normalized_change < -threshold:
        direction = "bearish"
    else:
        direction = "neutral"
    return {
        "evaluable": True,
        "direction": direction,
        "normalized_change": round(normalized_change, 6),
        "delta": delta,
        "scale": scale,
        "reason": "",
    }


def run_financial_agent(agent: FinancialAgent, ticker: str, report_date: str) -> dict[str, Any]:
    """Prediction boundary: every prediction must pass through FinancialAgent.analyze()."""
    agent.config["report_date"] = report_date
    signal = agent.analyze(clean_ticker(ticker))
    return signal.to_dict()


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    return numerator / denominator if denominator else None


def calculate_metrics(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = list(records)
    evaluable = [record for record in records if record.get("evaluable")]
    high_confidence = [
        record for record in evaluable if float(record.get("confidence") or 0) > 0.7
    ]
    return {
        "total_samples": len(records),
        "evaluable_samples": len(evaluable),
        "high_confidence_samples": len(high_confidence),
        "coverage_high_confidence": safe_ratio(len(high_confidence), len(evaluable)),
        "accuracy_high_confidence": safe_ratio(
            sum(bool(record.get("correct")) for record in high_confidence),
            len(high_confidence),
        ),
        "accuracy_all": safe_ratio(
            sum(bool(record.get("correct")) for record in evaluable),
            len(evaluable),
        ),
    }


def grouped_metrics(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record.get(field) or "unknown")].append(record)
    return [
        {"group": group, **calculate_metrics(group_records)}
        for group, group_records in sorted(groups.items())
    ]


def confidence_bucket_metrics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = {
        "<0.5": lambda value: value < 0.5,
        "0.5-0.6": lambda value: 0.5 <= value < 0.6,
        "0.6-0.7": lambda value: 0.6 <= value <= 0.7,
        ">0.7": lambda value: value > 0.7,
    }
    output = []
    for label, predicate in buckets.items():
        selected = [
            record
            for record in records
            if record.get("evaluable") and predicate(float(record.get("confidence") or 0))
        ]
        output.append(
            {
                "bucket": label,
                "samples": len(selected),
                "accuracy": safe_ratio(
                    sum(bool(record.get("correct")) for record in selected),
                    len(selected),
                ),
            }
        )
    return output


def confusion_matrix(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    directions = ("bullish", "neutral", "bearish")
    matrix = {actual: {predicted: 0 for predicted in directions} for actual in directions}
    for record in records:
        actual = record.get("actual_direction")
        predicted = record.get("predicted_direction")
        if record.get("evaluable") and actual in matrix and predicted in matrix[actual]:
            matrix[actual][predicted] += 1
    return matrix


def module_for_subsector(subsector_id: str) -> str:
    number = int(subsector_id)
    if 1 <= number <= 5:
        return "芯片设计与计算"
    if 6 <= number <= 11:
        return "制造、设备与材料"
    if 12 <= number <= 15:
        return "存储、载板和PCB"
    if 16 <= number <= 20 or number == 26:
        return "高速互连与网络"
    if 21 <= number <= 24:
        return "算力基础设施"
    return "机器人"


def outcome_type(next_profit: float | None, prior_profit: float | None) -> str:
    if next_profit is None or prior_profit is None:
        return "unknown"
    if prior_profit < 0 <= next_profit:
        return "扭亏"
    if prior_profit < 0 and next_profit < 0:
        return "亏损收窄" if next_profit > prior_profit else "持续亏损"
    return "盈利"


def gap_name(gap: Any) -> str:
    if isinstance(gap, dict):
        return str(gap.get("field") or gap.get("area") or "unknown")
    return str(gap)


def gap_label(value: str) -> str:
    labels = {
        "depreciation_amortization": "折旧摊销",
        "capacity_utilization": "产能利用率",
        "signed_orders": "已签订单",
        "order_backlog": "在手订单",
        "capacity_expansion_plan": "产能扩张计划",
        "supplier_long_term_agreements": "供应商长期协议",
        "segments/product_lines": "业务分部和产品线",
        "top_customers/top_suppliers/related_party_ratios": "客户、供应商和关联方结构",
        "revenue_qoq": "单季营收环比",
        "research_expense_qoq": "单季研发费用环比",
        "gross_margin_qoq": "单季毛利率环比",
        "operating_cash_flow_qoq": "单季经营现金流环比",
    }
    return labels.get(value, value)


def miss_analysis(record: dict[str, Any]) -> tuple[str, str]:
    predicted = record.get("predicted_direction")
    actual = record.get("actual_direction")
    normalized_change = abs(float(record.get("normalized_change") or 0))
    meta = record.get("signal", {}).get("meta", {})
    step_results = meta.get("step_results", {})
    unknown_steps = sum(value == "unknown" for value in step_results.values())
    gaps = [gap_name(item) for item in meta.get("data_gaps", [])]

    if normalized_change <= 0.20:
        category = "标签阈值附近"
        cause = "实际变化接近 neutral 边界，方向对阈值较敏感。"
    elif predicted == "neutral" and actual != "neutral":
        category = "中性偏置"
        cause = "七步链的混合信号被压缩为中性，未能识别下一季度利润方向。"
    elif predicted == "bullish":
        category = "质量信号未兑现"
        cause = "现金流、订单代理或扩张信号没有在下一季度兑现为归母净利润改善。"
    elif predicted == "bearish":
        category = "拐点识别滞后"
        cause = "风险项仍在，但下一季度利润已改善，可能存在低基数、减亏或商业化拐点。"
    else:
        category = "方向幅度判断不足"
        cause = "财务质量判断与下一季度利润同比方向不一致。"

    details = []
    if unknown_steps:
        details.append(f"{unknown_steps} 个步骤为 unknown")
    if gaps:
        details.append("主要缺口：" + "、".join(gaps[:4]))
    if details:
        cause += " " + "；".join(details) + "。"
    return category, cause


def company_equal_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_company[record["ticker"]].append(record)
    accuracies = []
    high_accuracies = []
    for company_records in by_company.values():
        metrics = calculate_metrics(company_records)
        if metrics["accuracy_all"] is not None:
            accuracies.append(metrics["accuracy_all"])
        if metrics["accuracy_high_confidence"] is not None:
            high_accuracies.append(metrics["accuracy_high_confidence"])
    return {
        "companies": len(by_company),
        "accuracy_all_company_equal": (
            sum(accuracies) / len(accuracies) if accuracies else None
        ),
        "accuracy_high_confidence_company_equal": (
            sum(high_accuracies) / len(high_accuracies) if high_accuracies else None
        ),
    }


class CachedFinancialDataSource:
    name = "东方财富历史财务缓存"

    def __init__(self, statements: dict[str, Any]):
        self.statements = statements

    def get_financial_data(
        self, stock_code: str, report_date: str | None = None
    ) -> dict[str, Any]:
        if not report_date:
            return {}
        return cached_payload(self.statements, stock_code, report_date)


def load_pool(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 51:
        raise ValueError(f"样本池必须恰好 51 家，实际 {len(rows)} 家")
    return rows


def payload_complete(payload: dict[str, Any]) -> bool:
    return all(statement_row(payload.get(sheet)) for sheet in ("balance", "income", "cashflow"))


def fetch_one(source: EastMoneyDataSource, ticker: str, report_date: str) -> dict[str, Any]:
    last_payload: dict[str, Any] = {}
    for attempt in range(3):
        last_payload = source.get_financial_data(clean_ticker(ticker), report_date=report_date)
        if payload_complete(last_payload):
            return last_payload
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    return last_payload


def load_or_fetch_statements(
    pool: list[dict[str, str]],
    cache_path: Path,
    *,
    max_workers: int,
    require_cache: bool = False,
) -> dict[str, Any]:
    if cache_path.exists():
        statements = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        statements = {}

    missing = [
        (row["ticker"], report_date)
        for row in pool
        for report_date in ALL_DATA_DATES
        if not payload_complete(cached_payload(statements, row["ticker"], report_date))
    ]
    if not missing:
        return statements
    if require_cache:
        preview = "、".join(f"{ticker}:{report_date}" for ticker, report_date in missing[:5])
        raise ValueError(
            "离线缓存不完整，无法在 require-cache 模式下运行回测；"
            f"缺失 {len(missing)} 个公司报告期三表，示例：{preview}"
        )

    source = EastMoneyDataSource()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(fetch_one, source, ticker, report_date): (ticker, report_date)
            for ticker, report_date in missing
        }
        for index, future in enumerate(as_completed(future_map), start=1):
            ticker, report_date = future_map[future]
            try:
                statements[cache_key(ticker, report_date)] = future.result()
            except Exception as exc:
                statements[cache_key(ticker, report_date)] = {"fetch_error": str(exc)}
            if index % 25 == 0 or index == len(future_map):
                cache_path.write_text(
                    json.dumps(statements, ensure_ascii=False),
                    encoding="utf-8",
                )
    return statements


def build_iteration_recommendations(
    misses: list[dict[str, Any]], records: list[dict[str, Any]]
) -> list[str]:
    categories = Counter(record["miss_category"] for record in misses)
    gaps = Counter(
        gap_name(gap)
        for record in misses
        for gap in record.get("signal", {}).get("meta", {}).get("data_gaps", [])
    )
    recommendations = []
    if categories.get("中性偏置"):
        recommendations.append(
            f"优先校准方向聚合规则：{categories['中性偏置']} 个误判来自中性偏置，"
            "应区分“高置信中性”和“证据冲突导致的中性”，并验证不同“通过/观察”组合的下一季方向。"
        )
    if categories.get("拐点识别滞后"):
        recommendations.append(
            f"增强亏损收窄和商业化拐点识别：{categories['拐点识别滞后']} 个误判为风险判断滞后，"
            "需把单季收入、毛利率、研发费用和经营现金流的拐点组合固化为可回测规则。"
        )
    if categories.get("质量信号未兑现"):
        recommendations.append(
            f"收紧前瞻质量信号：{categories['质量信号未兑现']} 个误判显示合同负债、收现或扩张"
            "不一定在下一季度兑现，应加入订单交付周期和利润率约束。"
        )
    if gaps:
        top_gaps = "、".join(
            f"{gap_label(name)}({count})" for name, count in gaps.most_common(6)
        )
        recommendations.append(
            f"按误判样本补数据而非继续堆通用阈值。高频缺口为：{top_gaps}；"
            "优先接入订单/产品线/产能利用率/客户结构等能直接解释需求真实性和扩张质量的数据。"
        )
    high_metrics = calculate_metrics(records)
    if (
        high_metrics["accuracy_high_confidence"] is not None
        and high_metrics["accuracy_high_confidence"] < 0.70
    ):
        recommendations.append(
            "重新校准置信度：高置信样本准确率未达到 70%，应按证据独立性、跨期一致性和"
            "方向支持强度重新拟合分档，暂不提升财务分析技能的稳定状态。"
        )
    recommendations.append(
        "建立公告时点历史快照层并重复本回测，区分“规则误判”和“重述数据或未来信息泄漏”造成的偏差。"
    )
    return recommendations


def execute_backtest(
    pool: list[dict[str, str]],
    statements: dict[str, Any],
    *,
    label_threshold: float = 0.10,
) -> list[dict[str, Any]]:
    data_source = CachedFinancialDataSource(statements)
    agent = FinancialAgent(
        config={
            "financial_data_source": data_source,
            "include_previous_period": True,
            "include_single_quarter_periods": True,
        }
    )
    records = []
    for company in pool:
        ticker = company["ticker"]
        for signal_date in SIGNAL_DATES:
            signal = run_financial_agent(agent, ticker, signal_date)
            result_date = next_quarter(signal_date)
            prior_result_date = prior_year(result_date)
            next_profit = standalone_quarter_value(
                statements, ticker, result_date, "income", "PARENT_NETPROFIT"
            )
            prior_profit = standalone_quarter_value(
                statements, ticker, prior_result_date, "income", "PARENT_NETPROFIT"
            )
            next_revenue = standalone_quarter_value(
                statements, ticker, result_date, "income", "OPERATE_INCOME"
            )
            actual = actual_direction(
                next_profit,
                prior_profit,
                next_revenue,
                threshold=label_threshold,
            )
            predicted = signal["direction"]
            record = {
                **company,
                "module": module_for_subsector(company["subsector_id"]),
                "signal_date": signal_date,
                "result_date": result_date,
                "predicted_direction": predicted,
                "confidence": signal["confidence"],
                "actual_direction": actual["direction"],
                "normalized_change": actual["normalized_change"],
                "evaluable": actual["evaluable"],
                "exclusion_reason": actual["reason"],
                "correct": actual["evaluable"] and predicted == actual["direction"],
                "next_quarter_net_profit": next_profit,
                "prior_year_same_quarter_net_profit": prior_profit,
                "next_quarter_revenue": next_revenue,
                "outcome_type": outcome_type(next_profit, prior_profit),
                "observed_stage": (
                    signal.get("meta", {}).get("business_stage", {}).get("stage", "unknown")
                ),
                "signal": signal,
            }
            records.append(record)
    return records


def build_report(
    pool: list[dict[str, str]],
    records: list[dict[str, Any]],
    *,
    cache_path: Path,
    label_threshold: float,
    pool_path: Path = DEFAULT_POOL_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    executed_by: str = DEFAULT_EXECUTED_BY,
) -> dict[str, Any]:
    misses = []
    for record in records:
        if record.get("evaluable") and not record.get("correct"):
            category, cause = miss_analysis(record)
            miss = dict(record)
            miss["miss_category"] = category
            miss["miss_cause"] = cause
            misses.append(miss)

    generated_at = datetime.now().isoformat(timespec="seconds")
    signal_window = "2024Q1 至 2025Q4"
    result_window = "2024Q2 至 2026Q1"
    return {
        "generated_at": generated_at,
        "backtest_record": {
            "backtest_date": generated_at[:10],
            "financial_agent_version": FINANCIAL_AGENT_VERSION,
            "executed_by": executed_by,
            "sample_pool": repo_relative(pool_path),
            "backtest_period": f"{signal_window} 信号，{result_window} 验证",
            "result_report": repo_relative(report_path),
        },
        "methodology": {
            "prediction_target": "下一季度单季归母净利润同比方向",
            "signal_window": signal_window,
            "result_window": result_window,
            "label_formula": (
                "变化额＝下一季度单季归母净利润－去年同期单季归母净利润；"
                "标准化基数取去年同期单季归母净利润绝对值、下一季度单季营收的 1% 和 1 三者最大值；"
                f"标准化变化＝变化额÷标准化基数，方向阈值为 ±{label_threshold:.2f}"
            ),
            "main_metric": "置信度大于 0.7 的方向准确率",
            "coverage_metric": "高置信 Signal 数量 / 可评估样本数",
            "prediction_boundary": "所有预测均由 FinancialAgent.analyze() 生成，未调用其他专家智能体。",
            "data_source": "FinancialAgent 配置的东方财富数据源，经固定历史报告期缓存复用。",
            "cache_path": repo_relative(cache_path),
        },
        "sample_pool": pool,
        "metrics": {**calculate_metrics(records), **company_equal_metrics(records)},
        "group_metrics": {
            "module": grouped_metrics(records, "module"),
            "subsector": grouped_metrics(records, "subsector"),
            "anchor_stage": grouped_metrics(records, "anchor_stage"),
            "observed_stage": grouped_metrics(records, "observed_stage"),
            "outcome_type": grouped_metrics(records, "outcome_type"),
            "signal_date": grouped_metrics(records, "signal_date"),
            "company": grouped_metrics(records, "company_name"),
        },
        "confidence_buckets": confidence_bucket_metrics(records),
        "confusion_matrix": confusion_matrix(records),
        "misses": misses,
        "iteration_recommendations": build_iteration_recommendations(misses, records),
        "limitations": [
            "当前东方财富历史接口返回的是执行日可见的历史报表数据，不是每个公告日冻结的历史快照；"
            "本报告是可复现基线，但不能完全排除财务重述带来的未来数据泄漏。",
            "当前仓库提交样本池、执行器和版本化 Markdown 报告，不提交完整历史三表输入快照；"
            "默认执行器在缓存缺失时会拉取线上数据，严格复现需使用同一份本地缓存并开启 require-cache 模式，"
            "或后续单独建设固定历史输入快照。",
            "当前结果是 draft 阶段基线记录，高置信准确率尚未达到 70% 最小可用版本目标，"
            "不表示财务 Agent 已进入稳定可用版。",
            "FinancialAgent 当前仅使用结构化三表及其可计算字段；订单、产品线、产能利用率、"
            "前五大客户/供应商和关联方等增强数据缺失时，会在数据缺口中披露。",
            "连续季度样本存在公司内相关性；本报告披露公司等权和公司-季度等权结果，"
            "尚未计算按公司聚类置信区间和留一公司验证。",
        ],
        "records": records,
    }


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def direction_label(value: str | None) -> str:
    return {
        "bullish": "看多",
        "bearish": "看空",
        "neutral": "中性",
    }.get(value or "", value or "不可评估")


def stage_label(value: str | None) -> str:
    return {
        "research_validation": "研发验证",
        "commercialization_ramp": "商业化爬坡",
        "scale_profit": "规模盈利",
        "mature_cyclical": "成熟周期",
        "rd_commercialization": "高研发商业化过渡",
        "standard": "标准阶段",
        "unknown": "未知",
    }.get(value or "", value or "未知")


def group_label(value: str) -> str:
    return stage_label(value) if value in {
        "research_validation",
        "commercialization_ramp",
        "scale_profit",
        "mature_cyclical",
        "rd_commercialization",
        "standard",
        "unknown",
    } else value


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    header = "| " + " | ".join(markdown_cell(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(markdown_cell(item) for item in row) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def group_markdown_table(rows: list[dict[str, Any]]) -> str:
    return markdown_table(
        ["分组", "样本数", "可评估数", "高置信数", "覆盖率", "高置信准确率", "全样本准确率"],
        (
            (
                group_label(row["group"]),
                row["total_samples"],
                row["evaluable_samples"],
                row["high_confidence_samples"],
                fmt_pct(row["coverage_high_confidence"]),
                fmt_pct(row["accuracy_high_confidence"]),
                fmt_pct(row["accuracy_all"]),
            )
            for row in rows
        ),
    )


def miss_summary_rows(misses: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    total = len(misses)
    counts = Counter(item["miss_category"] for item in misses)
    explanations = {
        "中性偏置": (
            "多组财务证据互相冲突时，结论集中落在中性，错过了下一季度明确改善或恶化。",
            "拆分“证据冲突中性”和“趋势稳定中性”，重新回测七步状态组合。",
        ),
        "拐点识别滞后": (
            "风险项仍在，但利润已经出现减亏、扭亏或低基数改善，现有规则对拐点反应偏慢。",
            "强化单季收入、毛利率、研发费用和经营现金流的拐点组合。",
        ),
        "质量信号未兑现": (
            "合同负债、销售收现或资产扩张等质量信号未在下一季度兑现为利润改善。",
            "增加订单交付周期、产品结构和利润率约束。",
        ),
        "标签阈值附近": (
            "实际变化接近中性阈值，轻微数据变化就可能改变真实方向标签。",
            "补充不同标签阈值的敏感性分析，避免对边界样本过度解读。",
        ),
        "方向幅度判断不足": (
            "经营质量判断与下一季度利润同比方向不一致。",
            "按行业和生命周期检查方向聚合规则。",
        ),
    }
    rows = []
    for category, count in counts.most_common():
        issue, suggestion = explanations.get(
            category,
            ("同类误判尚未形成稳定解释。", "继续按七步结果和数据缺口归因。"),
        )
        rows.append((category, count, fmt_pct(safe_ratio(count, total)), issue, suggestion))
    return rows


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    methodology = report["methodology"]
    backtest_record = report.get("backtest_record", {})
    sample_pool = report["sample_pool"]
    misses = report["misses"]
    confusion = report["confusion_matrix"]
    directions = ("bullish", "neutral", "bearish")
    methodology_labels = {
        "prediction_target": "预测目标",
        "signal_window": "信号季度",
        "result_window": "结果季度",
        "label_formula": "真实标签公式",
        "main_metric": "主指标",
        "coverage_metric": "覆盖率口径",
        "prediction_boundary": "预测边界",
        "data_source": "数据来源",
        "cache_path": "本地缓存位置",
    }
    record_labels = {
        "backtest_date": "日期",
        "financial_agent_version": "财务 Agent 版本",
        "executed_by": "回测执行人",
        "sample_pool": "回测样本池",
        "backtest_period": "回测周期",
        "result_report": "回测结果报告",
    }

    sample_table = markdown_table(
        ["细分", "公司", "代码", "生命周期", "市场"],
        (
            (
                item.get("subsector", ""),
                item.get("company_name", ""),
                item.get("ticker", ""),
                stage_label(item.get("anchor_stage")),
                item.get("listing_market", ""),
            )
            for item in sample_pool
        ),
    )
    confidence_table = markdown_table(
        ["置信度档位", "样本数", "准确率"],
        (
            (item["bucket"], item["samples"], fmt_pct(item["accuracy"]))
            for item in report["confidence_buckets"]
        ),
    )
    confusion_table = markdown_table(
        ["实际方向 \\ 预测方向", *(direction_label(item) for item in directions)],
        (
            (
                direction_label(actual),
                *(confusion.get(actual, {}).get(predicted, 0) for predicted in directions),
            )
            for actual in directions
        ),
    )
    miss_table = markdown_table(
        ["问题类别", "数量", "误判占比", "共性问题", "建议方向"],
        miss_summary_rows(misses),
    )
    methodology_list = "\n".join(
        f"- **{methodology_labels.get(key, key)}**：{value}"
        for key, value in methodology.items()
    )
    record_table = markdown_table(
        ["字段", "内容"],
        (
            (label, backtest_record.get(key, ""))
            for key, label in record_labels.items()
        ),
    )
    recommendations = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(report["iteration_recommendations"], start=1)
    )
    limitations = "\n".join(f"- {item}" for item in report["limitations"])
    group_titles = {
        "module": "产业模块",
        "subsector": "细分方向",
        "anchor_stage": "样本池生命周期",
        "observed_stage": "季度观察阶段",
        "outcome_type": "实际经营结果",
        "signal_date": "信号季度",
        "company": "公司",
    }
    group_sections = "\n\n".join(
        f"### 按{group_titles.get(name, name)}分组\n\n{group_markdown_table(rows)}"
        for name, rows in report["group_metrics"].items()
    )
    return f"""# FinancialAgent 全样本回测报告

生成时间：{report["generated_at"]}

## 回测记录

{record_table}

## 核心结果

| 指标 | 结果 |
| --- | --- |
| 总样本数 | {metrics["total_samples"]} |
| 可评估样本数 | {metrics["evaluable_samples"]} |
| 高置信样本数 | {metrics["high_confidence_samples"]} |
| 高置信覆盖率 | {fmt_pct(metrics["coverage_high_confidence"])} |
| 高置信准确率 | {fmt_pct(metrics["accuracy_high_confidence"])} |
| 全样本准确率 | {fmt_pct(metrics["accuracy_all"])} |
| 公司等权高置信准确率 | {fmt_pct(metrics.get("accuracy_high_confidence_company_equal"))} |
| 公司等权全样本准确率 | {fmt_pct(metrics.get("accuracy_all_company_equal"))} |

## 回测口径说明

{methodology_list}

### 口径限制

{limitations}

## 样本池

固定样本池共 {len(sample_pool)} 家公司，每家公司 8 个信号季度，理论样本 {len(sample_pool) * 8} 条。

{sample_table}

## 回测结果

### 置信度分档

{confidence_table}

### 混淆矩阵

{confusion_table}

### 分组结果

{group_sections}

## 误判分析

可评估样本中共有 {len(misses)} 个误判。以下只汇总同类问题，不列逐样本明细。
归因只使用 FinancialAgent 自身的七步结果、风险项和数据缺口，不引入其他专家智能体。

{miss_table if misses else "本次没有误判样本。"}

## FinancialAgent 迭代建议

{recommendations}

## 审计数据

逐样本预测、真实标签、七步结果、风险项和数据缺口保存在本地 JSON 审计文件中，
不在本报告展开。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 FinancialAgent 固定样本池全量回测")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--label-threshold", type=float, default=0.10)
    parser.add_argument(
        "--require-cache",
        action="store_true",
        help="只使用本地缓存；缓存缺失或不完整时直接失败，不拉取线上数据。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.cache or args.output_dir / "financial_statements_cache_v1.json"
    pool = load_pool(args.pool)
    statements = load_or_fetch_statements(
        pool,
        cache_path,
        max_workers=max(1, args.max_workers),
        require_cache=args.require_cache,
    )
    records = execute_backtest(
        pool,
        statements,
        label_threshold=args.label_threshold,
    )
    report = build_report(
        pool,
        records,
        cache_path=cache_path,
        label_threshold=args.label_threshold,
        pool_path=args.pool,
        report_path=args.report,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = args.output_dir / f"financial_agent_backtest_{stamp}.json"
    latest_json = args.output_dir / "financial_agent_backtest_latest.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    markdown_payload = render_markdown_report(report)
    json_path.write_text(payload + "\n", encoding="utf-8")
    latest_json.write_text(payload + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown_payload, encoding="utf-8")
    print(json.dumps({
        "report": str(args.report),
        "json": str(json_path),
        "metrics": report["metrics"],
        "misses": len(report["misses"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
