"""
Industrial Sentinel 专用复合数据源

为 IndustryAgent 提供统一的数据获取入口：
- 行业情绪数据（通过 IndustrySentimentDataSource）
- 财务数据（通过 EastMoneyDataSource）

设计原则（与项目 data_sources/ 层对齐）：
- 真实 fetching / parsing / provider 逻辑放在本层
- 网络异常时自动降级到本地缓存
- 缓存文件放在 data_sources/data/industrial_sentinel/ 下
- 返回统一格式的 dict，直接供 runtime._build_real_data 消费
- Agent 负责把数据缺失场景降级为框架级 preset fallback
"""

from typing import Any, Dict, Optional
from pathlib import Path
import json
from loguru import logger

# ── 底层数据源（项目共用） ──
try:
    from data_sources.industry_sentiment import IndustrySentimentDataSource
except Exception:
    IndustrySentimentDataSource = None

try:
    from data_sources.eastmoney import EastMoneyDataSource
except Exception:
    EastMoneyDataSource = None


class IndustrialSentinelDataSource:
    """Industrial Sentinel 复合数据源

    封装 IndustryAgent 所需的全部数据获取逻辑：
    1. 行业情绪（IndustrySentimentDataSource）
    2. 财务数据（EastMoneyDataSource）

    网络异常时自动降级到本地缓存，确保 Agent 始终有数据可用。
    """

    def __init__(
        self,
        industry_data_source: Optional[Any] = None,
        financial_data_source: Optional[Any] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.name = "IndustrialSentinel数据源"
        self._industry_ds = (
            industry_data_source
            if industry_data_source is not None
            else IndustrySentimentDataSource() if IndustrySentimentDataSource else None
        )
        self._financial_ds = (
            financial_data_source
            if financial_data_source is not None
            else EastMoneyDataSource() if EastMoneyDataSource else None
        )
        self._cache_dir = Path(cache_dir) if cache_dir else self._find_cache_dir()
        logger.info(f"[{self.name}] 初始化完成 (industry={self._industry_ds is not None}, financial={self._financial_ds is not None})")

    def get_data(self, stock_code: str) -> Dict[str, Any]:
        """获取 IndustryAgent 所需的全部数据。

        Args:
            stock_code: 股票代码，如 "002916.SZ"

        Returns:
            {
                "industry_result": {...} | None,  # 行业情绪数据
                "financial_data": {...} | None,   # 财务数据
                "industry_from_cache": bool,       # 行业数据是否来自缓存
                "financial_from_cache": bool,      # 财务数据是否来自缓存
                "degradation_reasons": [...],      # 降级原因列表（供 Agent 提示使用者）
            }
        """
        industry_result, industry_from_cache, industry_reason = self._get_industry_data(stock_code)
        financial_data, financial_from_cache, financial_reason = self._get_financial_data(stock_code)

        degradation_reasons = []
        if industry_reason:
            degradation_reasons.append(industry_reason)
        if financial_reason:
            degradation_reasons.append(financial_reason)

        industry_status = self._classify_industry_status(
            industry_result, industry_from_cache
        )
        financial_status = self._classify_financial_status(
            financial_data, financial_from_cache
        )

        return {
            "industry_result": industry_result,
            "financial_data": financial_data,
            "industry_from_cache": industry_from_cache,
            "financial_from_cache": financial_from_cache,
            "industry_status": industry_status,
            "financial_status": financial_status,
            "degradation_reasons": degradation_reasons,
        }

    # ── 行业情绪数据 ──

    def _get_industry_data(self, stock_code: str) -> tuple[Optional[Dict[str, Any]], bool, str]:
        """获取行业情绪数据，带缓存降级。

        Returns:
            (data_dict, from_cache, degradation_reason)
            degradation_reason: 空字符串表示无降级，否则为降级原因描述
        """
        # 1. 尝试实时获取
        if self._industry_ds:
            try:
                result = self._industry_ds.get_industry_sentiment(stock_code)
                if result and result.get("status") == "success":
                    self._save_cache(f"{stock_code}_industry", result)
                    logger.info(f"[{self.name}] 行业数据实时获取成功")
                    return result, False, ""
            except Exception as e:
                logger.warning(f"[{self.name}] 行业数据实时获取失败: {e}")

        # 2. 降级到缓存
        cached = self._load_cache(f"{stock_code}_industry")
        if cached and self._has_industry_payload(cached):
            logger.info(f"[{self.name}] 行业数据降级到缓存")
            return cached, True, ""
        if cached:
            logger.warning(f"[{self.name}] 行业缓存为空或格式无效，跳过缓存")

        # 3. 返回空 + 降级原因；框架级 preset fallback 由 IndustryAgent 负责。
        reason = (
            f"【行业情绪数据缺失】无法获取 {stock_code} 的行业板块景气数据。"
            f"建议补充方式：1) 使用 AI 搜索 '{stock_code} 所属行业 板块景气度'；"
            "2) 通过 data_sources 注入行业景气、生命周期、拐点和特殊信号字段"
        )
        logger.warning(f"[{self.name}] 行业数据不可用（实时+缓存均失败）")
        return None, False, reason

    # ── 财务数据 ──

    def _get_financial_data(self, stock_code: str) -> tuple[Optional[Dict[str, Any]], bool, str]:
        """获取财务数据，带缓存降级。

        Returns:
            (data_dict, from_cache, degradation_reason)
            degradation_reason: 空字符串表示无降级，否则为降级原因描述
        """
        # 预处理：去掉 .SH/.SZ/.BJ 后缀，避免 normalize_code 生成错误格式
        clean_code = self._clean_code(stock_code)

        # 1. 尝试实时获取
        if self._financial_ds:
            try:
                result = self._financial_ds.get_financial_data(clean_code)
                # 检查 API 是否返回错误响应
                if result and any(
                    isinstance(v, dict) and v.get("status") not in (0, "0", None, "")
                    for v in result.values()
                ):
                    logger.warning(f"[{self.name}] 财务 API 返回错误，视为获取失败")
                    result = None
                if result and not self._has_financial_payload(result):
                    logger.warning(f"[{self.name}] 财务 API 返回空报表，视为获取失败")
                    result = None
                if result:
                    self._save_cache(f"{stock_code}_financial", result)
                    logger.info(f"[{self.name}] 财务数据实时获取成功")
                    return result, False, ""
            except Exception as e:
                logger.warning(f"[{self.name}] 财务数据实时获取失败: {e}")

        # 2. 降级到缓存
        cached = self._load_cache(f"{stock_code}_financial")
        if cached and self._has_financial_payload(cached):
            logger.info(f"[{self.name}] 财务数据降级到缓存")
            return cached, True, ""
        if cached:
            logger.warning(f"[{self.name}] 财务缓存为空或格式无效，跳过缓存")

        # 3. 返回空 + 降级原因
        reason = (
            f"【财务数据缺失】无法获取 {stock_code} 的财务报表数据。"
            f"建议补充方式：1) 使用 AI 搜索 '{stock_code} 最新财报 营收增速 毛利率'；"
            "2) 通过 data_sources 注入营收、利润率、现金流和资产负债表字段"
        )
        logger.warning(f"[{self.name}] 财务数据不可用（实时+缓存均失败）")
        return None, False, reason

    def _clean_code(self, stock_code: str) -> str:
        """清理股票代码，去掉 .SH/.SZ/.BJ 后缀。

        EastMoneyDataSource.normalize_code 对带后缀的代码处理有问题：
        '002428.SZ' → 'SZ002428.SZ'（错误，应该是 'SZ002428'）
        这里先去掉后缀，再传给底层数据源。
        """
        code = stock_code.strip().upper()
        for suffix in (".SH", ".SZ", ".BJ"):
            if code.endswith(suffix):
                code = code[:-len(suffix)]
                break
        return code

    def _has_financial_payload(self, data: Dict[str, Any]) -> bool:
        """判断三张财报里是否至少有一张包含可用行数据。"""
        for sheet_name in ("balance", "income", "cashflow"):
            sheet = data.get(sheet_name)
            if isinstance(sheet, list) and len(sheet) > 0:
                return True
            if isinstance(sheet, dict):
                rows = sheet.get("data")
                if isinstance(rows, list) and len(rows) > 0:
                    return True
                if "data" not in sheet and len(sheet) > 0:
                    return True
        return False

    def _has_industry_payload(self, data: Dict[str, Any]) -> bool:
        """判断行业 payload 是否包含可用于分析或路由的信息。"""
        if not isinstance(data, dict):
            return False
        if data.get("status") == "preset_only" and data.get("preset"):
            return True
        if data.get("industry") or data.get("industry_name"):
            return True
        if data.get("signals") or data.get("special_signals"):
            return True
        if any(data.get(key) is not None for key in ("score", "stage", "direction")):
            return True
        return False

    def _classify_industry_status(
        self,
        industry_result: Optional[Dict[str, Any]],
        from_cache: bool,
    ) -> str:
        """返回行业数据状态，供 Agent meta 追踪使用。"""
        if not industry_result:
            return "missing"
        if industry_result.get("status") == "preset_only":
            return "preset_only"
        if from_cache:
            return "cache"
        return "live"

    def _classify_financial_status(
        self,
        financial_data: Optional[Dict[str, Any]],
        from_cache: bool,
    ) -> str:
        """返回财务数据状态，供 Agent meta 追踪使用。"""
        if not financial_data:
            return "missing"
        if from_cache:
            return "cache"
        return "live"

    # ── 缓存管理 ──

    def _find_cache_dir(self) -> Path:
        """查找缓存目录。

        缓存属于项目数据层，不写入 skill 目录，避免 analysis Skill
        持有 provider 运行态数据。
        """
        return Path(__file__).resolve().parent / "data" / "industrial_sentinel"

    def _save_cache(self, key: str, data: Dict[str, Any]) -> None:
        """保存数据到缓存。"""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / f"{key}_cache.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"[{self.name}] 缓存保存失败: {e}")

    def _load_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """从缓存加载数据。"""
        try:
            cache_file = self._cache_dir / f"{key}_cache.json"
            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"[{self.name}] 缓存加载失败: {e}")
        return None
