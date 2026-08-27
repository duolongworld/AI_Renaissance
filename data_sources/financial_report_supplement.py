"""Financial-report supplemental fields extracted from official CNINFO filings.

The existing :class:`EastMoneyDataSource` remains the source of the three
financial statements.  This module only fills fields that normally exist in
the filing narrative or notes: orders, capacity plans, segment/product-line
tables, and depreciation/amortization.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from .cninfo import CninfoDataSource


SUPPLEMENT_FIELDS = (
    "signed_orders",
    "order_backlog",
    "capacity_expansion_plan",
    "capacity_utilization",
    "segments",
    "product_lines",
    "depreciation_amortization",
)

_AMOUNT_RE = r"(-?[\d,]+(?:\.\d+)?)\s*(亿元|万元|元)"


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("\n", "").strip()
    if not text or text in {"-", "--", "—"}:
        return None
    text = text.replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _amount_to_yuan(value: str, unit: str) -> float:
    multiplier = {"亿元": 100_000_000.0, "万元": 10_000.0, "元": 1.0}[unit]
    return float(value.replace(",", "")) * multiplier


def _clean(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _page_label(page_text: str, pdf_page: int) -> Dict[str, int]:
    report_page = None
    for line in reversed((page_text or "").splitlines()):
        line = line.strip()
        if re.fullmatch(r"\d{1,4}", line):
            report_page = int(line)
            break
    result = {"pdf_page": pdf_page}
    if report_page is not None:
        result["report_page"] = report_page
    return result


def _find_text_page(text: str, evidence: str) -> Dict[str, int]:
    """Best-effort visible report page lookup in PyMuPDF's concatenated text."""
    index = text.find(evidence)
    if index < 0:
        return {}
    prefix = text[:index]
    matches = list(re.finditer(r"报告(?:全文)?\s*\n\s*(\d{1,4})\s*\n", prefix))
    return {"report_page": int(matches[-1].group(1))} if matches else {}


def _extract_orders(text: str) -> tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    compact = _compact_text(text)
    fields: Dict[str, Any] = {}
    sources: Dict[str, Any] = {}
    warnings: List[str] = []

    backlog_patterns = (
        rf"(截至本报告披露日[^。；]{{0,50}}?尚未确认收入的在手订单(?:金额)?(?:约|为|达)?{_AMOUNT_RE})",
        rf"(在手订单(?:金额)?(?:约|为|达){_AMOUNT_RE})",
    )
    for pattern in backlog_patterns:
        match = re.search(pattern, compact)
        if match:
            fields["order_backlog"] = _amount_to_yuan(match.group(2), match.group(3))
            sources["order_backlog"] = {
                "unit": "CNY",
                "scope": "company_total",
                "as_of": "report_disclosure_date" if "披露日" in match.group(1) else "filing_text",
                "evidence": match.group(1),
                **_find_text_page(text, "在手订单"),
            }
            break

    backlog_breakdown = next(
        (
            match
            for match in re.finditer(
                rf"((?P<scope>[^\u3002\uff1b]{{2,40}}?(?:\u4e1a\u52a1\u677f\u5757)?)\u5728\u624b\u8ba2\u5355(?:\u91d1\u989d)?(?:\u7ea6|\u4e3a|\u8fbe){_AMOUNT_RE})",
                compact,
            )
            if any(keyword in match.group("scope") for keyword in ("\u4e1a\u52a1", "\u4ea7\u54c1", "\u5149\u7535", "\u534a\u5bfc\u4f53", "\u5149\u4f0f"))
        ),
        None,
    )
    if backlog_breakdown:
        scope = re.sub(r"^截至本报告披露日，?", "", backlog_breakdown.group("scope"))
        scope = re.sub(r"^公司", "", scope)
        fields["order_backlog_breakdown"] = [{
            "scope": scope,
            "value": _amount_to_yuan(backlog_breakdown.group(3), backlog_breakdown.group(4)),
        }]
        sources["order_backlog_breakdown"] = {
            "unit": "CNY",
            "scope": scope,
            "evidence": backlog_breakdown.group(1),
            **_find_text_page(text, "\u5728\u624b\u8ba2\u5355\u91d1\u989d"),
        }

    signed_patterns = (
        rf"(本报告期内[^。；]{{0,100}}?(?:已收到|已签订|签署)[^。；]{{0,80}}?(?:累计)?(?:高达)?(?:约)?{_AMOUNT_RE}(?:的)?订单)",
        rf"((?:新签|已签|累计签订)订单(?:金额)?(?:约|为|达)?{_AMOUNT_RE})",
    )
    for pattern in signed_patterns:
        match = re.search(pattern, compact)
        if match:
            evidence = match.group(1)
            scope = "same_customer_group" if "同一集团客户" in evidence else "company_disclosed"
            fields["signed_orders"] = _amount_to_yuan(match.group(2), match.group(3))
            sources["signed_orders"] = {
                "unit": "CNY",
                "scope": scope,
                "period_scope": "reporting_period",
                "evidence": evidence,
                **_find_text_page(text, "本报告期内已收到"),
            }
            if scope != "company_disclosed":
                warnings.append("已签订单为特定客户范围披露，不代表公司全部已签订单。")
            break

    return fields, sources, warnings


def _extract_capacity(text: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    compact = _compact_text(text)
    sentences = re.split(r"(?<=[。；])", compact)
    keywords = (
        "扩产节奏",
        "扩充其产能",
        "生产/组装基地",
        "新的生产/组装基地",
        "人员、工具、供应商产能",
        "项目投产",
    )
    selected = [s for s in sentences if any(key in s for key in keywords)]
    fields: Dict[str, Any] = {}
    sources: Dict[str, Any] = {}
    if selected:
        evidence = "".join(selected[:5])[:1200]
        fields["capacity_expansion_plan"] = evidence
        sources["capacity_expansion_plan"] = {
            "unit": "text",
            "scope": "management_plan",
            "evidence": evidence,
            **_find_text_page(text, selected[0][:20]),
        }

    utilization = re.search(rf"(产能利用率(?:为|达|约为)?(-?[\d.]+)%?)", compact)
    if utilization:
        fields["capacity_utilization"] = float(utilization.group(2)) / 100.0
        sources["capacity_utilization"] = {
            "unit": "ratio",
            "scope": "filing_disclosed",
            "evidence": utilization.group(1),
            **_find_text_page(text, "产能利用率"),
        }
    return fields, sources


def _extract_depreciation(
    text: str, tables_by_page: List[Dict[str, Any]]
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    labels = {
        "fixed_asset_depreciation": "固定资产折旧",
        "right_of_use_asset_depreciation": "使用权资产折旧",
        "intangible_asset_amortization": "无形资产摊销",
        "long_term_deferred_amortization": "长期待摊费用摊销",
    }
    components: Dict[str, float] = {}
    pages: List[Dict[str, int]] = []
    evidence: List[str] = []
    for page in tables_by_page:
        for table in page.get("tables", []):
            if not table:
                continue
            header = "|".join(_clean(cell) for cell in table[0])
            if "补充资料" not in header or "本期金额" not in header:
                continue
            for row in table or []:
                if not row:
                    continue
                row_label = _clean(row[0])
                for key, label in labels.items():
                    if key in components or label not in row_label:
                        continue
                    value = _number(row[1] if len(row) > 1 else None)
                    if value is not None:
                        components[key] = value
                        evidence.append(f"{row_label}:{value}")
                        pages.append(_page_label(page.get("text", ""), page["pdf_page"]))

    compact = _compact_text(text)
    cashflow_note = compact.rfind("现金流量表补充资料")
    if cashflow_note >= 0:
        compact = compact[cashflow_note:]
    if len(components) < len(labels):
        for key, label in labels.items():
            if key in components:
                continue
            match = re.search(rf"{label}[^\d-]{{0,25}}(-?[\d,]+(?:\.\d+)?)", compact)
            value = _number(match.group(1)) if match else None
            if value is not None:
                components[key] = value
                evidence.append(f"{label}:{value}")

    if not components:
        return {}, {}
    total = round(sum(components.values()), 2)
    return {"depreciation_amortization": total}, {
        "depreciation_amortization": {
            "unit": "CNY",
            "scope": "reporting_period",
            "calculation": "sum_of_disclosed_components",
            "components": components,
            "evidence": evidence,
            "pages": pages,
        }
    }


def _extract_product_lines(
    tables_by_page: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    rows_out: List[Dict[str, Any]] = []
    pages: List[Dict[str, int]] = []
    for page in tables_by_page:
        for table in page.get("tables", []):
            if not table:
                continue
            header = "|".join(_clean(cell) for cell in table[0])
            if "营业收入" not in header or "营业成本" not in header or "毛利率" not in header:
                continue
            for row in table[1:]:
                if not row or len(row) < 4:
                    continue
                name = _clean(row[0])
                revenue, cost, margin = _number(row[1]), _number(row[2]), _number(row[3])
                if not name or revenue is None or cost is None or margin is None:
                    continue
                item = {
                    "name": name,
                    "revenue": revenue,
                    "operating_cost": cost,
                    "gross_margin": margin / 100.0,
                }
                if len(row) > 4 and _number(row[4]) is not None:
                    item["revenue_yoy"] = _number(row[4]) / 100.0
                if len(row) > 6 and _number(row[6]) is not None:
                    item["gross_margin_change_pp"] = _number(row[6])
                rows_out.append(item)
            if rows_out:
                pages.append(_page_label(page.get("text", ""), page["pdf_page"]))
    if not rows_out:
        return {}, {}
    return {"product_lines": rows_out}, {
        "product_lines": {
            "unit": "CNY_and_ratio",
            "scope": "products_or_services_over_10_percent",
            "pages": pages,
            "extraction_status": "table_extracted",
        }
    }


def _extract_segments(
    tables_by_page: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    segment_names: List[str] = []
    captured: Dict[str, List[Any]] = {}
    pages: List[Dict[str, int]] = []
    active = False
    for page in tables_by_page:
        for table in page.get("tables", []):
            if not table:
                continue
            first = [_clean(cell) for cell in table[0]]
            if "分部间抵销" in first and "合计" in first:
                active = True
                segment_names = [name for name in first[1:-2] if name]
                rows = table[1:]
            elif active and len(table[0]) == len(segment_names) + 3:
                rows = table
            else:
                continue
            for row in rows:
                if not row:
                    continue
                label = _clean(row[0])
                if label in {"营业收入", "其中：对外交易收入", "营业利润/(亏损)", "营业利润（亏损）", "营业利润"}:
                    captured[label] = [_number(cell) for cell in row[1:]]
                    pages.append(_page_label(page.get("text", ""), page["pdf_page"]))

    if not segment_names:
        return {}, {}
    revenue = captured.get("其中：对外交易收入") or captured.get("营业收入") or []
    profit = next((values for key, values in captured.items() if key.startswith("营业利润")), [])
    items = []
    for index, name in enumerate(segment_names):
        item = {"name": name}
        if index < len(revenue) and revenue[index] is not None:
            item["external_revenue"] = revenue[index]
        if index < len(profit) and profit[index] is not None:
            item["operating_profit"] = profit[index]
        items.append(item)
    consolidated = {}
    if revenue and revenue[-1] is not None:
        consolidated["external_revenue"] = revenue[-1]
    if profit and profit[-1] is not None:
        consolidated["operating_profit"] = profit[-1]
    value = {"items": items, "consolidated": consolidated}
    return {"segments": value}, {
        "segments": {
            "unit": "CNY",
            "scope": "reportable_segments",
            "pages": pages,
            "extraction_status": "table_extracted",
        }
    }


def extract_financial_report_supplement(
    text: str,
    tables_by_page: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract stable supplemental fields from filing text and PDF tables."""
    tables = tables_by_page or []
    fields: Dict[str, Any] = {}
    field_sources: Dict[str, Any] = {}
    warnings: List[str] = []
    for extractor in (
        lambda: _extract_orders(text),
        lambda: (*_extract_capacity(text), []),
        lambda: (*_extract_depreciation(text, tables), []),
        lambda: (*_extract_product_lines(tables), []),
        lambda: (*_extract_segments(tables), []),
    ):
        extracted, sources, extractor_warnings = extractor()
        fields.update(extracted)
        field_sources.update(sources)
        warnings.extend(extractor_warnings)
    return {"fields": fields, "field_sources": field_sources, "warnings": warnings}


class FinancialReportSupplementDataSource:
    """Fetch and parse one official periodic report for FinancialAgent."""

    name = "巨潮资讯财报补充数据源"

    def __init__(
        self,
        cninfo_source: Optional[CninfoDataSource] = None,
        table_reader: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    ):
        self.cninfo_source = cninfo_source or CninfoDataSource()
        self.table_reader = table_reader or self._read_pdf_tables
        self._report_cache: Dict[tuple[str, str], Dict[str, Any]] = {}
        self._supplement_cache: Dict[tuple[str, str], Dict[str, Any]] = {}

    @staticmethod
    def report_kind(report_date: str) -> tuple[int, str]:
        parsed = datetime.strptime(str(report_date)[:10], "%Y-%m-%d")
        kind = {(3, 31): "q1", (6, 30): "h1", (9, 30): "q3", (12, 31): "annual"}.get(
            (parsed.month, parsed.day)
        )
        if kind is None:
            raise ValueError(f"不支持的定期报告期: {report_date}")
        return parsed.year, kind

    @staticmethod
    def candidate_report_dates(as_of: Optional[date] = None) -> List[str]:
        today = as_of or date.today()
        candidates: List[str] = []
        if today.month >= 10:
            candidates.append(f"{today.year}-09-30")
        if today.month >= 7:
            candidates.append(f"{today.year}-06-30")
        if today.month >= 4:
            candidates.append(f"{today.year}-03-31")
        candidates.extend([f"{today.year - 1}-12-31", f"{today.year - 1}-09-30"])
        return candidates

    def resolve_latest_report_date(self, stock_code: str, as_of: Optional[date] = None) -> Optional[str]:
        for report_date in self.candidate_report_dates(as_of):
            result = self._fetch_report(stock_code, report_date)
            if result.get("status") == "success" and result.get("report"):
                return report_date
        return None

    def get_financial_supplement(self, stock_code: str, report_date: str) -> Dict[str, Any]:
        if not report_date:
            return self._error(stock_code, report_date, "缺少报告期")
        cache_key = (self._normalize_stock_code(stock_code), report_date)
        if cache_key in self._supplement_cache:
            return self._supplement_cache[cache_key]
        try:
            result = self._fetch_report(stock_code, report_date)
        except (TypeError, ValueError) as exc:
            return self._error(stock_code, report_date, str(exc))
        if result.get("status") != "success" or not result.get("report"):
            return self._error(stock_code, report_date, result.get("error") or "未取得定期报告")

        report = result["report"]
        md_path = Path(str(report.get("md_path") or ""))
        if not md_path.is_file():
            return self._error(stock_code, report_date, f"报告正文不存在: {md_path}", report=report)
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            return self._error(stock_code, report_date, f"读取报告正文失败: {exc}", report=report)

        warnings: List[str] = []
        tables: List[Dict[str, Any]] = []
        pdf_path = str(report.get("pdf_path") or "")
        if pdf_path:
            try:
                tables = self.table_reader(pdf_path)
            except Exception as exc:  # PDF tables are optional; text fields still survive.
                warnings.append(f"PDF表格提取失败: {type(exc).__name__}: {exc}")

        parsed = extract_financial_report_supplement(text, tables)
        warnings.extend(parsed["warnings"])
        common_source = {
            "source_type": "official_filing",
            "source_name": "CNINFO",
            "report_date": report_date,
            "ann_id": report.get("ann_id"),
            "ann_date": report.get("ann_date"),
            "title": report.get("title"),
            "pdf_url": report.get("pdf_url") or report.get("source"),
            "md_path": str(md_path),
            "pdf_path": pdf_path or None,
        }
        field_sources = {
            key: {**common_source, **source}
            for key, source in parsed["field_sources"].items()
        }
        fields = parsed["fields"]
        missing = [field for field in SUPPLEMENT_FIELDS if field not in fields]
        response = {
            "status": "success" if fields else "partial",
            "stock_code": self._normalize_stock_code(stock_code),
            "report_date": report_date,
            "source": common_source,
            "fields": fields,
            "field_sources": field_sources,
            "missing_fields": missing,
            "warnings": warnings,
        }
        self._supplement_cache[cache_key] = response
        return response

    def _fetch_report(self, stock_code: str, report_date: str) -> Dict[str, Any]:
        code = self._normalize_stock_code(stock_code)
        key = (code, report_date)
        if key in self._report_cache:
            return self._report_cache[key]
        year, kind = self.report_kind(report_date)
        result = self.cninfo_source.get_periodic_report(code, year, kind)
        if result.get("status") == "success" and result.get("report"):
            self._report_cache[key] = result
        return result

    @staticmethod
    def _normalize_stock_code(stock_code: str) -> str:
        match = re.search(r"(\d{6})", str(stock_code))
        return match.group(1) if match else str(stock_code).strip()

    @staticmethod
    def _error(
        stock_code: str,
        report_date: Optional[str],
        error: str,
        *,
        report: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "error",
            "stock_code": FinancialReportSupplementDataSource._normalize_stock_code(stock_code),
            "report_date": report_date,
            "source": {"source_type": "official_filing", "source_name": "CNINFO", "report": report or {}},
            "fields": {},
            "field_sources": {},
            "missing_fields": list(SUPPLEMENT_FIELDS),
            "warnings": [],
            "error": error,
        }

    @staticmethod
    def _read_pdf_tables(pdf_path: str) -> List[Dict[str, Any]]:
        try:
            import pdfplumber
        except ImportError as exc:  # pragma: no cover - dependency is installed in production/CI.
            raise RuntimeError("缺少 pdfplumber，无法提取财报表格") from exc

        pages: List[Dict[str, Any]] = []
        with pdfplumber.open(pdf_path) as pdf:
            for pdf_page, page in enumerate(pdf.pages, 1):
                text = page.extract_text(layout=True, x_tolerance=2, y_tolerance=2) or ""
                tables = page.extract_tables() or []
                if tables:
                    pages.append({"pdf_page": pdf_page, "text": text, "tables": tables})
        logger.debug(f"[财报补充数据] PDF表格提取完成: {pdf_path}, pages={len(pages)}")
        return pages
