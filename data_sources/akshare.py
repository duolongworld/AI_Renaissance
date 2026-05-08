"""
AkShare 数据源封装（开发3组）

封装 AkShare 中与资金流向 Agent 最相关的能力：
- 个股基础信息（市值、行业、概念、入选指数等）
- 个股主力资金流向
- 行业 / 概念板块资金流
- 大盘主力资金与北向资金概览
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple
import math

try:
    import pandas as pd
except ImportError:  # pragma: no cover - 运行环境缺失依赖时兜底
    pd = None

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:  # pragma: no cover - 运行环境缺失依赖时兜底
    ak = None
    HAS_AKSHARE = False

from .base import DataSourceBase


class AkshareDataSource(DataSourceBase):
    """AkShare 数据源"""

    VALID_MARKET_FLOW_INDICATORS = {"今日", "5日", "10日"}

    def __init__(self):
        super().__init__(name="AkShare数据源")

    def get_financial_data(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """AkShare 数据源当前不承担财务三大表能力。"""
        self.log(f"AkShare 暂不支持财务三大表接口：{stock_code}", "warning")
        return {}

    def get_market_data(self, stock_code: str, period: str = "daily") -> Dict[str, Any]:
        """兼容基类接口：返回个股基础信息。"""
        return self.get_stock_basic_info(stock_code)

    def get_fund_flow_data(self, stock_code: str) -> Dict[str, Any]:
        """兼容基类接口：返回个股主力资金流向。"""
        return self.get_stock_fund_flow(stock_code)

    def get_stock_basic_info(self, stock_code: str, concept_limit: int = 10) -> Dict[str, Any]:
        """获取个股基础信息、市值、行业、概念和指数板块。"""
        ready = self._ensure_ready("stock_basic_info", stock_code=stock_code)
        if ready:
            return ready

        code, market, market_symbol = self._normalize_stock_input(stock_code)
        if not code:
            return self._error_result(
                "stock_basic_info",
                f"无法识别股票代码：{stock_code}",
                stock_code=stock_code,
            )

        try:
            info_df = ak.stock_individual_info_em(symbol=code)
        except Exception as e:
            return self._error_result(
                "stock_basic_info",
                f"AkShare 获取个股基础信息失败：{e}",
                stock_code=code,
                market=market,
            )

        info_map = self._frame_to_key_value(info_df, "item", "value")
        profile: Dict[str, Any] = {}
        concept_records: List[Dict[str, Any]] = []
        partial_errors: List[str] = []

        try:
            profile_df = ak.stock_profile_cninfo(symbol=code)
            profile = self._first_row_dict(profile_df)
        except Exception as e:
            partial_errors.append(f"cninfo 公司档案获取失败：{e}")
            self.log(f"AkShare 个股基础信息降级：{code} 的 cninfo 公司档案获取失败：{e}", "warning")

        try:
            concept_df = ak.stock_hot_keyword_em(symbol=market_symbol)
            concept_records = self._frame_to_records(concept_df)
        except Exception as e:
            partial_errors.append(f"热门概念标签获取失败：{e}")
            self.log(f"AkShare 个股基础信息降级：{code} 的热门概念标签获取失败：{e}", "warning")

        concept_records.sort(key=lambda item: item.get("热度") or 0, reverse=True)
        concept_records = concept_records[: max(0, concept_limit)]

        stock_name = (
            info_map.get("股票简称")
            or profile.get("A股简称")
            or profile.get("公司名称")
            or code
        )
        industry = info_map.get("行业") or profile.get("所属行业")
        listing_date = self._format_cn_date(info_map.get("上市时间") or profile.get("上市日期"))
        index_memberships = self._split_text_items(profile.get("入选指数"))

        result = {
            "status": "success",
            "source": "akshare",
            "dataset": "stock_basic_info",
            "fetch_time": self._current_display_date(),
            "stock_code": code,
            "market": market,
            "stock_name": stock_name,
            "profile": {
                "股票代码": code,
                "股票名称": stock_name,
                "最新价": self._to_number(info_map.get("最新")),
                "总股本": self._to_number(info_map.get("总股本")),
                "流通股": self._to_number(info_map.get("流通股")),
                "总市值": self._to_number(info_map.get("总市值")),
                "流通市值": self._to_number(info_map.get("流通市值")),
                "所属行业": industry,
                "所属市场": profile.get("所属市场"),
                "上市日期": listing_date,
                "公司名称": profile.get("公司名称"),
                "法人代表": profile.get("法人代表"),
                "注册资金": self._to_number(profile.get("注册资金")),
                "主营业务": profile.get("主营业务"),
                "经营范围": profile.get("经营范围"),
                "官方网站": profile.get("官方网站"),
                "电子邮箱": profile.get("电子邮箱"),
                "联系电话": profile.get("联系电话"),
                "注册地址": profile.get("注册地址"),
                "办公地址": profile.get("办公地址"),
            },
            "boards": {
                "行业板块": industry,
                "入选指数": index_memberships,
            },
            "concepts": [
                {
                    "概念名称": item.get("概念名称"),
                    "概念代码": item.get("概念代码"),
                    "热度": self._to_number(item.get("热度")),
                    "时间": self._normalize_value(item.get("时间")),
                }
                for item in concept_records
            ],
            "raw": {
                "eastmoney_quote": info_map,
                "cninfo_profile": profile,
            },
        }
        if partial_errors:
            result["warnings"] = partial_errors
        return result

    def get_stock_fund_flow(self, stock_code: str, limit: int = 20) -> Dict[str, Any]:
        """获取个股主力资金流向明细。"""
        ready = self._ensure_ready("stock_fund_flow", stock_code=stock_code)
        if ready:
            return ready

        code, market, _ = self._normalize_stock_input(stock_code)
        if not code:
            return self._error_result(
                "stock_fund_flow",
                f"无法识别股票代码：{stock_code}",
                stock_code=stock_code,
            )

        try:
            df = ak.stock_individual_fund_flow(stock=code, market=market)
        except Exception as e:
            return self._error_result(
                "stock_fund_flow",
                f"AkShare 获取个股资金流失败：{e}",
                stock_code=code,
                market=market,
            )

        records = self._frame_to_records(df)
        latest = records[-1] if records else {}
        recent = list(reversed(records[-max(limit, 1) :]))

        result = {
            "status": "success",
            "source": "akshare",
            "dataset": "stock_fund_flow",
            "fetch_time": self._current_display_date(),
            "stock_code": code,
            "market": market,
            "total": len(records),
            "latest": latest,
            "recent": recent,
            "summary": {
                "最新收盘价": latest.get("收盘价"),
                "最新涨跌幅": latest.get("涨跌幅"),
                "最新主力净流入": latest.get("主力净流入-净额"),
                "最新主力净流入占比": latest.get("主力净流入-净占比"),
                "最新超大单净流入": latest.get("超大单净流入-净额"),
                "最新大单净流入": latest.get("大单净流入-净额"),
                "近3日主力净流入": self._sum_window(records, "主力净流入-净额", 3),
                "近5日主力净流入": self._sum_window(records, "主力净流入-净额", 5),
                "近10日主力净流入": self._sum_window(records, "主力净流入-净额", 10),
            },
        }
        return result

    def get_sector_fund_flow(
        self,
        stock_code: Optional[str] = None,
        indicator: str = "今日",
        top_n: int = 20,
        concept_limit: int = 10,
    ) -> Dict[str, Any]:
        """获取行业 / 概念板块资金流排名，可附带股票关联板块。"""
        ready = self._ensure_ready("sector_fund_flow", stock_code=stock_code)
        if ready:
            return ready

        indicator = self._normalize_indicator(indicator)
        if indicator not in self.VALID_MARKET_FLOW_INDICATORS:
            return self._error_result(
                "sector_fund_flow",
                f"indicator 仅支持 {sorted(self.VALID_MARKET_FLOW_INDICATORS)}，当前为：{indicator}",
                stock_code=stock_code,
            )

        try:
            industry_df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type="行业资金流")
            concept_df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type="概念资金流")
        except Exception as e:
            return self._error_result(
                "sector_fund_flow",
                f"AkShare 获取板块资金流失败：{e}",
                stock_code=stock_code,
                indicator=indicator,
            )

        industry_rankings = self._frame_to_records(industry_df)[: max(top_n, 1)]
        concept_rankings = self._frame_to_records(concept_df)[: max(top_n, 1)]
        fetch_time = self._current_display_date()
        industry_rankings = [self._attach_sector_meta(item, indicator, "行业资金流") for item in industry_rankings]
        concept_rankings = [self._attach_sector_meta(item, indicator, "概念资金流") for item in concept_rankings]

        result: Dict[str, Any] = {
            "status": "success",
            "source": "akshare",
            "dataset": "sector_fund_flow",
            "fetch_time": fetch_time,
            "indicator": indicator,
            "top_n": max(top_n, 1),
            "industry_rankings": industry_rankings,
            "concept_rankings": concept_rankings,
        }

        if stock_code:
            basic_info = self.get_stock_basic_info(stock_code=stock_code, concept_limit=concept_limit)
            if basic_info.get("status") == "success":
                industry_name = basic_info.get("boards", {}).get("行业板块") or basic_info.get("profile", {}).get("所属行业")
                concept_names = [
                    item.get("概念名称")
                    for item in basic_info.get("concepts", [])
                    if item.get("概念名称")
                ]
                result["stock_context"] = {
                    "stock_code": basic_info.get("stock_code"),
                    "stock_name": basic_info.get("stock_name"),
                    "industry": industry_name,
                    "concepts": concept_names,
                }
                result["related_industry_rankings"] = self._filter_rankings(industry_rankings, [industry_name])
                result["related_concept_rankings"] = self._filter_rankings(concept_rankings, concept_names)
            else:
                result["stock_context_error"] = basic_info.get("error")

        return result

    def get_market_fund_flow(self, limit: int = 20) -> Dict[str, Any]:
        """获取大盘主力资金流与北向资金概览。"""
        ready = self._ensure_ready("market_fund_flow")
        if ready:
            return ready

        try:
            market_df = ak.stock_market_fund_flow()
            north_df = ak.stock_hsgt_fund_flow_summary_em()
        except Exception as e:
            return self._error_result("market_fund_flow", f"AkShare 获取大盘/北向资金失败：{e}")

        market_records = self._frame_to_records(market_df)
        north_records = self._frame_to_records(north_df)
        latest_market = market_records[-1] if market_records else {}
        recent_market = list(reversed(market_records[-max(limit, 1) :]))

        latest_trade_date = self._latest_trade_date(north_records)
        latest_north_rows = [item for item in north_records if item.get("交易日") == latest_trade_date]
        northbound_rows = [item for item in latest_north_rows if item.get("资金方向") == "北向"]
        southbound_rows = [item for item in latest_north_rows if item.get("资金方向") == "南向"]

        result = {
            "status": "success",
            "source": "akshare",
            "dataset": "market_fund_flow",
            "fetch_time": self._current_display_date(),
            "market_main_flow": {
                "total": len(market_records),
                "latest": latest_market,
                "recent": recent_market,
            },
            "northbound": {
                "trade_date": latest_trade_date,
                "northbound_net_buy": self._sum_records(northbound_rows, "成交净买额"),
                "northbound_net_inflow": self._sum_records(northbound_rows, "资金净流入"),
                "southbound_net_buy": self._sum_records(southbound_rows, "成交净买额"),
                "southbound_net_inflow": self._sum_records(southbound_rows, "资金净流入"),
                "breakdown": latest_north_rows,
            },
        }
        return result

    def get_fundflow_snapshot(
        self,
        stock_code: str,
        indicator: str = "今日",
        flow_limit: int = 20,
        sector_top_n: int = 20,
        concept_limit: int = 10,
    ) -> Dict[str, Any]:
        """为资金流向 Agent 聚合一份可直接消费的数据快照。"""
        return {
            "status": "success",
            "source": "akshare",
            "dataset": "fundflow_snapshot",
            "fetch_time": self._current_display_date(),
            "stock_code": stock_code,
            "basic_info": self.get_stock_basic_info(stock_code=stock_code, concept_limit=concept_limit),
            "stock_fund_flow": self.get_stock_fund_flow(stock_code=stock_code, limit=flow_limit),
            "sector_fund_flow": self.get_sector_fund_flow(
                stock_code=stock_code,
                indicator=indicator,
                top_n=sector_top_n,
                concept_limit=concept_limit,
            ),
            "market_fund_flow": self.get_market_fund_flow(limit=flow_limit),
        }

    def _ensure_ready(self, dataset: str, **extra: Any) -> Optional[Dict[str, Any]]:
        if not HAS_AKSHARE:
            return self._error_result(dataset, "akshare 未安装，请先执行 `pip install akshare`", **extra)
        if pd is None:
            return self._error_result(dataset, "pandas 未安装，请先执行 `pip install pandas`", **extra)
        return None

    def _error_result(self, dataset: str, error: str, **extra: Any) -> Dict[str, Any]:
        result = {
            "status": "error",
            "source": "akshare",
            "dataset": dataset,
            "fetch_time": self._current_display_date(),
            "error": error,
        }
        result.update(extra)
        return result

    def _normalize_stock_input(self, stock_code: str) -> Tuple[str, str, str]:
        raw = (stock_code or "").strip().upper()
        if raw.startswith(("SH", "SZ", "BJ")) and len(raw) >= 8:
            market = raw[:2].lower()
            code = raw[2:]
        elif raw.isdigit() and len(raw) == 6:
            code = raw
            if raw.startswith("6"):
                market = "sh"
            elif raw.startswith(("0", "3")):
                market = "sz"
            elif raw.startswith(("4", "8")):
                market = "bj"
            else:
                return "", "", ""
        else:
            return "", "", ""
        return code, market, f"{market.upper()}{code}"

    def _frame_to_key_value(self, df, key_col: str, value_col: str) -> Dict[str, Any]:
        if df is None or getattr(df, "empty", True):
            return {}
        result = {}
        for _, row in df.iterrows():
            key = row.get(key_col)
            if key is None:
                continue
            result[str(key)] = self._normalize_value(row.get(value_col))
        return result

    def _first_row_dict(self, df) -> Dict[str, Any]:
        if df is None or getattr(df, "empty", True):
            return {}
        row = df.iloc[0].to_dict()
        return {str(k): self._normalize_value(v) for k, v in row.items()}

    def _frame_to_records(self, df) -> List[Dict[str, Any]]:
        if df is None or getattr(df, "empty", True):
            return []
        records = []
        for item in df.to_dict(orient="records"):
            records.append({str(k): self._normalize_value(v) for k, v in item.items()})
        return records

    def _normalize_value(self, value: Any) -> Any:
        if pd is not None and pd.isna(value):
            return None
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                pass
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            return self._format_chinese_date(value)
        if isinstance(value, date):
            return self._format_chinese_date(datetime.combine(value, datetime.min.time()))
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        if isinstance(value, str):
            formatted = self._try_format_datetime_string(value)
            return formatted if formatted else value
        return value

    def _to_number(self, value: Any) -> Optional[float]:
        value = self._normalize_value(value)
        if value in (None, "", "--"):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", ""))
            except ValueError:
                return None
        return None

    def _format_cn_date(self, value: Any) -> Optional[str]:
        value = self._normalize_value(value)
        if value in (None, "", "--"):
            return None
        text = str(value)
        if len(text) == 8 and text.isdigit():
            dt = datetime.strptime(text, "%Y%m%d")
            return self._format_chinese_date(dt)
        return text

    def _format_chinese_date(self, value: datetime) -> str:
        return value.strftime("%Y年%m月%d日")

    def _current_display_date(self) -> str:
        return self._format_chinese_date(datetime.now())

    def _try_format_datetime_string(self, value: str) -> Optional[str]:
        text = value.strip()
        if not text:
            return None
        patterns = [
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        for pattern in patterns:
            try:
                dt = datetime.strptime(text, pattern)
                return self._format_chinese_date(dt)
            except ValueError:
                continue
        return None

    def _split_text_items(self, value: Any) -> List[str]:
        value = self._normalize_value(value)
        if not value:
            return []
        text = str(value).replace("，", ",")
        return [item.strip() for item in text.split(",") if item.strip()]

    def _sum_window(self, records: List[Dict[str, Any]], field: str, window: int) -> Optional[float]:
        if not records:
            return None
        return self._sum_records(records[-window:], field)

    def _sum_records(self, records: List[Dict[str, Any]], field: str) -> Optional[float]:
        total = 0.0
        found = False
        for item in records:
            value = self._to_number(item.get(field))
            if value is None:
                continue
            total += value
            found = True
        return total if found else None

    def _filter_rankings(self, records: List[Dict[str, Any]], names: List[Optional[str]]) -> List[Dict[str, Any]]:
        name_set = {str(name).strip() for name in names if name}
        if not name_set:
            return []
        return [item for item in records if str(item.get("名称", "")).strip() in name_set]

    def _attach_sector_meta(
        self,
        item: Dict[str, Any],
        indicator: str,
        sector_type: str,
    ) -> Dict[str, Any]:
        row = dict(item)
        row.setdefault("统计口径", indicator)
        row.setdefault("榜单类型", sector_type)
        return row

    def _latest_trade_date(self, records: List[Dict[str, Any]]) -> Optional[str]:
        dates = [str(item.get("交易日")) for item in records if item.get("交易日")]
        return max(dates) if dates else None

    def _normalize_indicator(self, indicator: str) -> str:
        text = (indicator or "今日").strip()
        mapping = {
            "today": "今日",
            "5d": "5日",
            "10d": "10日",
        }
        return mapping.get(text.lower(), text)
