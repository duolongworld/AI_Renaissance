"""
财务分析 Agent - 专家1组

signal_type: financial
Skill 域: skills/financial/
核心能力：财报质量七步验证链
"""

from datetime import datetime
from typing import Any, Optional

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal
from data_sources import EastMoneyDataSource, FinancialReportSupplementDataSource
from skills.financial.financial_report_analysis.scripts.analyze_report import build_signal


FINANCIAL_AGENT_VERSION = "0.3.0"


class FinancialAgent(BaseAgent):
    """
    财务分析 Agent（专家1组）

    加载 skills/financial/ 下所有 Skill，
    对指定股票进行深度财报分析，输出 financial 类型的 Signal。
    """

    signal_type = "financial"
    version = FINANCIAL_AGENT_VERSION

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="财务分析Agent", config=config or {})
        # 启动时自动加载 financial 领域的所有 Skill
        self.load_skills_from_domain("financial")
        self.data_source = (
            self.config.get("financial_data_source")
            or self.config.get("data_source")
            or EastMoneyDataSource()
        )
        self.include_report_supplement = self.config.get("include_report_supplement", True)
        self.report_data_source = None
        if self.include_report_supplement:
            self.report_data_source = (
                self.config.get("financial_report_data_source")
                or FinancialReportSupplementDataSource()
            )
        self._resolved_report_dates: dict[str, str] = {}

    def analyze(self, stock_code: str) -> Signal:
        """
        分析指定股票的财报质量

        Args:
            stock_code: 股票代码

        Returns:
            标准 Signal 对象（signal_type="financial"）
        """
        self.log(f"开始财报分析：{stock_code}")

        try:
            raw_data = self._fetch_data(stock_code)
            normalized_data = self._prepare_skill_input(stock_code, raw_data)
            signal = Signal.from_dict(build_signal(normalized_data))
            signal.source = self.name
            signal.signal_type = self.signal_type
            signal.meta["financial_agent_version"] = self.version
            if not signal.stock_code or signal.stock_code == "unknown":
                signal.stock_code = stock_code
            return signal
        except Exception as exc:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"财务分析执行失败：{exc}",
                source=self.name,
                stock_code=stock_code,
                signal_type=self.signal_type,
                meta={
                    "skill_name": "financial-report-analysis",
                    "needs_human_review": True,
                    "error": str(exc),
                },
            )

    def _fetch_data(self, stock_code: str) -> dict[str, Any]:
        """通过数据层获取财务数据。"""
        report_date = self._current_report_date(stock_code)
        if not self.data_source:
            return {}
        try:
            current_data = self.data_source.get_financial_data(stock_code, report_date=report_date) or {}
        except TypeError:
            current_data = self.data_source.get_financial_data(stock_code) or {}

        current_data = dict(current_data) if isinstance(current_data, dict) else {}
        self._merge_report_supplement(current_data, stock_code, report_date)

        if self.config.get("include_previous_period", True):
            previous_report_date = self._previous_report_date(report_date)
            if previous_report_date:
                try:
                    previous_data = self.data_source.get_financial_data(
                        stock_code, report_date=previous_report_date
                    ) or {}
                except Exception:
                    previous_data = {}
                if previous_data:
                    current_data["previous_period_data"] = previous_data
                    current_data["previous_report_date"] = previous_report_date
                if self.config.get("include_single_quarter_periods", True):
                    previous_previous_report_date = self._previous_report_date(previous_report_date)
                    if previous_previous_report_date:
                        try:
                            previous_previous_data = self.data_source.get_financial_data(
                                stock_code, report_date=previous_previous_report_date
                            ) or {}
                        except Exception:
                            previous_previous_data = {}
                        if previous_previous_data:
                            current_data["previous_previous_period_data"] = previous_previous_data
                            current_data["previous_previous_report_date"] = previous_previous_report_date
        return current_data

    def _merge_report_supplement(
        self,
        current_data: dict[str, Any],
        stock_code: str,
        report_date: Optional[str],
    ) -> None:
        """Merge current-period CNINFO fields without overriding statement data."""
        if not self.report_data_source or not report_date:
            return
        try:
            supplement = self.report_data_source.get_financial_supplement(stock_code, report_date) or {}
        except Exception as exc:
            supplement = {
                "status": "error",
                "report_date": report_date,
                "fields": {},
                "error": f"财报原文补充数据获取失败: {type(exc).__name__}: {exc}",
            }
        current_data["financial_report_supplement"] = supplement
        for field, value in (supplement.get("fields") or {}).items():
            current_data.setdefault(field, value)

    def _current_report_date(self, stock_code: Optional[str] = None) -> Optional[str]:
        report_date = self.config.get("report_date")
        if report_date:
            return report_date
        cache_key = str(stock_code or "__default__").strip().upper()
        if cache_key in self._resolved_report_dates:
            return self._resolved_report_dates[cache_key]
        if (
            self.report_data_source
            and self.config.get("prefer_cninfo_report_date", True)
            and hasattr(self.report_data_source, "resolve_latest_report_date")
        ):
            try:
                resolved = self.report_data_source.resolve_latest_report_date(
                    stock_code or self.config.get("stock_code_for_report_resolution", "")
                )
            except Exception:
                resolved = None
            if resolved:
                self._resolved_report_dates[cache_key] = resolved
                return resolved
        if hasattr(self.data_source, "_get_latest_report_date"):
            return self.data_source._get_latest_report_date()
        return None

    def _previous_report_date(self, report_date: Optional[str]) -> Optional[str]:
        if not report_date:
            return None
        try:
            current = datetime.strptime(report_date[:10], "%Y-%m-%d")
        except ValueError:
            return None

        previous_quarter = {
            (3, 31): (current.year - 1, 12, 31),
            (6, 30): (current.year, 3, 31),
            (9, 30): (current.year, 6, 30),
            (12, 31): (current.year, 9, 30),
        }.get((current.month, current.day))
        if not previous_quarter:
            return None
        return f"{previous_quarter[0]:04d}-{previous_quarter[1]:02d}-{previous_quarter[2]:02d}"

    def _prepare_skill_input(self, stock_code: str, raw_data: dict[str, Any]) -> dict[str, Any]:
        """把数据源输出包装成 financial-report-analysis 可消费的输入。"""
        data = dict(raw_data or {})
        data.setdefault("ticker", stock_code)
        data.setdefault("company_name", data.get("stock_name") or data.get("name") or "unknown")
        data.setdefault("period", self._current_report_date(stock_code) or "unknown")
        data.setdefault("source_type", "data_source")
        data.setdefault("source_name", getattr(self.data_source, "name", "unknown data source"))
        supplement = data.get("financial_report_supplement")
        if isinstance(supplement, dict) and supplement.get("fields"):
            supplement_name = (supplement.get("source") or {}).get("source_name") or "CNINFO"
            if supplement_name not in str(data["source_name"]):
                data["source_name"] = f'{data["source_name"]} + {supplement_name}'

        balance = data.get("balance")
        income = data.get("income")
        cashflow = data.get("cashflow")
        data.setdefault("balance_sheet_present", bool(balance))
        data.setdefault("income_statement_present", bool(income))
        data.setdefault("cash_flow_statement_present", bool(cashflow))

        if not any((balance, income, cashflow)):
            data["summary"] = "未取得完整三张表数据，财务 Signal 降为中性并转人工复核。"
        return data
