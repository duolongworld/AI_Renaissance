"""
财务专家 Agent

调用 skills/financial_report_analysis/SKILL.md 中的七步验证链，
对指定股票进行深度财报分析，输出标准 Signal。

架构关系：
  Skill（魂）  ← skills/financial_report_analysis/SKILL.md
  Agent（壳）  ← 本文件（负责调用 Skill，封装 Signal）
"""

from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal


class FinancialReportAgent(BaseAgent):
    """
    财务专家 Agent

    触发逻辑：
      1. 加载 skills/financial_report_analysis/SKILL.md 作为分析框架
      2. 通过东方财富 API 拉取三张表数据
      3. 将数据和 Skill Prompt 一起发给 LLM 分析
      4. 解析 LLM 输出，封装成标准 Signal 返回
    """

    def __init__(self, config: Optional[dict] = None):
        super().__init__(name="财务专家Agent", config=config or {})
        self.skill_path = (
            Path(__file__).resolve().parent.parent.parent
            / "skills" / "financial_report_analysis" / "SKILL.md"
        )
        self.skill_content = ""
        self._load_skill()

    def _load_skill(self):
        """加载 Skill 文件内容"""
        try:
            self.skill_content = self.skill_path.read_text(encoding="utf-8")
            self.log(f"已加载 Skill：{self.skill_path}")
        except FileNotFoundError:
            self.log(f"Skill 文件不存在：{self.skill_path}", "error")
            self.skill_content = "# 财报分析\n请分析现金流、合同负债、资本开支等指标。"

    # ── 公开入口 ────────────────────────────────────────────────

    def analyze(self, stock_code: str) -> Signal:
        """
        分析指定股票的财报质量

        Args:
            stock_code: 股票代码，支持格式：600519、SZ300757、SH600519

        Returns:
            标准 Signal 对象
        """
        self.log(f"开始分析股票：{stock_code}")

        # 1. 标准化股票代码
        eastmoney_code = self._normalize_code(stock_code)
        if not eastmoney_code:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"无法识别股票代码：{stock_code}",
                source=self.name,
                stock_code=stock_code,
            )

        # 2. 拉取财务数据
        financial_data = self._fetch_financial_data(eastmoney_code)
        if not financial_data:
            return neutral_signal(
                confidence=0.1,
                reasoning=f"无法获取股票 {stock_code} 的财务数据",
                source=self.name,
                stock_code=stock_code,
            )

        # 3. 调用 LLM 按 Skill 框架分析
        analysis_result = self._analyze_with_skill(financial_data, stock_code)
        if not analysis_result:
            return neutral_signal(
                confidence=0.3,
                reasoning="LLM 分析未返回有效结果，建议人工复核",
                source=self.name,
                stock_code=stock_code,
            )

        # 4. 解析结果，封装成 Signal
        return self._build_signal(analysis_result, stock_code)

    # ── 股票代码标准化 ────────────────────────────────────────

    def _normalize_code(self, code: str) -> str:
        """
        把用户输入的股票代码转成东方财富 API 需要的格式
        600519   → SZ600519?  → 实际沪市用 SH，深市用 SZ
        注意：东方财富 API 参数 code=SZ300757（需要带前缀）
        """
        code = code.strip().upper()
        if code.startswith("SH") or code.startswith("SZ"):
            return code
        if code.startswith("6"):
            return f"SH{code}"
        if code.startswith(("0", "3")):
            return f"SZ{code}"
        self.log(f"无法识别的股票代码格式：{code}", "warning")
        return ""

    # ── 获取财务数据 ─────────────────────────────────────────

    def _fetch_financial_data(self, eastmoney_code: str) -> dict:
        """
        通过东方财富 API 拉取三张表的最新一期数据

        API 文档见 Skill 文件中的"执行流程"章节
        """
        if not HAS_REQUESTS:
            self.log("requests 库未安装，无法获取财务数据", "error")
            return {}

        base_url = "https://emweb.eastmoney.com/NewFinanceAnalysis"
        report_date = "2026-03-31"  # 最新披露期，后续应改为动态获取

        urls = {
            "balance":   f"{base_url}/zcfzbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
            "income":     f"{base_url}/lbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
            "cashflow":   f"{base_url}/xjlIbAjaxNew?companyType=4&reportDateType=0&reportType=1&dates={report_date}&code={eastmoney_code}",
        }

        results = {}
        for sheet_name, url in urls.items():
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                results[sheet_name] = resp.json()
                self.log(f"获取{sheet_name}数据成功：{eastmoney_code}")
            except Exception as e:
                self.log(f"获取{sheet_name}数据失败：{e}", "error")
                results[sheet_name] = {}

        return results

    # ── 调用 Skill 分析 ─────────────────────────────────────

    def _analyze_with_skill(self, financial_data: dict, stock_code: str) -> dict:
        """
        把 Skill Prompt + 财务数据一起发给 LLM，
        按 Skill 中的七步验证链进行分析。

        返回解析后的字典，包含 direction / confidence / reasoning / signals。
        """
        # 构造用户消息：把财务数据塞进去
        user_message = self._format_data_for_llm(financial_data, stock_code)

        # ── 方式 A：有 OpenAI API Key，直接调用 ──
        api_key = self.config.get("openai_api_key") or ""
        if api_key and HAS_REQUESTS:
            return self._call_openai(api_key, user_message)

        # ── 方式 B：无 API Key，用规则引擎本地计算（降级方案）──
        self.log("未配置 OpenAI API Key，使用本地规则引擎降级分析")
        return self._fallback_rule_engine(financial_data, stock_code)

    def _format_data_for_llm(self, financial_data: dict, stock_code: str) -> str:
        """把 API 返回的 JSON 数据格式化成 LLM 可读的文本"""
        parts = [f"股票代码：{stock_code}\n"]
        for sheet_name, data in financial_data.items():
            parts.append(f"## {sheet_name}\n{data}\n")
        return "\n".join(parts)

    def _call_openai(self, api_key: str, user_message: str) -> dict:
        """调用 OpenAI API 按 Skill 框架分析"""
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": self.config.get("model", "gpt-4o"),
                    "messages": [
                        {"role": "system", "content": self.skill_content},
                        {"role": "user",   "content": user_message},
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            import json
            return json.loads(resp.json()["choices"][0]["message"]["content"])
        except Exception as e:
            self.log(f"OpenAI API 调用失败：{e}", "error")
            return {}

    # ── 降级方案：本地规则引擎 ─────────────────────────────

    def _fallback_rule_engine(self, financial_data: dict, stock_code: str) -> dict:
        """
        本地规则引擎（不依赖 LLM）
        实现 Skill 中「第一步：看现金」的核心逻辑
        """
        try:
            # 尝试从 API 返回的结构化数据里提取核心字段
            # 东方财富 API 返回格式：{"data":[{"ORGCODE":"...","DATATYPE":"...",...}]}
            balance_data = financial_data.get("balance", {}).get("data", [{}])[0]
            income_data  = financial_data.get("income",  {}).get("data", [{}])[0]
            cashflow_data = financial_data.get("cashflow", {}).get("data", [{}])[0]

            # 提取核心数值（字段名以东方财富 API 实际返回为准，这里用常见字段）
            # 不同股票的字段名可能不同，做好容错
            net_profit = self._safe_float(income_data.get("PARENTPROFIT", 0))
            cash_flow  = self._safe_float(cashflow_data.get("OPERATENETCASHFLOW", 0))

            if net_profit == 0:
                return {
                    "direction": "neutral",
                    "confidence": 0.3,
                    "reasoning": "净利润为0，无法计算现金流比率",
                    "signals": ["净利润为0"],
                }

            ratio = cash_flow / abs(net_profit)
            if ratio > 1.2:
                return {
                    "direction": "bullish",
                    "confidence": min(ratio / 2.0, 0.95),
                    "reasoning": f"经营现金流/净利润 = {ratio:.2f}，利润质量优秀（Skill七步验证链第一步）",
                    "signals": [f"现金流比率{ratio:.2f}", "利润有现金支撑"],
                }
            elif ratio < 0.8:
                return {
                    "direction": "bearish",
                    "confidence": min((1.0 - ratio) / 0.5, 0.9),
                    "reasoning": f"经营现金流/净利润 = {ratio:.2f}，利润质量存疑（Skill七步验证链第一步）",
                    "signals": [f"现金流比率{ratio:.2f}", "利润现金支撑不足"],
                }
            else:
                return {
                    "direction": "neutral",
                    "confidence": 0.5,
                    "reasoning": f"经营现金流/净利润 = {ratio:.2f}，处于合理区间",
                    "signals": [f"现金流比率{ratio:.2f}"],
                }
        except Exception as e:
            self.log(f"本地规则引擎出错：{e}", "error")
            return {
                "direction": "neutral",
                "confidence": 0.2,
                "reasoning": f"本地分析出错：{str(e)}",
                "signals": [],
            }

    def _safe_float(self, val) -> float:
        """安全转换为 float"""
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    # ── 封装 Signal ─────────────────────────────────────────

    def _build_signal(self, result: dict, stock_code: str) -> Signal:
        """把 LLM / 规则引擎的输出封装成标准 Signal"""
        direction  = result.get("direction", "neutral")
        confidence = result.get("confidence", 0.5)
        reasoning  = result.get("reasoning", "")
        signals    = result.get("signals", [])

        if direction == "bullish":
            return bullish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type="financial",
                meta={"agent": "FinancialReportAgent"},
            )
        elif direction == "bearish":
            return bearish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type="financial",
                meta={"agent": "FinancialReportAgent"},
            )
        else:
            return neutral_signal(
                confidence=confidence,
                reasoning=reasoning or "无法确定明确方向",
                source=self.name,
                stock_code=stock_code,
                signal_type="financial",
            )
