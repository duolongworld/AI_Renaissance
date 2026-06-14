"""
技术指标 Agent - 专家2组

signal_type: technical
Skill 域: skills/technical/
核心能力：传统技术指标融合、量价背离与反转、公司发展沿革辅助研究
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent
from agents.signal import Signal, neutral_signal


_TECHNICAL_FUSION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "technical"
    / "traditional_model_fusion"
)
if str(_TECHNICAL_FUSION_ROOT) not in sys.path:
    sys.path.insert(0, str(_TECHNICAL_FUSION_ROOT))

try:
    from fusion_traditional_models.fusion import fuse_signals
    from fusion_traditional_models.runner import (
        RunContext,
        load_rows_from_code,
        load_rows_from_csv,
        run_models,
    )
except Exception:  # pragma: no cover - analyze() 会返回带错误信息的 neutral Signal
    fuse_signals = None
    RunContext = None
    load_rows_from_code = None
    load_rows_from_csv = None
    run_models = None

try:
    from data_sources.cninfo import CninfoDataSource
except Exception:  # pragma: no cover - cninfo 为可选数据源
    CninfoDataSource = None

try:
    from skills.technical.volume_price_reversal.runtime import run_volume_price_reversal
except Exception:  # pragma: no cover
    run_volume_price_reversal = None

try:
    from skills.technical.company_evolution_analysis.runtime import run_company_evolution_analysis
except Exception:  # pragma: no cover
    run_company_evolution_analysis = None


class TechnicalAgent(BaseAgent):
    """技术指标 Agent（专家2组）"""

    signal_type = "technical"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="技术指标Agent", config=config or {})
        self.load_skills_from_domain("technical")
        self.load_skills_from_domain("data")

    def analyze(self, stock_code: str) -> Signal:
        """
        运行专家2组三类技术 Skill：

        1. traditional_model_fusion：四模型传统技术指标融合；
        2. volume_price_reversal：量价背离与短期反转识别；
        3. company_evolution_analysis：公司发展沿革/节点叙事作为技术信号背景约束。

        数据优先级：
        1. config["ohlcv_rows"] 注入的测试/上游数据；
        2. config["ohlcv_data_source"] 提供的 get_ohlcv/fetch_ohlcv 方法；
        3. config["csv_path"] 指定的 OHLCV CSV；
        4. 默认尝试实时行情（EastMoney -> Tencent 兜底）；
        5. 仅当显式配置 allow_synthetic_ohlcv=True 时使用离线合成样本。
        """
        self.log(f"开始技术指标分析：{stock_code}")

        if not all([fuse_signals, RunContext, run_models]):
            return self._create_error_signal(
                "传统指标融合模块导入失败，请检查 skills/technical/traditional_model_fusion",
                stock_code,
            )

        try:
            rows, data_status, uncertainties = self._load_ohlcv_rows(stock_code)
            if not rows:
                return self._create_missing_ohlcv_signal(stock_code, data_status, uncertainties)
            skill_results = [
                self._run_traditional_model_fusion(stock_code, rows, data_status),
                self._run_volume_price_reversal(stock_code, rows, data_status),
                self._run_company_evolution_analysis(stock_code),
            ]
            return self._merge_skill_results(stock_code, rows, data_status, skill_results, uncertainties)
        except Exception as exc:
            self.log(f"技术指标分析失败：{exc}", level="error")
            return self._create_error_signal(str(exc), stock_code)

    def _run_traditional_model_fusion(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
    ) -> Dict[str, Any]:
        """调用 traditional_model_fusion 工程化 Skill。"""
        ctx = RunContext(
            stock_code=stock_code,
            target=self.config.get("target") or stock_code,
            source_name=data_status,
        )
        model_signals = run_models(rows, ctx)
        result = fuse_signals(
            model_signals,
            threshold=float(self.config.get("fusion_threshold", 0.6)),
        )
        fused = result.get("fused_signal", {})
        test_report = self._build_traditional_model_fusion_test_report(
            stock_code=stock_code,
            rows=rows,
            data_status=data_status,
            fusion_result=result,
            ctx=ctx,
        )
        meta = dict(fused.get("meta") or {})
        meta.update(
            {
                "skill_name": "traditional_model_fusion",
                "model_signals": result.get("model_signals", []),
                "validation_report": result.get("validation_report", {}),
                "test_report": test_report,
                "traditional_model_fusion_test_report": test_report,
            }
        )
        return {
            "skill_name": "traditional_model_fusion",
            "direction": str(fused.get("direction", "neutral")),
            "confidence": self._clamp(float(fused.get("confidence", 0.2) or 0.2)),
            "reasoning": str(fused.get("reasoning") or "传统技术指标融合完成。"),
            "signals": list(fused.get("signals") or []),
            "weight": float(fused.get("weight", 1.0) or 1.0),
            "meta": meta,
        }

    def _build_traditional_model_fusion_test_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        fusion_result: Dict[str, Any],
        ctx: Any,
    ) -> Dict[str, Any]:
        """构造 traditional_model_fusion 的可回放测试报告。

        报告结构对齐 `fusion_traditional_models.cli` 的核心 JSON 输出：
        `fused_signal`、`model_signals`、`validation_report`，并补充 Agent 运行时
        的数据来源、样本区间和执行参数，便于 debug_ui/测试用例直接断言。
        """
        fused_signal = dict(fusion_result.get("fused_signal") or {})
        model_signals = list(fusion_result.get("model_signals") or [])
        validation_report = dict(fusion_result.get("validation_report") or {})
        first_row = rows[0] if rows else {}
        last_row = rows[-1] if rows else {}
        model_summary = []
        for item in model_signals:
            signal = item.get("signal") if isinstance(item, dict) else {}
            signal = signal if isinstance(signal, dict) else {}
            model_summary.append(
                {
                    "name": item.get("name") if isinstance(item, dict) else "",
                    "direction": signal.get("direction"),
                    "confidence": signal.get("confidence"),
                    "base_weight": item.get("base_weight") if isinstance(item, dict) else None,
                    "effective_weight": item.get("effective_weight") if isinstance(item, dict) else None,
                    "vote": item.get("vote") if isinstance(item, dict) else None,
                    "notes": item.get("notes", []) if isinstance(item, dict) else [],
                }
            )

        return {
            "report_type": "traditional_model_fusion_test_report",
            "report_version": "0.1-runtime",
            "generated_at": datetime.now().isoformat(),
            "runner": "fusion_traditional_models.runner.run_models + fusion_traditional_models.fusion.fuse_signals",
            "stock_code": stock_code,
            "target": getattr(ctx, "target", stock_code),
            "data_status": data_status,
            "rows_count": len(rows),
            "row_range": {
                "start": first_row.get("date", ""),
                "end": last_row.get("date", ""),
            },
            "data_period": self._rows_date_range(rows),
            "final_signal": {
                "direction": fused_signal.get("direction", "neutral"),
                "confidence": fused_signal.get("confidence", 0.2),
                "reasoning": fused_signal.get("reasoning", ""),
                "signals": list(fused_signal.get("signals") or []),
            },
            "model_count": len(model_signals),
            "model_summary": model_summary,
            "model_signals": model_signals,
            "validation_report": validation_report,
            "raw_fusion_result": {
                "fused_signal": fused_signal,
                "model_signals": model_signals,
                "validation_report": validation_report,
            },
        }

    def _run_volume_price_reversal(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
    ) -> Dict[str, Any]:
        """调用 volume_price_reversal skill runtime。"""
        if run_volume_price_reversal is None:
            return self._neutral_skill_result(
                "volume_price_reversal",
                "volume_price_reversal runtime 导入失败，保持中性。",
                weight=float(self.config.get("volume_price_reversal_weight", 0.35)),
                confidence=0.2,
                meta={"needs_human_review": True, "uncertainties": ["volume_price_reversal runtime 导入失败"]},
            )
        return run_volume_price_reversal(stock_code, rows, data_status, self.config)

    def _run_company_evolution_analysis(self, stock_code: str) -> Dict[str, Any]:
        """调用 company_evolution_analysis skill runtime。"""
        if run_company_evolution_analysis is None:
            return self._neutral_skill_result(
                "company_evolution_analysis",
                "company_evolution_analysis runtime 导入失败，保持中性。",
                weight=float(self.config.get("company_evolution_analysis_weight", 0.10)),
                confidence=0.2,
                meta={"needs_human_review": True, "uncertainties": ["company_evolution_analysis runtime 导入失败"]},
            )
        return run_company_evolution_analysis(stock_code, self.config, CninfoDataSource)

    def _merge_skill_results(
        self,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        skill_results: List[Dict[str, Any]],
        data_uncertainties: List[str],
    ) -> Signal:
        """以 traditional_model_fusion/run_models 融合结果为最终 Signal。

        `runner.run_models()` 是专家2组技术指标模型的唯一四模型执行入口，
        TechnicalAgent 不再在 Agent 层重新做二次方向加权，避免与
        `fusion_traditional_models.cli` 的输出口径不一致。其他两个 technical skill
        作为辅助分析写入 meta，不改写最终 direction/confidence/reasoning/signals。
        """
        primary = next((item for item in skill_results if item.get("skill_name") == "traditional_model_fusion"), None)
        if primary is None:
            return self._create_error_signal("缺少 traditional_model_fusion 结果，无法对齐 run_models 输出。", stock_code)

        auxiliary_results = [item for item in skill_results if item is not primary]
        all_uncertainties = list(data_uncertainties)
        for item in skill_results:
            meta_uncertainties = item.get("meta", {}).get("uncertainties", [])
            all_uncertainties.extend(meta_uncertainties)

        primary_meta = dict(primary.get("meta") or {})
        primary_meta.setdefault("uncertainties", [])
        primary_meta["uncertainties"] = self._dedupe_strings(
            list(primary_meta.get("uncertainties") or []) + all_uncertainties
        )
        data_period = self._rows_date_range(rows)
        analysis_reports = self._build_analysis_reports(
            stock_code=stock_code,
            rows=rows,
            data_status=data_status,
            data_period=data_period,
            skill_results=skill_results,
            data_uncertainties=data_uncertainties,
            primary_meta=primary_meta,
        )

        meta = {
            **primary_meta,
            "data_status": data_status,
            "rows_count": len(rows),
            "ohlcv_rows": self._chart_ohlcv_rows(rows),
            "data_period": data_period,
            "analysis_start_date": data_period.get("start"),
            "analysis_end_date": data_period.get("end"),
            "loaded_skills": self.list_skills(),
            "skill_results": {item.get("skill_name", "unknown_skill"): item for item in skill_results},
            "analysis_reports": analysis_reports,
            "reports": analysis_reports,
            "report_order": [
                "traditional_model_fusion",
                "company_evolution_analysis",
                "volume_price_reversal",
            ],
            "traditional_model_fusion": primary_meta,
            "volume_price_reversal": next((item.get("meta", {}) for item in skill_results if item.get("skill_name") == "volume_price_reversal"), {}),
            "company_evolution_analysis": next((item.get("meta", {}) for item in skill_results if item.get("skill_name") == "company_evolution_analysis"), {}),
            "technical_agent_policy": {
                "primary_skill": "traditional_model_fusion",
                "primary_execution": "fusion_traditional_models.runner.run_models + fuse_signals",
                "final_signal_aligned_with_run_models": True,
                "auxiliary_skills_do_not_override_direction": [item.get("skill_name") for item in auxiliary_results],
            },
            "auxiliary_signals": {
                item.get("skill_name", "unknown_skill"): {
                    "direction": item.get("direction"),
                    "confidence": item.get("confidence"),
                    "reasoning": item.get("reasoning"),
                    "signals": item.get("signals", []),
                }
                for item in auxiliary_results
            },
            "related_skills": [
                "traditional_model_fusion",
                "volume_price_reversal",
                "company_evolution_analysis",
            ],
            "uncertainties": self._dedupe_strings(all_uncertainties),
        }
        return Signal(
            direction=str(primary.get("direction", "neutral")),
            confidence=self._clamp(float(primary.get("confidence", 0.2) or 0.2)),
            reasoning=str(primary.get("reasoning") or "传统技术指标融合完成。"),
            signals=list(primary.get("signals") or []),
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            weight=float(primary.get("weight", self.config.get("weight", 1.0)) or 1.0),
            meta=meta,
        )

    def _build_analysis_reports(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        skill_results: List[Dict[str, Any]],
        data_uncertainties: List[str],
        primary_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按三个 technical Skill 的 SKILL.md 契约组织 Agent 返回报告。"""
        result_by_name = {item.get("skill_name", "unknown_skill"): item for item in skill_results}
        return {
            "traditional_model_fusion": self._build_traditional_model_fusion_analysis_report(
                stock_code=stock_code,
                rows=rows,
                data_status=data_status,
                data_period=data_period,
                primary=result_by_name.get("traditional_model_fusion", {}),
                primary_meta=primary_meta,
                data_uncertainties=data_uncertainties,
            ),
            "company_evolution_analysis": self._build_company_evolution_report(
                stock_code=stock_code,
                data_period=data_period,
                result=result_by_name.get("company_evolution_analysis", {}),
            ),
            "volume_price_reversal": self._build_volume_price_reversal_report(
                stock_code=stock_code,
                rows=rows,
                data_status=data_status,
                data_period=data_period,
                result=result_by_name.get("volume_price_reversal", {}),
            ),
        }

    def _build_traditional_model_fusion_analysis_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        primary: Dict[str, Any],
        primary_meta: Dict[str, Any],
        data_uncertainties: List[str],
    ) -> Dict[str, Any]:
        """按 traditional_model_fusion/SKILL.md 的中文解读模板组织报告。"""
        validation = dict(primary_meta.get("validation_report") or {})
        model_signals = list(primary_meta.get("model_signals") or [])
        test_report = dict(primary_meta.get("traditional_model_fusion_test_report") or primary_meta.get("test_report") or {})
        risk_level = str(primary_meta.get("risk_level") or "medium")
        needs_review = bool(primary_meta.get("needs_human_review", False))
        direction = str(primary.get("direction") or "neutral")
        confidence = self._clamp(float(primary.get("confidence", 0.2) or 0.2))
        threshold = ((validation.get("final_thresholds") or {}).get("threshold"))
        total_vote = validation.get("total_vote")
        model_rows = []
        model_interpretations = []
        for row in model_signals:
            signal = row.get("signal") if isinstance(row, dict) else {}
            signal = signal if isinstance(signal, dict) else {}
            meta = signal.get("meta") if isinstance(signal.get("meta"), dict) else {}
            name = str(row.get("name") or "unknown_model") if isinstance(row, dict) else "unknown_model"
            model_rows.append(
                {
                    "model": name,
                    "model_label": self._traditional_model_label(name),
                    "direction": signal.get("direction", "neutral"),
                    "confidence": signal.get("confidence", 0.0),
                    "risk_level": meta.get("risk_level", "medium"),
                    "needs_human_review": bool(meta.get("needs_human_review", False)),
                    "effective_weight": row.get("effective_weight") if isinstance(row, dict) else None,
                    "vote": row.get("vote") if isinstance(row, dict) else None,
                    "notes": row.get("notes", []) if isinstance(row, dict) else [],
                    "reasoning": signal.get("reasoning", ""),
                }
            )
            model_interpretations.append(
                {
                    "title": self._traditional_model_label(name),
                    "model": name,
                    "direction": signal.get("direction", "neutral"),
                    "summary": signal.get("reasoning", "未返回子模型解释。"),
                    "key_findings": list(meta.get("key_findings") or []),
                    "uncertainties": list(meta.get("uncertainties") or []),
                    "evidence": list(meta.get("evidence") or []),
                }
            )

        conflicts = list(validation.get("conflicts") or [])
        gates = list(validation.get("gates_triggered") or [])
        if direction == "neutral":
            neutral_note = "本次融合结果未跨过做多/做空阈值，或因门控/风险折扣保持保守，并不等同于明确看空。"
        else:
            neutral_note = f"本次融合结果为 {direction}，表示技术面方向倾向已跨过阈值，但仍不是交易指令。"

        sections = [
            {
                "title": "1. 一句话结论",
                "content": [
                    f"融合总信号：{direction}",
                    f"置信度：{confidence:.2f}",
                    f"风险等级：{risk_level}",
                    f"是否需要人工复核：{needs_review}",
                    str(primary.get("reasoning") or "传统技术指标融合完成。"),
                ],
            },
            {"title": "2. 这不是简单看多或看空", "content": [neutral_note]},
            {
                "title": "3. 融合投票是怎么来的",
                "content": [f"total_vote={self._format_optional_number(total_vote, 4)}，threshold={self._format_optional_number(threshold, 2)}，最终方向={direction}。"],
                "table": model_rows,
            },
            {"title": "4. 四个子模型分别在说什么", "items": model_interpretations},
            {
                "title": "5. 风险和人工复核点",
                "content": self._dedupe_strings(
                    list(primary_meta.get("risk_notes") or [])
                    + list(primary_meta.get("uncertainties") or [])
                    + list(data_uncertainties or [])
                )
                or ["未发现额外风险说明；仍需结合基本面、消息面和更长周期复核。"],
            },
            {
                "title": "6. 门控与冲突",
                "content": [
                    f"门控触发数量：{len(gates)}。",
                    f"方向冲突数量：{len(conflicts)}。",
                    "没有直接多空冲突时，也需关注未确认指标、有效权重调整和风险折扣。",
                ],
                "gates_triggered": gates,
                "conflicts": conflicts,
            },
            {
                "title": "7. 对结果的使用建议",
                "content": ["该结果适合作为技术面过滤器和复核线索，不是交易指令；建议结合更长周期、基本面、消息面和人工复核。"],
            },
            {
                "title": "8. 后续改进建议",
                "content": [
                    "数据：补充更稳定的复权口径、成交额、换手率和行业横截面数据。",
                    "模型：补充强趋势/弱趋势市场状态识别。",
                    "融合规则：持续复盘门控阈值和风险折扣。",
                    "回测验证：按行业、波动率和市值分层评估命中率。",
                ],
            },
        ]
        return {
            "report_type": "traditional_model_fusion_analysis_report",
            "skill_name": "traditional_model_fusion",
            "skill_contract": "skills/technical/traditional_model_fusion/SKILL.md",
            "title": f"{stock_code} 传统模型融合结果解读",
            "data_status": data_status,
            "rows_count": len(rows),
            "data_period": data_period,
            "summary": {
                "direction": direction,
                "confidence": confidence,
                "risk_level": risk_level,
                "needs_human_review": needs_review,
                "total_vote": total_vote,
                "threshold": threshold,
            },
            "sections": sections,
            "json_result": test_report.get("raw_fusion_result") or {
                "fused_signal": test_report.get("final_signal") or {},
                "model_signals": model_signals,
                "validation_report": validation,
            },
            "test_report": test_report,
        }

    def _build_company_evolution_report(self, *, stock_code: str, data_period: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """按 company_evolution_analysis/SKILL.md 的节点叙事结构组织报告。"""
        meta = dict(result.get("meta") or {})
        nodes = list(meta.get("nodes") or [])
        catalysts = list(meta.get("catalysts") or [])
        risks = list(meta.get("risks") or [])
        data_source_meta = dict(meta.get("data_source_meta") or {})
        requires_web_search = bool(meta.get("requires_web_search_for_full_report", True))
        if data_source_meta.get("provider") == "cninfo" and data_source_meta.get("status") == "success":
            status = "ready_from_cninfo_disclosures"
        elif data_source_meta.get("provider") == "cninfo":
            status = "cninfo_unavailable"
        elif nodes or catalysts or risks:
            status = "ready_from_injected_profile"
        else:
            status = "requires_web_search_or_injected_profile"
        if data_source_meta.get("provider") == "cninfo":
            integrity_note = str(result.get("reasoning") or "基于 cninfo 法定披露数据形成公司发展路径背景约束。")
        elif requires_web_search and status != "ready_from_injected_profile":
            integrity_note = "未注入联网检索后的公司节点事实；为避免编造，本报告只返回结构化占位和复核要求。"
        else:
            integrity_note = str(result.get("reasoning") or "基于注入的公司节点事实形成背景约束。")

        return {
            "report_type": "company_evolution_analysis_report",
            "skill_name": "company_evolution_analysis",
            "skill_contract": "skills/technical/company_evolution_analysis/SKILL.md",
            "title": f"{stock_code} 公司发展路径节点叙事分析",
            "status": status,
            "data_period": data_period,
            "summary": {
                "direction": result.get("direction", "neutral"),
                "confidence": result.get("confidence", 0.2),
                "requires_web_search_for_full_report": requires_web_search,
                "needs_human_review": bool(meta.get("needs_human_review", True)),
                "integrity_note": integrity_note,
                "source": meta.get("source"),
                "data_source_meta": data_source_meta,
            },
            "sections": [
                {
                    "title": "公司版图演进总览",
                    "content": self._dedupe_strings(
                        [integrity_note]
                        + ([f"cninfo 公告窗口：{data_source_meta.get('since')} 至 {data_source_meta.get('until')}，去重公告 {data_source_meta.get('announcements_total')} 条。"] if data_source_meta.get("provider") == "cninfo" else [])
                    ),
                },
                {
                    "title": "关键节点叙事",
                    "items": nodes,
                    "empty_state": "cninfo 公告未识别出并购、融资、控制权变更、资产交易等关键节点；完整发展史仍需结合招股书、年报正文和外部检索。",
                },
                {
                    "title": "当前格局陈述",
                    "content": list(meta.get("current_position") or []),
                    "empty_state": "未注入最新财报、市场份额、客户结构、竞争对手和现金流等事实。",
                },
                {
                    "title": "当前增长点的事实陈述",
                    "items": catalysts,
                    "empty_state": "未注入在建产能、研发转订单、新客户、新业务或产业变量契合度等可追溯事实。",
                },
                {
                    "title": "未来几年趋势的可能走向",
                    "content": list(meta.get("future_outlook") or []),
                    "empty_state": "需要基于真实节点、订单和产能事实分短期/中期/中长期推演。",
                },
                {
                    "title": "风险与挑战",
                    "items": risks,
                    "empty_state": "未注入技术路线、竞争、客户集中、地缘政治、业绩兑现或估值消化风险。",
                },
                {
                    "title": "cninfo 事实锚与复核要求",
                    "items": list(meta.get("evidence") or []),
                    "empty_state": "暂无 cninfo 事实锚。",
                },
            ],
            "raw_signal": result,
            "data_source_meta": data_source_meta,
        }

    def _build_volume_price_reversal_report(
        self,
        *,
        stock_code: str,
        rows: List[Dict[str, Any]],
        data_status: str,
        data_period: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """按 volume_price_reversal/SKILL.md 的标准 JSON + 摘要结构组织报告。"""
        meta = dict(result.get("meta") or {})
        direction = str(result.get("direction") or "neutral")
        confidence = self._clamp(float(result.get("confidence", 0.2) or 0.2))
        risk_level = str(meta.get("risk_level") or "medium")
        latest = rows[-1] if rows else {}
        metrics = dict(meta.get("metrics") or {})
        trigger_pattern = self._extract_trigger_pattern(list(result.get("signals") or []))
        standard_json = {
            "direction": direction,
            "confidence": confidence,
            "reasoning": result.get("reasoning", ""),
            "signals": list(result.get("signals") or []),
            "source": "volume-price-reversal",
            "signal_type": "technical",
            "stock_code": stock_code,
            "weight": float(result.get("weight", 1.0) or 1.0),
            "meta": {
                "output_version": meta.get("output_version", "0.1-runtime"),
                "skill_name": "volume-price-reversal",
                "owner_group": "专家2组（指标）",
                "target": stock_code,
                "period": data_status,
                "time_horizon": meta.get("time_horizon", "short"),
                "risk_level": risk_level,
                "key_findings": list(meta.get("key_findings") or []),
                "evidence": list(meta.get("evidence") or []),
                "risk_notes": list(meta.get("risk_notes") or []),
                "uncertainties": list(meta.get("uncertainties") or []),
                "needs_human_review": bool(meta.get("needs_human_review", False)),
            },
        }
        summary = {
            "target": stock_code,
            "direction": direction,
            "confidence": confidence,
            "risk_level": risk_level,
            "trigger_pattern": trigger_pattern,
            "signal_brief": self._short_text(str(result.get("reasoning") or ""), 80),
        }
        return {
            "report_type": "volume_price_reversal_report",
            "skill_name": "volume_price_reversal",
            "skill_contract": "skills/technical/volume_price_reversal/SKILL.md",
            "title": f"{stock_code} 高盛量价背离与反转信号识别",
            "data_status": data_status,
            "rows_count": len(rows),
            "data_period": data_period,
            "latest_bar": latest,
            "summary_table": [summary],
            "standard_json": standard_json,
            "markdown_summary": {
                "headline": f"{stock_code} — `{direction}` / {confidence:.2f} / {risk_level}",
                "overview": (list(result.get("signals") or [])[:1] or [result.get("reasoning") or "无形态触发。"])[0],
                "metrics": {
                    "day_return": metrics.get("day_return"),
                    "latest_volume": metrics.get("latest_volume"),
                    "latest_volume_display": metrics.get("latest_volume_display"),
                    "latest_volume_shares": metrics.get("latest_volume_shares"),
                    "avg_volume_20": metrics.get("avg_volume_20"),
                    "avg_volume_20_display": metrics.get("avg_volume_20_display"),
                    "avg_volume_20_shares": metrics.get("avg_volume_20_shares"),
                    "volume_unit": metrics.get("volume_unit"),
                    "volume_share_multiplier": metrics.get("volume_share_multiplier"),
                    "volume_ratio_20": metrics.get("volume_ratio_20"),
                    "vol_surp": metrics.get("vol_surp"),
                    "amount": metrics.get("amount"),
                    "avg_amount_20": metrics.get("avg_amount_20"),
                    "amount_threshold": metrics.get("amount_threshold"),
                },
                "evidence": list(meta.get("evidence") or []),
                "execution_constraints": list(meta.get("key_findings") or []) + list(meta.get("uncertainties") or []),
            },
            "raw_signal": result,
        }

    def _load_ohlcv_rows(self, stock_code: str) -> Tuple[List[Dict[str, Any]], str, List[str]]:
        """加载 OHLCV 行情，返回 rows、数据状态和不确定性说明。"""
        uncertainties: List[str] = []

        injected_rows = self.config.get("ohlcv_rows")
        if injected_rows:
            return self._normalize_ohlcv_rows(injected_rows), "config:ohlcv_rows", uncertainties

        data_source = self.config.get("ohlcv_data_source")
        if data_source is not None:
            rows = self._load_from_data_source(data_source, stock_code)
            if rows:
                return self._normalize_ohlcv_rows(rows), "config:ohlcv_data_source", uncertainties
            uncertainties.append("ohlcv_data_source 未返回有效 K 线数据。")

        csv_path = self.config.get("csv_path")
        if csv_path and load_rows_from_csv:
            rows, csv_uncertainties = load_rows_from_csv(str(csv_path))
            uncertainties.extend(csv_uncertainties)
            if rows:
                return self._normalize_ohlcv_rows(rows), f"csv:{csv_path}", uncertainties

        use_live_data = bool(self.config.get("use_live_data", True))
        if use_live_data and load_rows_from_code:
            start, end = self._default_date_range()
            rows, live_uncertainties = load_rows_from_code(
                stock_code,
                self.config.get("start", start),
                self.config.get("end", end),
                freq=self.config.get("freq", "D"),
                adjust=self.config.get("adjust", "qfq"),
            )
            uncertainties.extend(live_uncertainties)
            if rows:
                source_name = self._extract_market_source(live_uncertainties, f"market_data:{stock_code}")
                return self._normalize_ohlcv_rows(rows), source_name, uncertainties

        if self.config.get("allow_synthetic_ohlcv", False):
            uncertainties.append("已显式启用 allow_synthetic_ohlcv，使用离线 OHLCV 样本完成测试/演示。")
            return self._build_offline_rows(), "offline:synthetic_ohlcv", uncertainties

        uncertainties.append("未取得有效真实 OHLCV 行情；默认/生产路径不使用合成行情。")
        return [], "missing:ohlcv", uncertainties

    def _load_from_data_source(self, data_source: Any, stock_code: str) -> List[Dict[str, Any]]:
        """兼容不同注入数据源形态。"""
        if callable(data_source):
            data = data_source(stock_code)
        elif hasattr(data_source, "get_ohlcv"):
            data = data_source.get_ohlcv(stock_code)
        elif hasattr(data_source, "fetch_ohlcv"):
            data = data_source.fetch_ohlcv(stock_code)
        else:
            return []

        if isinstance(data, dict):
            return list(data.get("rows") or data.get("kline") or data.get("data") or [])
        return list(data or [])

    def _extract_market_source(self, uncertainties: List[str], default: str) -> str:
        for item in uncertainties:
            text = str(item)
            if text.startswith("行情来源："):
                return text.replace("行情来源：", "", 1)
        return default

    def _normalize_ohlcv_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把上游字段统一为 fusion_traditional_models 需要的 OHLCV 格式。"""
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            close = self._to_float(row.get("close"))
            high = self._to_float(row.get("high"))
            low = self._to_float(row.get("low"))
            volume = self._to_float(row.get("volume"))
            if close is None or high is None or low is None or volume is None:
                continue
            open_value = self._to_float(row.get("open"))
            normalized_row = {
                "date": str(row.get("date") or row.get("trade_date") or ""),
                "open": close if open_value is None else open_value,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for optional_key in ("amount", "turnover", "money", "turnover_rate", "volume_raw"):
                optional_value = self._to_float(row.get(optional_key))
                if optional_value is not None:
                    normalized_row[optional_key] = optional_value
            for optional_key in ("volume_unit", "volume_raw_unit"):
                if row.get(optional_key):
                    normalized_row[optional_key] = str(row.get(optional_key))
            normalized.append(normalized_row)
        return normalized

    def _build_offline_rows(self, periods: int = 120) -> List[Dict[str, Any]]:
        """构造确定性离线行情样本，避免无网环境下 Agent 退化为未实现。"""
        start = date.today() - timedelta(days=periods * 2)
        rows: List[Dict[str, Any]] = []
        previous_close = 10.0
        for idx in range(periods):
            trade_date = start + timedelta(days=idx)
            trend = idx * 0.035
            wave = math.sin(idx / 6.0) * 0.25
            close = 10.0 + trend + wave
            open_value = previous_close + math.sin(idx / 5.0) * 0.05
            high = max(open_value, close) + 0.18 + abs(math.sin(idx / 7.0)) * 0.08
            low = min(open_value, close) - 0.18 - abs(math.cos(idx / 8.0)) * 0.06
            volume = 1_000_000 + idx * 8_000 + int((math.sin(idx / 4.0) + 1.2) * 120_000)
            rows.append(
                {
                    "date": trade_date.isoformat(),
                    "open": round(open_value, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": float(volume),
                }
            )
            previous_close = close
        return rows

    def _default_date_range(self) -> Tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=240)
        return start.isoformat(), end.isoformat()

    def _neutral_skill_result(
        self,
        skill_name: str,
        reasoning: str,
        weight: float,
        confidence: float = 0.25,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "skill_name": skill_name,
            "direction": "neutral",
            "confidence": self._clamp(confidence),
            "reasoning": reasoning,
            "signals": [reasoning],
            "weight": weight,
            "meta": {"skill_name": skill_name, **(meta or {})},
        }

    def _clamp(self, value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        if math.isnan(value) or math.isinf(value):
            return lower
        return max(lower, min(upper, value))

    def _dedupe_strings(self, values: List[str]) -> List[str]:
        result: List[str] = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if text and text not in seen:
                result.append(text)
                seen.add(text)
        return result

    def _traditional_model_label(self, name: str) -> str:
        labels = {
            "volume_price_momentum_analysis": "量价模型",
            "advanced_trend_tracking_system": "趋势模型",
            "oscillator_check": "震荡模型",
            "trend_application_dulling_divergence": "钝化/背离模型",
        }
        return labels.get(name, name)

    def _format_optional_number(self, value: Any, digits: int = 2) -> str:
        number = self._to_float(value)
        if number is None:
            return "—"
        return f"{number:.{digits}f}"

    def _rows_date_range(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """返回实际参与分析的行情样本起止时间，便于校验数据与模型结果。"""
        if not rows:
            return {"start": "", "end": "", "rows_count": 0}
        start = str((rows[0] or {}).get("date") or (rows[0] or {}).get("trade_date") or "")[:10]
        end = str((rows[-1] or {}).get("date") or (rows[-1] or {}).get("trade_date") or "")[:10]
        return {"start": start, "end": end, "rows_count": len(rows)}

    def _chart_ohlcv_rows(self, rows: List[Dict[str, Any]], limit: int = 240) -> List[Dict[str, Any]]:
        """为 debug_ui K 线图输出精简 OHLCV 数据。"""
        chart_rows: List[Dict[str, Any]] = []
        for row in rows[-limit:]:
            chart_rows.append(
                {
                    "date": str(row.get("date") or row.get("trade_date") or "")[:10],
                    "open": self._to_float(row.get("open")),
                    "high": self._to_float(row.get("high")),
                    "low": self._to_float(row.get("low")),
                    "close": self._to_float(row.get("close")),
                    "volume": self._to_float(row.get("volume")),
                    "volume_unit": row.get("volume_unit") or "手",
                    "volume_raw_unit": row.get("volume_raw_unit"),
                }
            )
        return chart_rows

    def _extract_trigger_pattern(self, signals: List[str]) -> str:
        if not signals:
            return "无形态触发"
        first = str(signals[0])
        patterns = [
            "形态一·顶背离",
            "形态二·底背离",
            "形态三·量价齐升乏力",
            "形态四·量价齐跌衰竭",
            "十字星犹豫",
        ]
        for pattern in patterns:
            if pattern in first:
                return pattern
        if "无明确量价背离" in first or "无形态" in first:
            return "无形态触发"
        return first.split("：", 1)[0][:24]

    def _short_text(self, text: str, limit: int = 80) -> str:
        clean = " ".join(str(text or "").split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 1)] + "…"

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _create_error_signal(self, error_message: str, stock_code: str) -> Signal:
        return neutral_signal(
            confidence=0.1,
            reasoning=f"技术指标分析执行失败: {error_message}",
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            meta={
                "error": error_message,
                "needs_human_review": True,
                "loaded_skills": self.list_skills(),
            },
        )

    def _create_missing_ohlcv_signal(self, stock_code: str, data_status: str, uncertainties: List[str]) -> Signal:
        reasoning = "未取得有效真实 OHLCV 行情，默认/生产路径不会使用合成行情生成技术信号。"
        return neutral_signal(
            confidence=0.1,
            reasoning=reasoning,
            source=self.name,
            stock_code=stock_code,
            signal_type=self.signal_type,
            meta={
                "data_status": data_status or "missing:ohlcv",
                "rows_count": 0,
                "data_period": {"start": "", "end": "", "rows_count": 0},
                "analysis_start_date": "",
                "analysis_end_date": "",
                "loaded_skills": self.list_skills(),
                "needs_human_review": True,
                "uncertainties": self._dedupe_strings(list(uncertainties or []) + [reasoning]),
                "technical_agent_policy": {
                    "primary_skill": "traditional_model_fusion",
                    "final_signal_aligned_with_run_models": False,
                    "blocked_reason": "missing_real_ohlcv",
                },
            },
        )
