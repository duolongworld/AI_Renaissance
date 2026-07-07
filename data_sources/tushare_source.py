"""
Tushare 数据源封装（开发3组）

基于 Tushare Pro API，提供：
- 财务三大表（资产负债表、利润表、现金流量表）
- 个股日线行情
- 个股资金流向（需要 tushare 更高权限等级）
- 个股基础信息

使用方式：
    1. 注册 Tushare 账号：https://tushare.pro
    2. 获取 token
    3. 设置环境变量：export TUSHARE_TOKEN=your_token
    4. 或通过构造参数传入：TushareDataSource(token="your_token")

调用能力取决于个人 Tushare 账号的权限等级（积分越高可调用接口越多）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import os

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:  # pragma: no cover
    pd = None
    HAS_PANDAS = False

try:
    import tushare as ts

    HAS_TUSHARE = True
except ImportError:  # pragma: no cover
    ts = None
    HAS_TUSHARE = False

from .base import DataSourceBase


class TushareDataSource(DataSourceBase):
    """Tushare Pro 数据源

    通过 Tushare Pro API 获取金融数据。调用能力取决于个人 token 对应的权限等级。

    Token 获取方式（优先级从高到低）：
    1. 构造参数传入：TushareDataSource(token="xxx")
    2. 环境变量：export TUSHARE_TOKEN=xxx
    3. .env 文件：在项目根目录创建 .env，写入 TUSHARE_TOKEN=xxx
    """

    # tushare 股票代码格式：{code}.{exchange}，如 600519.SH、000001.SZ
    EXCHANGE_MAP = {"sh": "SH", "sz": "SZ", "bj": "BJ"}

    def __init__(self, token: Optional[str] = None):
        """
        Args:
            token: Tushare token。不传则从环境变量 TUSHARE_TOKEN 或 .env 文件中读取。
        """
        super().__init__(name="Tushare数据源")
        self._token: Optional[str] = token or self._resolve_token()
        self._pro: Any = None  # lazy init

    # ------------------------------------------------------------------
    # 基类抽象方法实现
    # ------------------------------------------------------------------

    def get_financial_data(
        self, stock_code: str, report_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取财务三大表数据。

        Returns:
            {"balance": [...], "income": [...], "cashflow": [...]}
        """
        ready = self._ensure_ready("financial_data", stock_code=stock_code)
        if ready:
            return ready

        ts_code = self._to_ts_code(stock_code)
        if not ts_code:
            return self._error_result("financial_data", f"无法识别股票代码：{stock_code}", stock_code=stock_code)

        end_date = report_date or self._latest_report_date()

        try:
            income = self._call_pro(
                "income",
                ts_code=ts_code,
                end_date=end_date,
                fields=self._income_fields(),
            )
        except Exception as e:
            income = None
            self.log(f"利润表获取失败：{e}", "warning")

        try:
            balance = self._call_pro(
                "balancesheet",
                ts_code=ts_code,
                end_date=end_date,
                fields=self._balance_fields(),
            )
        except Exception as e:
            balance = None
            self.log(f"资产负债表获取失败：{e}", "warning")

        try:
            cashflow = self._call_pro(
                "cashflow",
                ts_code=ts_code,
                end_date=end_date,
                fields=self._cashflow_fields(),
            )
        except Exception as e:
            cashflow = None
            self.log(f"现金流量表获取失败：{e}", "warning")

        if income is None and balance is None and cashflow is None:
            return self._error_result(
                "financial_data",
                "Tushare 财务三大表全部获取失败，可能原因：1) 该股票无财务数据 2) token 权限等级不足以调用财务接口（需要 2000 积分以上）",
                stock_code=ts_code,
            )

        records: Dict[str, Any] = {
            "status": "success",
            "source": "tushare",
            "dataset": "financial_data",
            "fetch_time": self._current_iso(),
            "stock_code": ts_code,
            "end_date": end_date,
            "income": self._frame_to_records(income),
            "balance": self._frame_to_records(balance),
            "cashflow": self._frame_to_records(cashflow),
        }
        warnings = []
        if income is None:
            warnings.append("利润表获取失败（可能权限不足）")
        if balance is None:
            warnings.append("资产负债表获取失败（可能权限不足）")
        if cashflow is None:
            warnings.append("现金流量表获取失败（可能权限不足）")
        if warnings:
            records["warnings"] = warnings
        return records

    def get_market_data(self, stock_code: str, period: str = "daily") -> Dict[str, Any]:
        """获取个股日线行情数据。

        Args:
            period: 周期，仅支持 daily
        """
        ready = self._ensure_ready("market_data", stock_code=stock_code)
        if ready:
            return ready

        ts_code = self._to_ts_code(stock_code)
        if not ts_code:
            return self._error_result("market_data", f"无法识别股票代码：{stock_code}", stock_code=stock_code)

        if period != "daily":
            return self._error_result(
                "market_data",
                f"Tushare 当前只支持 daily 周期，不支持的周期：{period}",
                stock_code=ts_code,
            )

        try:
            df = self._call_pro(
                "daily",
                ts_code=ts_code,
                fields=self._daily_fields(),
            )
        except Exception as e:
            return self._error_result("market_data", str(e), stock_code=ts_code)

        records = self._frame_to_records(df)
        return {
            "status": "success",
            "source": "tushare",
            "dataset": "market_data",
            "fetch_time": self._current_iso(),
            "stock_code": ts_code,
            "period": period,
            "total": len(records),
            "records": records,
        }

    def get_fund_flow_data(self, stock_code: str) -> Dict[str, Any]:
        """获取个股资金流向数据。

        注意：需要 tushare 积分 2000 以上才能调用 moneyflow 接口。
        """
        ready = self._ensure_ready("fund_flow_data", stock_code=stock_code)
        if ready:
            return ready

        ts_code = self._to_ts_code(stock_code)
        if not ts_code:
            return self._error_result("fund_flow_data", f"无法识别股票代码：{stock_code}", stock_code=stock_code)

        try:
            df = self._call_pro(
                "moneyflow",
                ts_code=ts_code,
                fields=self._moneyflow_fields(),
            )
        except Exception as e:
            return self._error_result(
                "fund_flow_data",
                f"Tushare 资金流向获取失败：{e}（注意：moneyflow 接口需要 2000 积分以上权限）",
                stock_code=ts_code,
            )

        records = self._frame_to_records(df)
        return {
            "status": "success",
            "source": "tushare",
            "dataset": "fund_flow_data",
            "fetch_time": self._current_iso(),
            "stock_code": ts_code,
            "total": len(records),
            "records": records,
        }

    # ------------------------------------------------------------------
    # 便捷方法（非基类接口，供 Agent 按需调用）
    # ------------------------------------------------------------------

    def get_stock_basic(self, stock_code: str) -> Dict[str, Any]:
        """获取个股基础信息（上市日期、行业、地区等）。"""
        ready = self._ensure_ready("stock_basic", stock_code=stock_code)
        if ready:
            return ready

        ts_code = self._to_ts_code(stock_code)
        if not ts_code:
            return self._error_result("stock_basic", f"无法识别股票代码：{stock_code}", stock_code=stock_code)

        try:
            df = self._call_pro(
                "stock_basic",
                ts_code=ts_code,
                fields="ts_code,name,area,industry,list_date,market,exchange,is_hs,list_status",
            )
        except Exception as e:
            return self._error_result("stock_basic", str(e), stock_code=ts_code)

        records = self._frame_to_records(df)
        if not records:
            return self._error_result("stock_basic", f"未找到股票：{ts_code}", stock_code=ts_code)

        return {
            "status": "success",
            "source": "tushare",
            "dataset": "stock_basic",
            "fetch_time": self._current_iso(),
            "stock_code": ts_code,
            "info": records[0],
        }

    def get_income(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """单独获取利润表（便捷方法）。"""
        return self.get_financial_data(stock_code, report_date)

    def get_balance(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """单独获取资产负债表（便捷方法）。"""
        return self.get_financial_data(stock_code, report_date)

    def get_cashflow(self, stock_code: str, report_date: Optional[str] = None) -> Dict[str, Any]:
        """单独获取现金流量表（便捷方法）。"""
        return self.get_financial_data(stock_code, report_date)

    def has_token(self) -> bool:
        """检查是否已配置 token。"""
        return bool(self._token)

    def get_token_status(self) -> Dict[str, Any]:
        """检查 token 是否有效、获取账号信息。

        无副作用：只是探测 token 是否可用。
        """
        if not self._token:
            return {"status": "error", "source": "tushare", "error": "未配置 Tushare token"}
        pro = self._get_pro()
        if pro is None:
            return {
                "status": "error",
                "source": "tushare",
                "error": "tushare 未安装，请执行 pip install tushare",
            }
        try:
            # 用 trade_cal 做 token 校验，该接口不限频，不会消耗 stock_basic 额度
            df = pro.trade_cal(exchange="SSE", start_date="20260101", end_date="20260101")
            if df is not None and not (hasattr(df, "empty") and df.empty):
                return {
                    "status": "success",
                    "source": "tushare",
                    "dataset": "token_status",
                    "message": "token 有效，Tushare 连接正常",
                }
            return {"status": "error", "source": "tushare", "error": "token 可能无效，接口返回为空"}
        except Exception as e:
            return {
                "status": "error",
                "source": "tushare",
                "error": f"token 校验失败：{e}（提示：check token 是否正确，或网络是否可达）",
            }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _resolve_token(self) -> Optional[str]:
        """从环境变量或 .env 文件中解析 token。

        优先级：TUSHARE_TOKEN 环境变量 > .env 文件
        """
        token = os.getenv("TUSHARE_TOKEN")
        if token:
            return token

        # 尝试从项目根目录 .env 读取
        try:
            from dotenv import load_dotenv

            env_paths = [
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
                os.path.join(os.getcwd(), ".env"),
            ]
            for env_path in env_paths:
                if os.path.isfile(env_path):
                    load_dotenv(env_path)
                    break
            token = os.getenv("TUSHARE_TOKEN")
            if token:
                self.log("从 .env 文件读取到 TUSHARE_TOKEN")
        except ImportError:
            pass  # python-dotenv 未安装，跳过

        return token or None

    def _get_pro(self):
        """惰性初始化 tushare pro_api。"""
        if self._pro is not None:
            return self._pro
        if not self._token:
            return None
        if not HAS_TUSHARE:
            return None
        self._pro = ts.pro_api(self._token)
        return self._pro

    def _ensure_ready(self, dataset: str, **extra: Any) -> Optional[Dict[str, Any]]:
        """检查 tushare 和 pandas 是否可用、token 是否配置。"""
        if not HAS_TUSHARE:
            return self._error_result(
                dataset,
                "tushare 未安装，请先执行 `pip install tushare`",
                **extra,
            )
        if not HAS_PANDAS:
            return self._error_result(
                dataset,
                "pandas 未安装，请先执行 `pip install pandas`",
                **extra,
            )
        if not self._token:
            return self._error_result(
                dataset,
                (
                    "未配置 Tushare token。获取方式："
                    "1) 注册 Tushare 账号 https://tushare.pro "
                    "2) 在「个人主页 - 接口TOKEN」获取 token "
                    "3) 复制项目根目录 .env.example 为 .env，将 your_token_here 替换为你的 token "
                    "或通过构造参数传入：TushareDataSource(token='your_token')"
                ),
                **extra,
            )
        return None

    def _error_result(self, dataset: str, error: str, **extra: Any) -> Dict[str, Any]:
        """统一错误返回格式。"""
        result = {
            "status": "error",
            "source": "tushare",
            "dataset": dataset,
            "fetch_time": self._current_iso(),
            "error": error,
        }
        result.update(extra)
        return result

    def _to_ts_code(self, code: str) -> str:
        """将通用股票代码转为 tushare 格式（如 600519 -> 600519.SH）。"""
        code = code.strip().upper()
        # 已经是 tushare 格式
        if "." in code and code.split(".")[-1] in ("SH", "SZ", "BJ"):
            return code
        # SH/SZ 前缀格式
        if code.startswith("SH"):
            return f"{code[2:]}.SH"
        if code.startswith("SZ"):
            return f"{code[2:]}.SZ"
        if code.startswith("BJ"):
            return f"{code[2:]}.BJ"
        # 6位纯数字
        if code.isdigit() and len(code) == 6:
            if code.startswith("6"):
                return f"{code}.SH"
            if code.startswith(("0", "3")):
                return f"{code}.SZ"
            if code.startswith(("4", "8")):
                return f"{code}.BJ"
        return ""

    def _call_pro(self, api_name: str, **kwargs) -> Any:
        """调用 tushare pro_api 接口，统一异常处理。"""
        pro = self._get_pro()
        if pro is None:
            raise RuntimeError("tushare pro_api 未初始化（token 缺失或 tushare 未安装）")
        fn = getattr(pro, api_name, None)
        if fn is None:
            raise ValueError(f"tushare 不支持接口：{api_name}")
        df = fn(**kwargs)
        if df is None or (HAS_PANDAS and isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError(f"接口 {api_name} 返回为空，可能权限不足或无此数据")
        return df

    def _frame_to_records(self, df) -> List[Dict[str, Any]]:
        """将 DataFrame 转为 dict 列表，处理 NaN 和日期类型。"""
        if df is None:
            return []
        if HAS_PANDAS and isinstance(df, pd.DataFrame):
            if df.empty:
                return []
            # 先转为 object 类型，确保 None 能正确存储不被转回 NaN
            cleaned = df.astype(object).where(pd.notna(df), None)
            return cleaned.to_dict(orient="records")
        return []

    def _current_iso(self) -> str:
        """返回 ISO 格式当前时间。"""
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    def _latest_report_date(self) -> Optional[str]:
        """推测最新报告期（最近一个季末）。"""
        now = datetime.now()
        quarter_end = ((now.month - 1) // 3) * 3
        if quarter_end == 0:
            year = now.year - 1
            month = 12
        else:
            year = now.year
            month = quarter_end
        return f"{year}{month:02d}31"

    # ------------------------------------------------------------------
    # 字段定义（按需返回常用字段，避免接口超载）
    # ------------------------------------------------------------------

    @staticmethod
    def _income_fields() -> str:
        return (
            "ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,"
            "total_revenue,revenue,oper_cost,operate_profit,total_profit,"
            "income_tax,n_income,n_income_attr_p,"
            "basic_eps,diluted_eps,"
            "total_revenue_yoy,operate_profit_yoy,n_income_yoy,basic_eps_yoy"
        )

    @staticmethod
    def _balance_fields() -> str:
        return (
            "ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,"
            "total_assets,total_liab,total_hldr_eqy_exc_min_int,"
            "total_cur_assets,total_cur_liab,"
            "money_cap,accounts_receiv,inventories,"
            "notes_receiv,accounts_payable,"
            "goodwill,"
            "total_assets_yoy,total_hldr_eqy_exc_min_int_yoy"
        )

    @staticmethod
    def _cashflow_fields() -> str:
        return (
            "ts_code,ann_date,f_ann_date,end_date,report_type,comp_type,"
            "c_fr_sale_sg,n_cashflow_act,"
            "n_cashflow_inv_act,n_cashflow_fin_act,"
            "free_cashflow,"
            "n_cashflow_act_yoy"
        )

    @staticmethod
    def _daily_fields() -> str:
        return (
            "ts_code,trade_date,open,high,low,close,pre_close,"
            "change,pct_chg,vol,amount"
        )

    @staticmethod
    def _moneyflow_fields() -> str:
        return (
            "ts_code,trade_date,buy_elg_amount,buy_elg_vol,"
            "buy_lg_amount,buy_lg_vol,buy_md_amount,buy_md_vol,"
            "buy_sm_amount,buy_sm_vol,buy_elg_amount,buy_lg_amount,"
            "sell_elg_amount,sell_lg_amount,sell_md_amount,sell_sm_amount,"
            "net_mf_amount,net_mf_vol,"
            "net_elg_amount,net_lg_amount,net_md_amount,net_sm_amount"
        )
