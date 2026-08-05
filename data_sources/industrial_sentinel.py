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

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, Mapping, Optional
from pathlib import Path
from datetime import date, datetime
import hashlib
import json
import os
import tempfile
import fcntl
from loguru import logger

from data_sources.industrial_sentinel_builders import (
    build_company_financial_signals,
    build_peer_basket,
)

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
        peer_financial_data_source: Optional[Any] = None,
        peer_codes: Optional[Any] = None,
        peer_fetch_workers: int = 4,
        cache_dir: Optional[Path] = None,
        route_evidence_path: Optional[Path] = None,
        industry_evidence_path: Optional[Path] = None,
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
        self._peer_financial_ds = peer_financial_data_source or self._financial_ds
        self._peer_codes_explicit = peer_codes is not None
        self._peer_codes = peer_codes if peer_codes is not None else []
        try:
            configured_workers = int(peer_fetch_workers)
        except (TypeError, ValueError):
            configured_workers = 4
        self._peer_fetch_workers = max(1, min(configured_workers, 8))
        self._cache_dir = Path(cache_dir) if cache_dir else self._find_cache_dir()
        self._route_evidence_path = (
            Path(route_evidence_path)
            if route_evidence_path
            else Path(__file__).resolve().with_name("industrial_sentinel_route_evidence.json")
        )
        self._industry_evidence_path = (
            Path(industry_evidence_path)
            if industry_evidence_path
            else Path(__file__).resolve().with_name("industrial_sentinel_industry_evidence.json")
        )
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
        route_evidence = self._load_route_evidence(stock_code)
        preliminary_plan = self._resolve_collection_plan(
            stock_code,
            None,
            route_evidence,
        )
        # Market context does not vote in System A.  Fetch it alongside the
        # target and bounded peer financials so a slow board API cannot delay
        # the evidence path it does not govern.
        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="industry-scope-fetch",
        ) as executor:
            industry_future = executor.submit(self._get_industry_data, stock_code)
            financial_future = executor.submit(
                self._get_financial_scopes,
                stock_code,
                preliminary_plan,
            )
            industry_result, industry_from_cache, industry_reason = industry_future.result()
            (
                financial_data,
                financial_from_cache,
                financial_reason,
                peer_financial_data,
                peer_reason,
            ) = financial_future.result()

        collection_plan = self._resolve_collection_plan(
            stock_code,
            industry_result,
            route_evidence,
        )
        if self._plan_fetch_signature(collection_plan) != self._plan_fetch_signature(preliminary_plan):
            (
                financial_data,
                financial_from_cache,
                financial_reason,
                peer_financial_data,
                peer_reason,
            ) = self._get_financial_scopes(stock_code, collection_plan)

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

        if peer_reason:
            degradation_reasons.append(peer_reason)

        cached_envelope = self.get_last_known_good(stock_code)
        cached_packet = dict(cached_envelope["packet"]) if cached_envelope else None
        fundamentals, fundamentals_reason = self._load_industry_fundamentals(
            stock_code,
            collection_plan,
        )
        if fundamentals_reason:
            degradation_reasons.append(fundamentals_reason)
        # Curated fundamentals are a missing-data fallback, not a second live
        # provider.  Once the injected provider has supplied any direct
        # industry signal, preserve that dataset and its LKG semantics intact.
        live_provider_has_direct_signals = self._has_valid_live_industry_scope(
            industry_result,
            collection_plan,
            live=(industry_status == "live" and not industry_from_cache),
        )
        cache_has_direct_signals = bool(
            cached_packet and cached_packet.get("industry_signals")
        )
        if fundamentals and not live_provider_has_direct_signals and not cache_has_direct_signals:
            if industry_from_cache and isinstance(industry_result, Mapping):
                # Keep cached market context, but never let a stale direct
                # System A scope contaminate the fresh curated fallback.
                industry_result = dict(industry_result)
                industry_result.pop("industry_signals", None)
                industry_result.pop("evidence", None)
            industry_result = self._merge_industry_fundamentals(
                industry_result,
                fundamentals,
            )

        packet = self._build_packet(
            stock_code=stock_code,
            industry_result=industry_result,
            financial_data=financial_data,
            peer_financial_data=peer_financial_data,
            industry_status=industry_status,
            financial_status=financial_status,
            collection_plan=collection_plan,
        )
        try:
            packet["evidence"] = self._append_evidence_history(
                stock_code,
                packet.get("evidence") or [],
            )
        except ValueError as exc:
            packet["evidence"] = []
            degradation_reasons.append(f"【evidence history 拒绝写入】{exc}")
        packet = self._apply_cache_freshness(packet)
        packet["data_hash"] = self._packet_hash(packet)
        current_has_payload = bool(
            packet.get("industry_signals")
            or packet.get("peer_basket_signals")
            or packet.get("company_signals")
        )
        _, invalid_scopes, validation_reasons = self._validate_packet_candidate(
            packet,
            cached_packet,
        )
        if validation_reasons:
            degradation_reasons.extend(
                f"【标准数据包拒绝】{reason}" for reason in validation_reasons
            )
        has_fresh_provider = any(
            status in {"live", "curated_web"}
            for status in (packet.get("provider_status") or {}).values()
        )
        if cached_packet and not has_fresh_provider:
            invalid_scopes.update(
                scope
                for scope in ("industry_signals", "peer_basket_signals", "company_signals")
                if cached_packet.get(scope)
            )
        merge_candidate = self._without_invalid_scopes(packet, invalid_scopes)
        restored_scopes: list[str] = []
        if cached_packet:
            packet, restored_scopes = self._merge_packet_with_last_known_good(
                merge_candidate,
                cached_packet,
                cached_envelope,
            )
        else:
            packet = merge_candidate
        if restored_scopes:
            degradation_reasons.append(
                "【标准数据包缓存回填】live 缺失字段已从 last-known-good 恢复："
                + ", ".join(restored_scopes)
                + "；来源状态已标注 cache/stale。"
            )
        if not current_has_payload and cached_packet:
            degradation_reasons.append("【标准数据包缓存回退】live 数据包不可用，已使用最近可用 IndustryDataPacket。")
        profile_bound = bool(packet.get("profile_version"))
        if current_has_payload and has_fresh_provider and profile_bound:
            packet, publish_restored, publish_reasons, published = self._publish_last_known_good(
                stock_code,
                merge_candidate,
            )
            for scope in publish_restored:
                if scope not in restored_scopes:
                    restored_scopes.append(scope)
            if not published:
                degradation_reasons.extend(
                    f"【LKG 未更新】{reason}" for reason in publish_reasons
                )
        elif current_has_payload and has_fresh_provider and not profile_bound:
            degradation_reasons.append("【LKG 未更新】数据包尚未绑定实际 Methodology Profile 版本。")

        return {
            "packet": packet,
            "industry_result": industry_result,
            "financial_data": financial_data,
            "industry_from_cache": industry_from_cache,
            "financial_from_cache": financial_from_cache,
            "industry_status": industry_status,
            "financial_status": financial_status,
            "degradation_reasons": degradation_reasons,
        }

    def _get_financial_scopes(
        self,
        stock_code: str,
        collection_plan: Optional[Mapping[str, Any]],
    ) -> tuple[
        Optional[Dict[str, Any]],
        bool,
        str,
        Dict[str, Any],
        str,
    ]:
        """Fetch target and peer financial scopes concurrently under one plan."""
        with ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="industry-financial-scope",
        ) as executor:
            company_future = executor.submit(
                self._get_financial_data,
                stock_code,
                collection_plan,
            )
            peer_future = executor.submit(
                self._get_peer_financial_data,
                stock_code,
                collection_plan,
            )
            financial_data, financial_from_cache, financial_reason = company_future.result()
            peer_financial_data, peer_reason = peer_future.result()
        return (
            financial_data,
            financial_from_cache,
            financial_reason,
            peer_financial_data,
            peer_reason,
        )

    @staticmethod
    def _plan_fetch_signature(plan: Optional[Mapping[str, Any]]) -> tuple[Any, ...]:
        value = dict(plan or {})
        route = dict(value.get("route") or {})
        periods = dict(value.get("report_periods") or {})
        methodology = dict(value.get("methodology_profile") or {})
        return (
            tuple(route.get("peer_candidates") or []),
            periods.get("report_period"),
            periods.get("comparison_report_period"),
            periods.get("previous_balance_report_period"),
            methodology.get("version"),
        )

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

    def _get_financial_data(
        self,
        stock_code: str,
        collection_plan: Optional[Mapping[str, Any]] = None,
    ) -> tuple[Optional[Dict[str, Any]], bool, str]:
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
                result = self._fetch_planned_financial_data(
                    self._financial_ds,
                    clean_code,
                    collection_plan,
                )
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

    def _fetch_planned_financial_data(
        self,
        provider: Any,
        clean_code: str,
        collection_plan: Optional[Mapping[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Fetch the plan's comparable periods without changing shared providers.

        EastMoney accepts a comma-separated ``report_date`` and returns all rows
        in one request per statement.  Flow statements retain current and prior-
        year comparable periods; the balance sheet retains current and the prior
        balance period.  Simpler injected providers keep their one-argument API.
        """
        method = provider.get_financial_data
        periods = dict((collection_plan or {}).get("report_periods") or {})
        requested = self._ordered_unique(
            periods.get(name)
            for name in (
                "report_period",
                "comparison_report_period",
                "previous_balance_report_period",
            )
        )
        supports_report_date = False
        try:
            from inspect import signature

            parameters = signature(method).parameters
            supports_report_date = "report_date" in parameters
        except (TypeError, ValueError):
            pass

        if not requested or not supports_report_date:
            return method(clean_code)
        report_date = ",".join(requested)
        payload = method(clean_code, report_date=report_date)
        selected = self._select_comparable_periods(payload, periods)
        if self._has_financial_payload(selected) and self._planned_financial_gaps(selected, periods):
            retry_payload = method(clean_code, report_date=report_date)
            payload = self._merge_financial_payloads(payload, retry_payload)
            selected = self._select_comparable_periods(payload, periods)
        return selected

    @staticmethod
    def _ordered_unique(values: Iterable[Any]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = str(value or "")[:10]
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _select_comparable_periods(
        self,
        payload: Optional[Mapping[str, Any]],
        periods: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result = dict(payload or {})
        current = str(periods.get("report_period") or "")[:10]
        comparison = str(periods.get("comparison_report_period") or "")[:10]
        previous_balance = str(periods.get("previous_balance_report_period") or "")[:10]
        allowed_by_sheet = {
            "income": {current, comparison},
            "cashflow": {current, comparison},
            "balance": {current, previous_balance},
        }
        for sheet_name, allowed in allowed_by_sheet.items():
            sheet = result.get(sheet_name)
            if not isinstance(sheet, Mapping) or not isinstance(sheet.get("data"), list):
                continue
            wrapper = dict(sheet)
            wrapper["data"] = [
                dict(row)
                for row in sheet.get("data") or []
                if isinstance(row, Mapping)
                and str(
                    row.get("REPORT_DATE")
                    or row.get("REPORTDATE")
                    or row.get("REPORT_PERIOD")
                    or ""
                )[:10] in allowed
            ]
            wrapper["count"] = len(wrapper["data"])
            result[sheet_name] = wrapper
        return result

    def _planned_financial_gaps(
        self,
        payload: Mapping[str, Any],
        periods: Mapping[str, Any],
    ) -> list[str]:
        current = str(periods.get("report_period") or "")[:10]
        comparison = str(periods.get("comparison_report_period") or "")[:10]
        previous_balance = str(periods.get("previous_balance_report_period") or "")[:10]
        expected = {
            "income": {current, comparison},
            "cashflow": {current, comparison},
            "balance": {current, previous_balance},
        }
        gaps = []
        for sheet_name, required_periods in expected.items():
            sheet = payload.get(sheet_name)
            rows = sheet.get("data") if isinstance(sheet, Mapping) else None
            observed = {
                str(
                    row.get("REPORT_DATE")
                    or row.get("REPORTDATE")
                    or row.get("REPORT_PERIOD")
                    or ""
                )[:10]
                for row in rows or []
                if isinstance(row, Mapping)
            }
            if not {value for value in required_periods if value}.issubset(observed):
                gaps.append(sheet_name)
        return gaps

    @staticmethod
    def _merge_financial_payloads(
        first: Optional[Mapping[str, Any]],
        second: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(first or {})
        for sheet_name in ("balance", "income", "cashflow"):
            left = dict(merged.get(sheet_name) or {}) if isinstance(merged.get(sheet_name), Mapping) else {}
            right_raw = (second or {}).get(sheet_name)
            right = dict(right_raw or {}) if isinstance(right_raw, Mapping) else {}
            rows = []
            seen = set()
            for wrapper in (left, right):
                for row in wrapper.get("data") or []:
                    if not isinstance(row, Mapping):
                        continue
                    value = dict(row)
                    key = str(
                        value.get("REPORT_DATE")
                        or value.get("REPORTDATE")
                        or value.get("REPORT_PERIOD")
                        or value
                    )
                    if key not in seen:
                        seen.add(key)
                        rows.append(value)
            wrapper = left or right
            wrapper["data"] = rows
            wrapper["count"] = len(rows)
            merged[sheet_name] = wrapper
        return merged

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

    # ── v0.2 标准数据包 ──

    def _get_peer_financial_data(
        self,
        stock_code: str,
        collection_plan: Optional[Mapping[str, Any]] = None,
    ) -> tuple[Dict[str, Any], str]:
        codes = self._resolve_peer_codes(stock_code, collection_plan)
        if not codes:
            return {}, ""
        if self._peer_financial_ds is None:
            return {}, "【同业财报缺失】已配置同业代码，但同业财务数据源不可用。"

        candidates = [
            code
            for code in codes
            if self._clean_code(code) != self._clean_code(stock_code)
        ]
        if not candidates:
            return {}, ""

        worker_count = min(self._peer_fetch_workers, len(candidates))
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="industry-peer-fetch",
        ) as executor:
            futures = [
                executor.submit(
                    self._fetch_peer_financial_candidate,
                    code,
                    collection_plan,
                )
                for code in candidates
            ]
            outcomes = [future.result() for future in futures]

        result: Dict[str, Any] = {}
        failures = []
        for code, (payload, failure_kind) in zip(candidates, outcomes):
            if payload:
                result[code] = payload
            else:
                failures.append(f"{code}({failure_kind})")
        reason = ""
        if failures:
            reason = f"【同业财报部分缺失】未获取：{', '.join(failures)}"
        return result, reason

    def _fetch_peer_financial_candidate(
        self,
        code: str,
        collection_plan: Optional[Mapping[str, Any]],
    ) -> tuple[Optional[Dict[str, Any]], str]:
        """Fetch one bounded peer without letting one provider error cancel the basket."""
        try:
            payload = self._fetch_planned_financial_data(
                self._peer_financial_ds,
                self._clean_code(code),
                collection_plan,
            )
            if payload and self._has_financial_payload(payload):
                return payload, ""
            return None, "empty_payload"
        except Exception as exc:
            logger.warning(f"[{self.name}] 同业 {code} 财报获取失败: {exc}")
            return None, f"provider_error:{type(exc).__name__}"

    def _resolve_peer_codes(
        self,
        stock_code: str,
        collection_plan: Optional[Mapping[str, Any]] = None,
    ) -> list[str]:
        value = self._peer_codes
        if not self._peer_codes_explicit:
            value = dict((collection_plan or {}).get("route") or {}).get("peer_candidates") or []
        if isinstance(value, Mapping):
            clean = self._clean_code(stock_code)
            value = value.get(stock_code) or value.get(stock_code.upper()) or value.get(clean) or []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item) for item in value] if isinstance(value, Iterable) else []

    def _resolve_collection_plan(
        self,
        stock_code: str,
        industry_result: Optional[Mapping[str, Any]],
        route_evidence: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Resolve bounded peer candidates and the exact Methodology Profile version."""
        try:
            from skills.industry.industrial_sentinel.planning import build_execution_plan

            source = dict(industry_result or {})
            source["route_evidence"] = list(route_evidence or [])
            source["target"] = {
                "stock_code": stock_code,
                "stock_name": source.get("stock_name") or stock_code,
                "industry": source.get("industry") or source.get("industry_name") or "",
                "sub_sector": source.get("sub_sector") or "",
                "preset": source.get("preset") or "generic",
                "input_type": "stock_code",
            }
            return build_execution_plan(
                stock_code,
                source,
                reference_date=source.get("as_of_date") or date.today().isoformat(),
            )
        except Exception as exc:
            logger.warning(f"[{self.name}] CollectionPlan 解析失败: {exc}")
            return {}

    def _load_route_evidence(self, stock_code: str) -> list[Dict[str, Any]]:
        """Load one compact local registry of source facts; fail closed on errors."""
        try:
            payload = json.loads(self._route_evidence_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception as exc:
            logger.warning(f"[{self.name}] 路由 evidence 文件不可读: {exc}")
            return []
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != "industry-route-evidence/0.1"
            or not isinstance(payload.get("records"), list)
        ):
            logger.warning(f"[{self.name}] 路由 evidence schema 无效，已忽略")
            return []
        target = self._clean_code(stock_code)
        return [
            dict(item)
            for item in payload.get("records") or []
            if isinstance(item, Mapping)
            and self._clean_code(str(item.get("stock_code") or "")) == target
        ]

    def _load_industry_fundamentals(
        self,
        stock_code: str,
        collection_plan: Optional[Mapping[str, Any]],
    ) -> tuple[Dict[str, Any], str]:
        """Load one profile-bound, audited industry evidence bundle.

        The file is a compact extraction registry, not a conclusion cache.  It
        may supply source facts only when the fixed-query preflight, profile
        binding, evidence metadata and time anchor all validate.
        """
        try:
            payload = json.loads(self._industry_evidence_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}, ""
        except Exception as exc:
            logger.warning(f"[{self.name}] 行业基本面 evidence 文件不可读: {exc}")
            return {}, "【行业基本面采集拒绝】evidence 文件不可读，未注入 System A。"

        plan = dict(collection_plan or {})
        profile_id = str((plan.get("methodology_profile") or {}).get("profile_id") or "")
        peer_group = str((plan.get("route") or {}).get("target_peer_group") or "")
        reference = self._parse_iso_date(plan.get("reference_date")) or date.today()
        profiles = payload.get("profiles") if isinstance(payload, Mapping) else None
        queries = payload.get("fixed_queries") if isinstance(payload, Mapping) else None
        preflight = payload.get("preflight") if isinstance(payload, Mapping) else None
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != "industry-fundamental-evidence/0.1"
            or not isinstance(profiles, Mapping)
            or not isinstance(queries, list)
            or not queries
            or not isinstance(preflight, Mapping)
            or preflight.get("status") != "passed"
        ):
            return {}, "【行业基本面采集拒绝】registry schema 或搜索前置校验无效，未注入 System A。"

        bundle = profiles.get(profile_id)
        if not isinstance(bundle, Mapping):
            return {}, ""
        if str(bundle.get("target_peer_group") or "") != peer_group:
            return {}, "【行业基本面采集拒绝】同行组与 Methodology Profile 不匹配，未注入 System A。"

        signals = bundle.get("industry_signals")
        evidence = bundle.get("evidence")
        query_ids = {
            str(item.get("query_id") or "")
            for item in queries
            if isinstance(item, Mapping) and item.get("query") and item.get("query_id")
        }
        if not isinstance(signals, Mapping) or not signals or not isinstance(evidence, list):
            return {}, "【行业基本面采集拒绝】行业信号或 evidence 为空，未注入 System A。"

        complete_paths = set()
        for item in evidence:
            if not isinstance(item, Mapping) or not self._complete_evidence_metadata(item):
                return {}, "【行业基本面采集拒绝】evidence 元数据不完整，未注入 System A。"
            path = str(item.get("field_path") or "")
            if not path.startswith("industry_signals."):
                return {}, "【行业基本面采集拒绝】存在越过行业信号边界的 evidence，未注入 System A。"
            if str(item.get("query_ref") or "") not in query_ids:
                return {}, "【行业基本面采集拒绝】evidence 未绑定固定查询，未注入 System A。"
            evidence_date = self._parse_iso_date(item.get("as_of_date"))
            if not evidence_date or evidence_date > reference:
                return {}, "【行业基本面采集拒绝】evidence 日期晚于运行时间锚点，未注入 System A。"
            if str(item.get("source_level") or "").upper() not in {"L1", "L2"}:
                return {}, "【行业基本面采集拒绝】evidence 来源等级无效，未注入 System A。"
            complete_paths.add(path)
        expected_paths = {f"industry_signals.{field}" for field in signals}
        if expected_paths - complete_paths:
            return {}, "【行业基本面采集拒绝】行业信号缺少逐字段 evidence，未注入 System A。"

        result = dict(bundle)
        result["collection_mode"] = str(payload.get("collection_mode") or "curated_web")
        result["registry_fetched_at"] = str(payload.get("fetched_at") or "")
        return result, ""

    @staticmethod
    def _parse_iso_date(value: Any) -> Optional[date]:
        try:
            return date.fromisoformat(str(value or "")[:10])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _merge_industry_fundamentals(
        industry_result: Optional[Mapping[str, Any]],
        fundamentals: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Fill missing direct fields while preserving any real provider facts."""
        result = dict(industry_result or {})
        existing = dict(result.get("industry_signals") or {})
        incoming = dict(fundamentals.get("industry_signals") or {})
        accepted_fields = []
        for field, value in incoming.items():
            if field not in existing:
                existing[field] = value
                accepted_fields.append(str(field))
        result["industry_signals"] = existing

        accepted_paths = {f"industry_signals.{field}" for field in accepted_fields}
        current_evidence = [dict(item) for item in result.get("evidence") or [] if isinstance(item, Mapping)]
        current_evidence.extend(
            dict(item)
            for item in fundamentals.get("evidence") or []
            if isinstance(item, Mapping) and str(item.get("field_path") or "") in accepted_paths
        )
        result["evidence"] = current_evidence
        result["needs_data"] = [
            *[dict(item) for item in result.get("needs_data") or [] if isinstance(item, Mapping)],
            *[dict(item) for item in fundamentals.get("needs_data") or [] if isinstance(item, Mapping)],
        ]
        dates = [
            str(result.get("as_of_date") or "")[:10],
            str(fundamentals.get("as_of_date") or "")[:10],
        ]
        result["as_of_date"] = max((item for item in dates if item), default="")
        result["_industry_fundamental_status"] = fundamentals.get("collection_mode") or "curated_web"
        result["_industry_fundamental_registry_fetched_at"] = fundamentals.get("registry_fetched_at") or ""
        return result

    def _build_packet(
        self,
        stock_code: str,
        industry_result: Optional[Dict[str, Any]],
        financial_data: Optional[Dict[str, Any]],
        peer_financial_data: Mapping[str, Any],
        industry_status: str,
        financial_status: str,
        collection_plan: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        industry_result = dict(industry_result or {})
        explicit_industry_signals = (
            dict(industry_result.get("industry_signals") or {})
            if isinstance(industry_result.get("industry_signals"), dict)
            else {}
        )
        explicit_evidence = self._list_of_dicts(industry_result.get("evidence"))
        product_industry_map = self._list_of_dicts(
            industry_result.get("product_industry_map")
            or industry_result.get("products")
        )
        valuation_context = (
            dict(industry_result.get("valuation_context") or {})
            if isinstance(industry_result.get("valuation_context"), Mapping)
            else {}
        )
        planned = dict(collection_plan or {})

        company = build_company_financial_signals(
            financial_data,
            stock_code=stock_code,
            stock_name=str(industry_result.get("stock_name") or stock_code),
        )
        peer = build_peer_basket(
            peer_financial_data,
            target_code=stock_code,
            methodology_profile=planned.get("methodology_profile") or {},
        )
        evidence = explicit_evidence + company["evidence"] + peer["evidence"]

        as_of_candidates = [
            industry_result.get("as_of_date"),
            company.get("report_period"),
            peer.get("peer_basket_meta", {}).get("report_period"),
        ]
        as_of_date = max(
            [str(item)[:10] for item in as_of_candidates if item],
            default="",
        )
        needs_data = self._list_of_dicts(industry_result.get("needs_data"))
        if not explicit_industry_signals:
            needs_data.append(
                {
                    "field_path": "industry_signals",
                    "reason": "当前行业 provider 只提供市场情绪/板块背景，不提供 System A 基本面证据。",
                }
            )
        if not peer.get("peer_basket_signals"):
            needs_data.append(
                {
                    "field_path": "peer_basket_signals",
                    "reason": "未配置或未成功构建同业财报篮子。",
                }
            )

        live = industry_status == "live" or financial_status == "live"
        planned_target = dict(planned.get("target") or {})
        strategic_route = dict(planned.get("route") or {}).get("route_mode") == "evidence_backed_strategic"
        packet = {
            "schema_version": "industry-data/0.2",
            "target": {
                "stock_code": stock_code,
                "stock_name": industry_result.get("stock_name") or planned_target.get("stock_name") or stock_code,
                "industry": industry_result.get("industry") or industry_result.get("industry_name") or planned_target.get("industry") or "",
                "sub_sector": industry_result.get("sub_sector") or planned_target.get("sub_sector") or "",
                "preset": (
                    planned_target.get("preset")
                    if strategic_route
                    else industry_result.get("preset") or planned_target.get("preset")
                ) or "generic",
                "input_type": "stock_code",
            },
            "industry_signals": explicit_industry_signals,
            "peer_basket_signals": peer.get("peer_basket_signals") or {},
            "peer_basket_meta": peer.get("peer_basket_meta") or {},
            "company_signals": company.get("company_signals") or {},
            # Optional research facts injected by an industry-scoped source.
            # They do not participate in System A admission; runtime uses them
            # only after the industry conclusion has been frozen.
            "product_industry_map": product_industry_map,
            "valuation_context": valuation_context,
            "market_context": {
                "provider": "industry_sentiment",
                "status": industry_status,
                "industry_name": industry_result.get("industry_name") or industry_result.get("industry") or "",
                "score": industry_result.get("score"),
                "stage": industry_result.get("stage"),
                "direction": industry_result.get("direction"),
                "indicators": industry_result.get("indicators") or {},
                "special_signals": industry_result.get("special_signals") or [],
                "usage": "market_context_only",
            },
            "evidence": evidence,
            "needs_data": self._dedupe_needs_data(needs_data),
            "as_of_date": as_of_date,
            "data_quality": "complete" if explicit_industry_signals else "incomplete" if company["company_signals"] else "missing",
            "provider_status": {
                "market_context": industry_status,
                "industry_fundamentals": (
                    str(industry_result.get("_industry_fundamental_status"))
                    if explicit_industry_signals and industry_result.get("_industry_fundamental_status")
                    else "live" if explicit_industry_signals and industry_status == "live"
                    else "cache" if explicit_industry_signals and industry_status == "cache"
                    else "missing"
                ),
                "company_financials": financial_status,
                "peer_financials": "live" if peer_financial_data else "not_configured",
            },
            "source_mode": (
                "mixed_live_curated" if live and industry_result.get("_industry_fundamental_status")
                else "live" if live
                else "curated_web" if industry_result.get("_industry_fundamental_status")
                else "cache" if (industry_status == "cache" or financial_status == "cache")
                else "missing"
            ),
            "fetched_at": datetime.now().isoformat(),
            "routing": dict(planned.get("route") or {}),
            "route_evidence": list(planned.get("route_evidence") or []),
            "route_evidence_rejections": list(planned.get("route_evidence_rejections") or []),
            "profile_version": (planned.get("methodology_profile") or {}).get("version") or "",
            "profile_id": (planned.get("methodology_profile") or {}).get("profile_id") or "",
            "collection_plan": planned,
        }
        packet["data_hash"] = self._packet_hash(packet)
        return packet

    def _validate_packet_candidate(
        self,
        packet: Mapping[str, Any],
        previous: Optional[Mapping[str, Any]],
    ) -> tuple[bool, set[str], list[str]]:
        """Validate a live candidate before it may replace last-known-good."""
        invalid_scopes: set[str] = set()
        reasons: list[str] = []
        scopes = ("industry_signals", "peer_basket_signals", "company_signals")
        if packet.get("schema_version") != "industry-data/0.2":
            reasons.append("schema_version 不是 industry-data/0.2。")
            invalid_scopes.update(scopes)
        if not isinstance(packet.get("target"), Mapping) or not (packet.get("target") or {}).get("stock_code"):
            reasons.append("target.stock_code 缺失。")
            invalid_scopes.update(scopes)
        if not isinstance(packet.get("evidence"), list):
            reasons.append("evidence 必须为列表。")
            invalid_scopes.update(scopes)

        evidence_records = [
            item for item in packet.get("evidence") or []
            if isinstance(item, Mapping)
        ]
        complete_evidence_paths = {
            str(item.get("field_path") or "")
            for item in evidence_records
            if self._complete_evidence_metadata(item)
        }
        incomplete_evidence_paths = {
            str(item.get("field_path") or "")
            for item in evidence_records
            if item.get("field_path") and not self._complete_evidence_metadata(item)
        }
        for scope in scopes:
            values = packet.get(scope)
            if not isinstance(values, Mapping):
                reasons.append(f"{scope} 必须为映射。")
                invalid_scopes.add(scope)
                continue
            missing_evidence = [
                field for field in values
                if f"{scope}.{field}" not in complete_evidence_paths
            ]
            if missing_evidence:
                incomplete = [
                    field for field in missing_evidence
                    if f"{scope}.{field}" in incomplete_evidence_paths
                ]
                if incomplete:
                    reasons.append(
                        f"{scope} evidence 元数据不完整：{', '.join(sorted(map(str, incomplete)))}。"
                    )
                absent = sorted(set(map(str, missing_evidence)) - set(map(str, incomplete)))
                if absent:
                    reasons.append(f"{scope} 缺少 evidence：{', '.join(absent)}。")
                invalid_scopes.add(scope)
            previous_values = dict((previous or {}).get(scope) or {})
            current_count = len(values)
            previous_count = len(previous_values)
            if previous_count > 0 and current_count == 0:
                reasons.append(
                    f"{scope} 从 {previous_count} 个字段降为 0，未提供显式 tombstone，拒绝删除 LKG scope。"
                )
                invalid_scopes.add(scope)
            if (
                previous_count >= 4
                and current_count > 0
                and current_count / previous_count < 0.5
                and previous_count - current_count >= 2
            ):
                reasons.append(
                    f"{scope} 关键字段骤减：{previous_count} → {current_count}，拒绝覆盖 last-known-good。"
                )
                invalid_scopes.add(scope)
        if packet.get("peer_basket_signals") and not packet.get("peer_basket_meta"):
            reasons.append("peer_basket_signals 缺少 peer_basket_meta。")
            invalid_scopes.add("peer_basket_signals")
        peer_regressions = self._peer_coverage_regressions(packet, previous)
        if peer_regressions:
            reasons.append(
                "peer_basket_signals 同报告期覆盖或成员回退："
                + ", ".join(peer_regressions)
                + "；拒绝让随机 provider 缺失改变同行投票。"
            )
            invalid_scopes.add("peer_basket_signals")
        return not reasons, invalid_scopes, reasons

    @staticmethod
    def _peer_coverage_regressions(
        current: Mapping[str, Any],
        previous: Optional[Mapping[str, Any]],
    ) -> list[str]:
        """Detect same-period peer shrinkage that must use the fuller LKG basket."""
        if not previous or not current.get("peer_basket_signals") or not previous.get("peer_basket_signals"):
            return []
        current_meta = dict(current.get("peer_basket_meta") or {})
        previous_meta = dict(previous.get("peer_basket_meta") or {})
        same_period = (
            current_meta.get("report_period")
            and current_meta.get("report_period") == previous_meta.get("report_period")
        )
        same_profile = (
            current.get("profile_version")
            and current.get("profile_version") == previous.get("profile_version")
        )
        if not same_period or not same_profile:
            return []

        regressions: list[str] = []
        current_sample = int(current_meta.get("sample_size") or 0)
        previous_sample = int(previous_meta.get("sample_size") or 0)
        if current_sample < previous_sample:
            regressions.append(f"sample_size {previous_sample}→{current_sample}")
        current_coverage = dict(current_meta.get("coverage_ratio_by_field") or {})
        previous_coverage = dict(previous_meta.get("coverage_ratio_by_field") or {})
        for field in sorted(set(current_coverage) & set(previous_coverage)):
            current_ratio = float(current_coverage.get(field) or 0)
            previous_ratio = float(previous_coverage.get(field) or 0)
            if current_ratio + 1e-9 < previous_ratio:
                regressions.append(f"{field} {previous_ratio:.2f}→{current_ratio:.2f}")
        current_members = IndustrialSentinelDataSource._peer_evidence_members_by_field(current)
        previous_members = IndustrialSentinelDataSource._peer_evidence_members_by_field(previous)
        for field in sorted(set(current_members) & set(previous_members)):
            missing_members = previous_members[field] - current_members[field]
            if missing_members:
                regressions.append(
                    f"{field} 缺少既有成员 {','.join(sorted(missing_members))}"
                )
        return regressions

    @staticmethod
    def _peer_evidence_members_by_field(packet: Mapping[str, Any]) -> Dict[str, set[str]]:
        members: Dict[str, set[str]] = {}
        for item in packet.get("evidence") or []:
            path = str(item.get("field_path") or "")
            if not path.startswith("peer_basket_signals."):
                continue
            code = str(item.get("member_stock_code") or item.get("stock_code") or "").upper()
            if code:
                members.setdefault(path.split(".", 1)[1], set()).add(code)
        return members

    @staticmethod
    def _complete_evidence_metadata(item: Mapping[str, Any]) -> bool:
        return bool(
            item.get("evidence_id")
            and item.get("fact_key")
            and item.get("fetched_at")
            and item.get("fact_type")
            and item.get("company_code")
            and item.get("report_period")
            and item.get("as_of_date")
            and (item.get("provider") or item.get("source_type"))
            and isinstance(item.get("raw_values"), Mapping)
            and item.get("raw_values")
        )

    @classmethod
    def _has_valid_live_industry_scope(
        cls,
        industry_result: Optional[Mapping[str, Any]],
        collection_plan: Optional[Mapping[str, Any]],
        *,
        live: bool,
    ) -> bool:
        """Return true only for a complete, fresh live direct-industry scope."""
        if not live or not isinstance(industry_result, Mapping):
            return False
        signals = dict(industry_result.get("industry_signals") or {})
        if not signals:
            return False
        evidence = [
            item for item in industry_result.get("evidence") or []
            if isinstance(item, Mapping) and cls._complete_evidence_metadata(item)
        ]
        profile = dict((collection_plan or {}).get("methodology_profile") or {})
        default_days = int(
            dict(profile.get("observation_windows") or {}).get("default_freshness_days")
            or 180
        )
        definitions_by_path = {
            str(item.get("field_path") or ""): dict(item)
            for items in dict(profile.get("indicators") or {}).values()
            for item in items or []
            if isinstance(item, Mapping) and item.get("field_path")
        }
        reference = cls._parse_iso_date((collection_plan or {}).get("reference_date")) or date.today()
        for field in signals:
            path = f"industry_signals.{field}"
            definition = definitions_by_path.get(path)
            if not definition:
                return False
            allowed_levels = {
                str(item).upper() for item in definition.get("source_levels") or []
            } & {"L1", "L2", "L3"}
            if not allowed_levels:
                return False
            matching_dates = [
                cls._parse_iso_date(item.get("as_of_date"))
                for item in evidence
                if str(item.get("field_path") or "") == path
                and str(item.get("scope") or "") == "industry"
                and str(item.get("source_level") or "").upper() in allowed_levels
            ]
            max_age = min(int(definition.get("freshness_days") or default_days), 90)
            if not any(
                item is not None and -7 <= (reference - item).days <= max_age
                for item in matching_dates
            ):
                return False
        return True

    def _apply_cache_freshness(self, packet: Mapping[str, Any]) -> Dict[str, Any]:
        """Turn generic cache labels into scope-aware cache/stale provenance."""
        result = dict(packet)
        statuses = dict(packet.get("provider_status") or {})
        scope_status_fields = {
            "industry_signals": "industry_fundamentals",
            "peer_basket_signals": "peer_financials",
            "company_signals": "company_financials",
            "market_context": "market_context",
        }
        for scope, status_field in scope_status_fields.items():
            if statuses.get(status_field) == "cache" and packet.get(scope):
                statuses[status_field] = self._scope_cache_status(packet, scope)
                if scope == "company_signals":
                    statuses["company_financials_by_field"] = self._company_cache_status_by_field(packet)
        result["provider_status"] = statuses

        relevant = []
        for scope, status_field in scope_status_fields.items():
            if packet.get(scope):
                relevant.append(statuses.get(status_field))
        if "live" in relevant and any(item in {"cache", "stale"} for item in relevant):
            result["source_mode"] = "mixed_cache"
        elif "live" not in relevant and "stale" in relevant:
            result["source_mode"] = "stale_cache"
        elif "live" not in relevant and "cache" in relevant:
            result["source_mode"] = "cache"
        return result

    def _without_invalid_scopes(
        self,
        packet: Mapping[str, Any],
        invalid_scopes: Iterable[str],
    ) -> Dict[str, Any]:
        result = dict(packet)
        for scope in set(invalid_scopes):
            result[scope] = {}
            if scope == "peer_basket_signals":
                result["peer_basket_meta"] = {}
        if invalid_scopes:
            invalid_prefixes = tuple(f"{scope}." for scope in invalid_scopes)
            result["evidence"] = [
                dict(item)
                for item in packet.get("evidence") or []
                if not str(item.get("field_path") or "").startswith(invalid_prefixes)
            ]
            result["data_hash"] = self._packet_hash(result)
        return result

    def _save_packet_cache(self, stock_code: str, packet: Dict[str, Any]) -> bool:
        profile = dict(packet.get("methodology_profile") or {})
        profile_version = packet.get("profile_version") or profile.get("version") or ""
        if not profile_version:
            logger.warning(f"[{self.name}] 标准数据包缺少 Methodology Profile 版本，拒绝更新 LKG")
            return False
        envelope = {
            "schema_version": "industry-data/0.2",
            "profile_version": profile_version,
            "fetched_at": datetime.now().isoformat(),
            "as_of_date": packet.get("as_of_date") or "",
            "report_period": (
                packet.get("peer_basket_meta", {}).get("report_period")
                or packet.get("as_of_date")
                or ""
            ),
            "provider_status": packet.get("provider_status") or {},
            "data_hash": self._packet_hash(packet),
            "packet": packet,
        }
        return self._save_cache(f"{stock_code}_packet_v02", envelope)

    def _publish_last_known_good(
        self,
        stock_code: str,
        current: Mapping[str, Any],
    ) -> tuple[Dict[str, Any], list[str], list[str], bool]:
        """Atomically merge and publish one stock's last-known-good packet.

        Fetching happens outside this critical section.  Inside the lock we re-read
        the latest envelope, validate the live scopes against that exact version,
        merge missing scopes, validate the final packet, and only then replace the
        cache.  This prevents concurrent company/peer updates from losing each
        other's valid scope.
        """
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._cache_dir / f"{stock_code}_packet_v02.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                latest_envelope = self.get_last_known_good(stock_code)
                latest_packet = (
                    dict(latest_envelope["packet"])
                    if latest_envelope
                    else None
                )
                _, invalid_scopes, reasons = self._validate_packet_candidate(
                    current,
                    latest_packet,
                )
                candidate = self._without_invalid_scopes(current, invalid_scopes)
                restored: list[str] = []
                if latest_packet:
                    candidate, restored = self._merge_packet_with_last_known_good(
                        candidate,
                        latest_packet,
                        latest_envelope,
                    )
                publish_valid, _, publish_reasons = self._validate_packet_candidate(
                    candidate,
                    None,
                )
                reasons.extend(publish_reasons)
                if not publish_valid:
                    return candidate, restored, reasons, False
                saved = self._save_packet_cache(stock_code, candidate)
                if not saved:
                    reasons.append("标准数据包原子写入失败，已保留原 last-known-good。")
                return candidate, restored, reasons, saved
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _merge_packet_with_last_known_good(
        self,
        current: Mapping[str, Any],
        cached: Mapping[str, Any],
        cache_envelope: Optional[Mapping[str, Any]] = None,
    ) -> tuple[Dict[str, Any], list[str]]:
        """Fill missing packet scopes without replacing fresher live scopes."""
        merged = dict(current)
        merged["target"] = dict(current.get("target") or {})
        for key, value in dict(cached.get("target") or {}).items():
            if not merged["target"].get(key):
                merged["target"][key] = value

        restored: list[str] = []
        route_restored = False
        cached_route_evidence = list(cached.get("route_evidence") or [])
        if (
            not current.get("route_evidence")
            and cached_route_evidence
            and self._route_evidence_is_fresh(cached_route_evidence, current.get("as_of_date"))
            and dict(cached.get("routing") or {}).get("route_mode") == "evidence_backed_strategic"
        ):
            for field in (
                "routing", "route_evidence", "methodology_profile",
                "collection_plan", "profile_version", "profile_id",
            ):
                merged[field] = cached.get(field)
            merged["target"]["preset"] = dict(cached.get("target") or {}).get("preset") or merged["target"].get("preset")
            # A peer basket fetched under the fallback/static route is not
            # comparable with the restored strategic route. Restore its matching
            # cached basket below instead of mixing scopes.
            merged["peer_basket_signals"] = {}
            merged["peer_basket_meta"] = {}
            route_restored = True
            restored.append("routing")
        scope_fields = {
            "industry_signals": ("industry_signals",),
            "peer_basket_signals": ("peer_basket_signals", "peer_basket_meta"),
            "company_signals": ("company_signals",),
        }
        status_fields = {
            "industry_signals": "industry_fundamentals",
            "peer_basket_signals": "peer_financials",
            "company_signals": "company_financials",
        }
        provider_status = dict(current.get("provider_status") or {})
        evidence = [
            dict(item)
            for item in current.get("evidence") or []
            if not route_restored
            or not str(item.get("field_path") or "").startswith("peer_basket_signals.")
        ]
        restored_statuses: list[str] = []
        current_hash = current.get("data_hash") or self._packet_hash(current)
        current_provenance = {
            "mode": "live",
            "fetched_at": current.get("fetched_at") or "",
            "data_hash": current_hash,
            "profile_version": current.get("profile_version") or "",
        }
        scope_provenance = {
            scope: dict(current_provenance, mode=provider_status.get(status_fields[scope]) or "missing")
            for scope in scope_fields
            if current.get(scope)
        }
        cache_origin = {
            "data_hash": (cache_envelope or {}).get("data_hash") or cached.get("data_hash") or self._packet_hash(cached),
            "fetched_at": (cache_envelope or {}).get("fetched_at") or cached.get("fetched_at") or "",
            "profile_version": (cache_envelope or {}).get("profile_version") or cached.get("profile_version") or "",
        }
        if route_restored:
            scope_provenance["routing"] = dict(cache_origin, mode="cache")

        for scope, fields in scope_fields.items():
            if merged.get(scope) or not cached.get(scope):
                continue
            for field_name in fields:
                merged[field_name] = dict(cached.get(field_name) or {})
            prefix = f"{scope}."
            evidence.extend(
                dict(item)
                for item in cached.get("evidence") or []
                if str(item.get("field_path") or "").startswith(prefix)
            )
            cache_status = self._scope_cache_status(cached, scope)
            provider_status[status_fields[scope]] = cache_status
            scope_provenance[scope] = dict(cache_origin, mode=cache_status)
            if scope == "company_signals":
                provider_status["company_financials_by_field"] = self._company_cache_status_by_field(cached)
            restored_statuses.append(cache_status)
            restored.append(scope)

        current_market = dict(current.get("market_context") or {})
        if current_market.get("status") != "live" and cached.get("market_context"):
            merged["market_context"] = dict(cached.get("market_context") or {})
            market_status = self._scope_cache_status(cached, "market_context")
            provider_status["market_context"] = market_status
            scope_provenance["market_context"] = dict(cache_origin, mode=market_status)
            restored_statuses.append(market_status)
            restored.append("market_context")

        merged["provider_status"] = provider_status
        merged["evidence"] = self._dedupe_evidence(evidence)
        if restored:
            has_current_scope = any(current.get(name) for name in scope_fields) or (
                current_market.get("status") == "live"
            )
            any_stale = "stale" in restored_statuses
            merged["source_mode"] = "mixed_cache" if has_current_scope else ("stale_cache" if any_stale else "cache")
            merged["cache_origin"] = cache_origin
            merged["scope_provenance"] = scope_provenance
            if not has_current_scope:
                merged["fetched_at"] = cache_origin["fetched_at"]
            merged["data_hash"] = self._packet_hash(merged)
        return merged, restored

    @staticmethod
    def _route_evidence_is_fresh(
        evidence: Iterable[Mapping[str, Any]],
        reference_date: Any,
    ) -> bool:
        try:
            reference = date.fromisoformat(str(reference_date or date.today().isoformat())[:10])
        except ValueError:
            reference = date.today()
        dates = []
        for item in evidence:
            try:
                dates.append(date.fromisoformat(str(item.get("as_of_date") or "")[:10]))
            except ValueError:
                return False
        return bool(dates) and all(-7 <= (reference - value).days <= 450 for value in dates)

    def _load_packet_cache(self, stock_code: str) -> Optional[Dict[str, Any]]:
        envelope = self.get_last_known_good(stock_code)
        return dict(envelope["packet"]) if envelope else None

    def get_last_known_good(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """Return a hash-verified last-known-good envelope for audit/replay."""
        envelope = self._load_cache(f"{stock_code}_packet_v02")
        if not isinstance(envelope, dict) or envelope.get("schema_version") != "industry-data/0.2":
            return None
        required = (
            "profile_version", "fetched_at", "as_of_date", "report_period",
            "provider_status", "data_hash", "packet",
        )
        if any(field not in envelope for field in required):
            return None
        if not str(envelope.get("profile_version") or "") or str(envelope.get("profile_version")).startswith("preset:"):
            return None
        packet = envelope.get("packet")
        if (
            not isinstance(packet, dict)
            or packet.get("schema_version") != "industry-data/0.2"
            or not isinstance(envelope.get("provider_status"), dict)
        ):
            return None
        if envelope.get("data_hash") != self._packet_hash(packet):
            logger.warning(f"[{self.name}] 标准数据包缓存 hash 校验失败")
            return None
        return dict(envelope)

    def _scope_cache_status(self, packet: Mapping[str, Any], scope: str) -> str:
        """Apply the TTL belonging to the restored data scope."""
        prefix = f"{scope}."
        evidence_dates = []
        for item in packet.get("evidence") or []:
            if str(item.get("field_path") or "").startswith(prefix):
                try:
                    evidence_dates.append(date.fromisoformat(str(item.get("as_of_date") or "")[:10]))
                except ValueError:
                    continue
        if evidence_dates:
            as_of = max(evidence_dates)
        else:
            raw_date = (
                (packet.get("peer_basket_meta") or {}).get("report_period")
                if scope == "peer_basket_signals"
                else packet.get("as_of_date")
            )
            try:
                as_of = date.fromisoformat(str(raw_date or "")[:10])
            except ValueError:
                return "stale"

        if scope in {"industry_signals", "market_context"}:
            max_age = 90
        elif scope == "peer_basket_signals":
            max_age = 180
        elif scope == "company_signals":
            field_status = self._company_cache_status_by_field(packet)
            return "stale" if not field_status or "stale" in field_status.values() else "cache"
        else:
            max_age = 90
        return "stale" if (date.today() - as_of).days > max_age else "cache"

    def _company_cache_status_by_field(self, packet: Mapping[str, Any]) -> Dict[str, str]:
        """Keep annual and quarterly company indicators on separate TTLs."""
        annual_fields = {"profit_stability"}
        evidence_by_field = {
            str(item.get("field_path") or "").split(".", 1)[-1]: item
            for item in packet.get("evidence") or []
            if str(item.get("field_path") or "").startswith("company_signals.")
        }
        statuses: Dict[str, str] = {}
        for field_name in (packet.get("company_signals") or {}):
            item = evidence_by_field.get(field_name) or {}
            try:
                as_of = date.fromisoformat(str(item.get("as_of_date") or packet.get("as_of_date") or "")[:10])
            except ValueError:
                statuses[field_name] = "stale"
                continue
            max_age = 450 if field_name in annual_fields else 180
            statuses[field_name] = "stale" if (date.today() - as_of).days > max_age else "cache"
        return statuses

    def _packet_hash(self, packet: Mapping[str, Any]) -> str:
        payload = dict(packet)
        payload.pop("data_hash", None)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get_evidence_history(self, stock_code: str) -> list[Dict[str, Any]]:
        """Return the immutable raw-evidence history for audit and replay."""
        path = self._cache_dir / f"{stock_code}_evidence_history.json"
        if not path.exists():
            return []
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError(f"evidence history 无法读取：{path}") from exc
        if not isinstance(loaded, dict) or loaded.get("schema_version") != "industry-evidence-store/0.1":
            raise ValueError(f"evidence history schema 无效：{path}")
        records = loaded.get("records")
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            raise ValueError(f"evidence history records 无效：{path}")
        return [dict(item) for item in records]

    def _append_evidence_history(
        self,
        stock_code: str,
        evidence: Iterable[Mapping[str, Any]],
    ) -> list[Dict[str, Any]]:
        """Append logical evidence versions and return records used by this packet."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._cache_dir / f"{stock_code}_evidence_history.lock"
        with open(lock_path, "a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                return self._append_evidence_history_locked(stock_code, evidence)
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _append_evidence_history_locked(
        self,
        stock_code: str,
        evidence: Iterable[Mapping[str, Any]],
    ) -> list[Dict[str, Any]]:
        history = self.get_evidence_history(stock_code)
        latest_by_fact: Dict[str, Dict[str, Any]] = {}
        for item in history:
            fact_key = str(item.get("fact_key") or "")
            if not fact_key:
                continue
            current = latest_by_fact.get(fact_key)
            if current is None or int(item.get("revision") or 0) > int(current.get("revision") or 0):
                latest_by_fact[fact_key] = item

        packet_records: list[Dict[str, Any]] = []
        appended = False
        fetched_at = datetime.now().isoformat()
        for raw in evidence:
            normalized = self._normalize_evidence_record(stock_code, raw, fetched_at)
            previous = latest_by_fact.get(normalized["fact_key"])
            if previous and previous.get("content_hash") == normalized.get("content_hash"):
                packet_records.append(dict(previous))
                continue
            revision = int(previous.get("revision") or 0) + 1 if previous else 1
            supersedes = previous.get("evidence_id") if previous else None
            evidence_identity = f"{normalized['fact_key']}:{normalized['content_hash']}:{revision}:{supersedes or ''}"
            normalized["evidence_id"] = "ev_" + hashlib.sha256(
                evidence_identity.encode("utf-8")
            ).hexdigest()[:24]
            normalized["revision"] = revision
            normalized["supersedes_evidence_id"] = supersedes
            history.append(normalized)
            latest_by_fact[normalized["fact_key"]] = normalized
            packet_records.append(dict(normalized))
            appended = True

        if appended:
            envelope = {
                "schema_version": "industry-evidence-store/0.1",
                "stock_code": stock_code,
                "updated_at": fetched_at,
                "record_count": len(history),
                "records": history,
            }
            self._write_json_atomic(
                self._cache_dir / f"{stock_code}_evidence_history.json",
                envelope,
            )
        return packet_records

    @staticmethod
    def _normalize_evidence_record(
        target_code: str,
        raw: Mapping[str, Any],
        fetched_at: str,
    ) -> Dict[str, Any]:
        record = dict(raw)
        field_path = str(record.get("field_path") or "")
        fact_type = field_path.split(".", 1)[-1] if field_path else "unknown"
        company_code = (
            record.get("member_stock_code")
            or record.get("stock_code")
            or target_code
        )
        identity = {
            "provider": record.get("provider") or record.get("source_type") or "unknown",
            "company_code": company_code,
            "fact_type": fact_type,
            "field_path": field_path,
            "report_period": str(record.get("report_period") or "")[:10],
            "source_url": record.get("source_url") or record.get("url") or "",
        }
        fact_key = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        content = {
            "raw_values": record.get("raw_values") or {},
            "value": record.get("value"),
            "aggregate_value": record.get("aggregate_value"),
            "previous_report_period": record.get("previous_report_period") or "",
            "comparison": record.get("comparison") or "",
            "comparison_operands": record.get("comparison_operands") or {},
            "member_direction": record.get("member_direction") or "",
            "derivation_method": record.get("derivation_method") or "",
            "aggregation_method": record.get("aggregation_method"),
        }
        content_hash = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        record.update(
            {
                "fact_key": fact_key,
                "content_hash": content_hash,
                "fact_type": fact_type,
                "company_code": str(company_code),
                "fetched_at": record.get("fetched_at") or fetched_at,
            }
        )
        return record

    @staticmethod
    def _dedupe_evidence(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
        seen = set()
        result = []
        for item in items:
            value = dict(item)
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def _list_of_dicts(value: Any) -> list[Dict[str, Any]]:
        if isinstance(value, dict):
            return [dict(value)]
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _dedupe_needs_data(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        seen = set()
        result = []
        for item in items:
            key = (str(item.get("field_path") or ""), str(item.get("reason") or ""))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    # ── 缓存管理 ──

    def _find_cache_dir(self) -> Path:
        """查找缓存目录。

        缓存属于项目数据层，不写入 skill 目录，避免 analysis Skill
        持有 provider 运行态数据。
        """
        return Path(__file__).resolve().parent / "data" / "industrial_sentinel"

    def _save_cache(self, key: str, data: Dict[str, Any]) -> bool:
        """原子保存缓存，避免进程中断留下半个 JSON。"""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self._cache_dir / f"{key}_cache.json"
            self._write_json_atomic(cache_file, data)
            return True
        except Exception as e:
            logger.debug(f"[{self.name}] 缓存保存失败: {e}")
            return False

    def _write_json_atomic(self, path: Path, data: Mapping[str, Any]) -> None:
        """Write one JSON document through fsync and atomic replacement."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

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
