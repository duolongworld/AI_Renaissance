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
import time

import requests

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
    EASTMONEY_DELAY_HOST = "https://push2delay.eastmoney.com"
    EASTMONEY_HIS_HOST = "http://push2his.eastmoney.com"
    EASTMONEY_DATACENTER_HOST = "https://datacenter-web.eastmoney.com"
    EASTMONEY_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://data.eastmoney.com/",
    }

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
            info_df = self._fetch_stock_individual_info_em(code, market)
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
            df = self._fetch_stock_individual_fund_flow(code, market)
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
            industry_df = self._fetch_stock_sector_fund_flow_rank(indicator=indicator, sector_type="行业资金流")
            concept_df = self._fetch_stock_sector_fund_flow_rank(indicator=indicator, sector_type="概念资金流")
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
            market_df = self._fetch_stock_market_fund_flow()
            north_df = self._fetch_stock_hsgt_fund_flow_summary_em()
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

    def _request_json(self, url: str, params: Dict[str, Any], timeout: float = 15) -> Dict[str, Any]:
        """请求东方财富 JSON 接口。

        AkShare 1.18.x 里部分函数仍通过 HTTPS 访问 ``push2.eastmoney.com`` / ``push2his.eastmoney.com``，
        在当前环境会被服务端直接断开连接。这里保留 AkShare 的字段契约，但改为显式访问当前可用的
        东方财富接口域名：实时/板块使用 ``push2delay``，历史资金流使用 HTTP ``push2his``。
        """
        response = requests.get(url, params=params, headers=self.EASTMONEY_HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _fetch_stock_individual_info_em(self, code: str, market: str):
        market_code = 1 if market == "sh" else 0
        data_json = self._request_json(
            f"{self.EASTMONEY_DELAY_HOST}/api/qt/stock/get",
            {
                "fltt": "2",
                "invt": "2",
                "fields": "f57,f58,f84,f85,f127,f116,f117,f189,f43",
                "secid": f"{market_code}.{code}",
                "_": int(time.time() * 1000),
            },
        )
        data = data_json.get("data") or {}
        if not data:
            raise ValueError(f"东方财富未返回个股基础信息：{code}")
        code_name_map = {
            "f57": "股票代码",
            "f58": "股票简称",
            "f84": "总股本",
            "f85": "流通股",
            "f127": "行业",
            "f116": "总市值",
            "f117": "流通市值",
            "f189": "上市时间",
            "f43": "最新",
        }
        rows = [{"item": name, "value": data.get(field)} for field, name in code_name_map.items()]
        return pd.DataFrame(rows)

    def _fetch_stock_individual_fund_flow(self, code: str, market: str):
        market_map = {"sh": 1, "sz": 0, "bj": 0}
        data_json = self._request_json(
            f"{self.EASTMONEY_HIS_HOST}/api/qt/stock/fflow/daykline/get",
            {
                "lmt": "0",
                "klt": "101",
                "secid": f"{market_map[market]}.{code}",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
                "_": int(time.time() * 1000),
            },
        )
        klines = ((data_json.get("data") or {}).get("klines")) or []
        if not klines:
            raise ValueError(f"东方财富未返回个股资金流：{code}")
        temp_df = pd.DataFrame([item.split(",") for item in klines])
        temp_df.columns = [
            "日期",
            "主力净流入-净额",
            "小单净流入-净额",
            "中单净流入-净额",
            "大单净流入-净额",
            "超大单净流入-净额",
            "主力净流入-净占比",
            "小单净流入-净占比",
            "中单净流入-净占比",
            "大单净流入-净占比",
            "超大单净流入-净占比",
            "收盘价",
            "涨跌幅",
            "-",
            "--",
        ]
        temp_df = temp_df[
            [
                "日期",
                "收盘价",
                "涨跌幅",
                "主力净流入-净额",
                "主力净流入-净占比",
                "超大单净流入-净额",
                "超大单净流入-净占比",
                "大单净流入-净额",
                "大单净流入-净占比",
                "中单净流入-净额",
                "中单净流入-净占比",
                "小单净流入-净额",
                "小单净流入-净占比",
            ]
        ]
        return self._coerce_fund_flow_frame(temp_df, ["收盘价", "涨跌幅"])

    def _fetch_stock_market_fund_flow(self):
        data_json = self._request_json(
            f"{self.EASTMONEY_HIS_HOST}/api/qt/stock/fflow/daykline/get",
            {
                "lmt": "0",
                "klt": "101",
                "secid": "1.000001",
                "secid2": "0.399001",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
                "ut": "b2884a393a59ad64002292a3e90d46a5",
                "_": int(time.time() * 1000),
            },
        )
        klines = ((data_json.get("data") or {}).get("klines")) or []
        if not klines:
            raise ValueError("东方财富未返回大盘资金流")
        temp_df = pd.DataFrame([item.split(",") for item in klines])
        temp_df.columns = [
            "日期",
            "主力净流入-净额",
            "小单净流入-净额",
            "中单净流入-净额",
            "大单净流入-净额",
            "超大单净流入-净额",
            "主力净流入-净占比",
            "小单净流入-净占比",
            "中单净流入-净占比",
            "大单净流入-净占比",
            "超大单净流入-净占比",
            "上证-收盘价",
            "上证-涨跌幅",
            "深证-收盘价",
            "深证-涨跌幅",
        ]
        ordered = [
            "日期",
            "上证-收盘价",
            "上证-涨跌幅",
            "深证-收盘价",
            "深证-涨跌幅",
            "主力净流入-净额",
            "主力净流入-净占比",
            "超大单净流入-净额",
            "超大单净流入-净占比",
            "大单净流入-净额",
            "大单净流入-净占比",
            "中单净流入-净额",
            "中单净流入-净占比",
            "小单净流入-净额",
            "小单净流入-净占比",
        ]
        return self._coerce_fund_flow_frame(temp_df[ordered], ["上证-收盘价", "上证-涨跌幅", "深证-收盘价", "深证-涨跌幅"])

    def _coerce_fund_flow_frame(self, df, extra_numeric_fields: List[str]):
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
        numeric_fields = [
            "主力净流入-净额",
            "小单净流入-净额",
            "中单净流入-净额",
            "大单净流入-净额",
            "超大单净流入-净额",
            "主力净流入-净占比",
            "小单净流入-净占比",
            "中单净流入-净占比",
            "大单净流入-净占比",
            "超大单净流入-净占比",
            *extra_numeric_fields,
        ]
        for field in numeric_fields:
            if field in df.columns:
                df[field] = pd.to_numeric(df[field], errors="coerce")
        return df

    def _fetch_stock_sector_fund_flow_rank(self, indicator: str = "今日", sector_type: str = "行业资金流"):
        sector_type_map = {"行业资金流": "2", "概念资金流": "3", "地域资金流": "1"}
        indicator_map = {
            "今日": {
                "fid0": "f62",
                "stat": "1",
                "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124",
                "columns": {
                    "f14": "名称",
                    "f3": "今日涨跌幅",
                    "f62": "今日主力净流入-净额",
                    "f184": "今日主力净流入-净占比",
                    "f66": "今日超大单净流入-净额",
                    "f69": "今日超大单净流入-净占比",
                    "f72": "今日大单净流入-净额",
                    "f75": "今日大单净流入-净占比",
                    "f78": "今日中单净流入-净额",
                    "f81": "今日中单净流入-净占比",
                    "f84": "今日小单净流入-净额",
                    "f87": "今日小单净流入-净占比",
                    "f204": "今日主力净流入最大股",
                },
                "sort": "今日主力净流入-净额",
            },
            "5日": {
                "fid0": "f164",
                "stat": "5",
                "fields": "f12,f14,f2,f109,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f257,f258,f124",
                "columns": {
                    "f14": "名称",
                    "f109": "5日涨跌幅",
                    "f164": "5日主力净流入-净额",
                    "f165": "5日主力净流入-净占比",
                    "f166": "5日超大单净流入-净额",
                    "f167": "5日超大单净流入-净占比",
                    "f168": "5日大单净流入-净额",
                    "f169": "5日大单净流入-净占比",
                    "f170": "5日中单净流入-净额",
                    "f171": "5日中单净流入-净占比",
                    "f172": "5日小单净流入-净额",
                    "f173": "5日小单净流入-净占比",
                    "f257": "5日主力净流入最大股",
                },
                "sort": "5日主力净流入-净额",
            },
            "10日": {
                "fid0": "f174",
                "stat": "10",
                "fields": "f12,f14,f2,f160,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f260,f261,f124",
                "columns": {
                    "f14": "名称",
                    "f160": "10日涨跌幅",
                    "f174": "10日主力净流入-净额",
                    "f175": "10日主力净流入-净占比",
                    "f176": "10日超大单净流入-净额",
                    "f177": "10日超大单净流入-净占比",
                    "f178": "10日大单净流入-净额",
                    "f179": "10日大单净流入-净占比",
                    "f180": "10日中单净流入-净额",
                    "f181": "10日中单净流入-净占比",
                    "f182": "10日小单净流入-净额",
                    "f183": "10日小单净流入-净占比",
                    "f260": "10日主力净流入最大股",
                },
                "sort": "10日主力净流入-净额",
            },
        }
        config = indicator_map[indicator]
        params = {
            "pn": "1",
            "pz": "100",
            "po": "1",
            "np": "1",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fltt": "2",
            "invt": "2",
            "fid0": config["fid0"],
            "fs": f"m:90 t:{sector_type_map[sector_type]}",
            "stat": config["stat"],
            "fields": config["fields"],
            "rt": "52975239",
            "_": int(time.time() * 1000),
        }
        first_page = self._request_json(f"{self.EASTMONEY_DELAY_HOST}/api/qt/clist/get", params)
        total = ((first_page.get("data") or {}).get("total")) or 0
        total_page = max(1, math.ceil(total / 100))
        rows = list(((first_page.get("data") or {}).get("diff")) or [])
        for page in range(2, total_page + 1):
            params.update({"pn": page})
            page_json = self._request_json(f"{self.EASTMONEY_DELAY_HOST}/api/qt/clist/get", params)
            rows.extend(((page_json.get("data") or {}).get("diff")) or [])
        if not rows:
            raise ValueError(f"东方财富未返回{sector_type}排名")
        temp_df = pd.DataFrame(rows)
        temp_df = temp_df.rename(columns=config["columns"])
        keep_columns = ["名称", *[value for value in config["columns"].values() if value != "名称"]]
        temp_df = temp_df[[column for column in keep_columns if column in temp_df.columns]].copy()
        for column in temp_df.columns:
            if column != "名称" and not column.endswith("最大股"):
                temp_df[column] = pd.to_numeric(temp_df[column], errors="coerce")
        sort_column = config["sort"]
        if sort_column in temp_df.columns:
            temp_df.sort_values([sort_column], ascending=False, inplace=True)
        temp_df.reset_index(drop=True, inplace=True)
        temp_df.insert(0, "序号", range(1, len(temp_df) + 1))
        return temp_df

    def _fetch_stock_hsgt_fund_flow_summary_em(self):
        data_json = self._request_json(
            f"{self.EASTMONEY_DATACENTER_HOST}/api/data/v1/get",
            {
                "reportName": "RPT_MUTUAL_QUOTA",
                "columns": "TRADE_DATE,MUTUAL_TYPE,BOARD_TYPE,MUTUAL_TYPE_NAME,FUNDS_DIRECTION,INDEX_CODE,INDEX_NAME,BOARD_CODE",
                "quoteColumns": "status~07~BOARD_CODE,dayNetAmtIn~07~BOARD_CODE,dayAmtRemain~07~BOARD_CODE,"
                "dayAmtThreshold~07~BOARD_CODE,f104~07~BOARD_CODE,f105~07~BOARD_CODE,"
                "f106~07~BOARD_CODE,f3~03~INDEX_CODE~INDEX_f3,netBuyAmt~07~BOARD_CODE",
                "quoteType": "0",
                "pageNumber": "1",
                "pageSize": "2000",
                "sortTypes": "1",
                "sortColumns": "MUTUAL_TYPE",
                "source": "WEB",
                "client": "WEB",
            },
        )
        rows = ((data_json.get("result") or {}).get("data")) or []
        if not rows:
            raise ValueError("东方财富未返回沪深港通资金流")
        temp_df = pd.DataFrame(rows).rename(
            columns={
                "TRADE_DATE": "交易日",
                "BOARD_TYPE": "类型",
                "MUTUAL_TYPE_NAME": "板块",
                "FUNDS_DIRECTION": "资金方向",
                "status": "交易状态",
                "netBuyAmt": "成交净买额",
                "dayNetAmtIn": "资金净流入",
                "dayAmtRemain": "当日资金余额",
                "f104": "上涨数",
                "f106": "持平数",
                "f105": "下跌数",
                "INDEX_NAME": "相关指数",
                "INDEX_f3": "指数涨跌幅",
            }
        )
        columns = [
            "交易日",
            "类型",
            "板块",
            "资金方向",
            "交易状态",
            "成交净买额",
            "资金净流入",
            "当日资金余额",
            "上涨数",
            "持平数",
            "下跌数",
            "相关指数",
            "指数涨跌幅",
        ]
        temp_df = temp_df[[column for column in columns if column in temp_df.columns]].copy()
        temp_df["交易日"] = pd.to_datetime(temp_df["交易日"], errors="coerce").dt.date
        for column in ["成交净买额", "资金净流入", "当日资金余额", "上涨数", "持平数", "下跌数", "指数涨跌幅"]:
            if column in temp_df.columns:
                temp_df[column] = pd.to_numeric(temp_df[column], errors="coerce")
        for column in ["成交净买额", "资金净流入", "当日资金余额"]:
            if column in temp_df.columns:
                temp_df[column] = temp_df[column] / 10000
        return temp_df

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
