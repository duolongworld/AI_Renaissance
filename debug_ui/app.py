"""
AI Renaissance - Agent 本地调试工具（麦肯锡风格）

8 Agent + N Skill 架构

运行方式：
    python debug_ui/app.py

然后在浏览器打开 http://localhost:8080
"""

from flask import Flask, render_template, request, jsonify
import json
import math
import sys
import os
import importlib
import traceback

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"))

# ── 全局兜底：NaN / Infinity → null（JSON 标准不支持 NaN/Infinity）────────
class _SafeJSONEncoder(json.JSONEncoder):
    """将 float('nan'), float('inf'), float('-inf') 序列化为 null"""
    def default(self, o):
        return super().default(o)
    def encode(self, o):
        return super().encode(self._sanitize(o))
    def iterencode(self, o, _one_shot=False):
        return super().iterencode(self._sanitize(o), _one_shot)
    @staticmethod
    def _sanitize(o):
        if isinstance(o, float):
            if math.isnan(o) or math.isinf(o):
                return None
            return o
        if isinstance(o, dict):
            return {k: _SafeJSONEncoder._sanitize(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_SafeJSONEncoder._sanitize(v) for v in o]
        return o

app.json_encoder = _SafeJSONEncoder

# 把项目根目录加入路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


# ── 7个专家Agent注册表 ──────────────────────────────────
# 格式：{"显示名称": {"module": "模块路径", "class": "类名", "owner": "负责组"}}
AVAILABLE_AGENTS = {
    "财务分析Agent": {
        "module": "agents.financial.agent",
        "class": "FinancialAgent",
        "owner": "专家1组",
        "description": "财报质量七步验证链，利润真实性分析",
        "signal_type": "financial",
    },
    "技术指标Agent": {
        "module": "agents.technical.agent",
        "class": "TechnicalAgent",
        "owner": "专家2组",
        "description": "量价技术指标、趋势识别、支撑压力位",
        "signal_type": "technical",
    },
    "资金流向Agent": {
        "module": "agents.fundflow.agent",
        "class": "FundflowAgent",
        "owner": "专家3组",
        "description": "主力资金追踪、北向资金、聪明钱动向",
        "signal_type": "fundflow",
    },
    "宏观周期Agent": {
        "module": "agents.macro.agent",
        "class": "MacroAgent",
        "owner": "专家4组",
        "description": "利率/汇率/PMI解读，大周期位置判断",
        "signal_type": "macro",
    },
    "行业景气Agent": {
        "module": "agents.industry.agent",
        "class": "IndustryAgent",
        "owner": "专家5组",
        "description": "产业链景气度、行业拐点、竞争格局",
        "signal_type": "industry",
    },
    "舆情情感Agent": {
        "module": "agents.news_agent.agent",
        "class": "NewsAgent",
        "owner": "专家6组",
        "description": "大盘、行业、个股情绪温度三层辅助，数据计算较多，加载运行需要5分钟左右",
        "signal_type": "news",
    },
    "风险预警Agent": {
        "module": "agents.risk.agent",
        "class": "RiskAgent",
        "owner": "专家7组",
        "description": "尾部风险识别、仓位上限、守住不爆仓的底线",
        "signal_type": "risk",
    },
}


def load_agent(module_path: str, class_name: str):
    """动态加载 Agent"""
    mod = importlib.import_module(module_path)
    agent_class = getattr(mod, class_name)
    return agent_class(config={})


@app.route("/")
def index():
    """渲染主页面"""
    return render_template(
        "index.html",
        agents=AVAILABLE_AGENTS,
    )


@app.route("/data")
def data_skills_page():
    """渲染数据 Skill 测试页面"""
    return render_template("data.html")


@app.route("/api/agents", methods=["GET"])
def list_agents():
    """返回所有可用 Agent（供前端动态加载）"""
    result = []
    for name, info in AVAILABLE_AGENTS.items():
        result.append({
            "name": name,
            "owner": info.get("owner", "未指定"),
            "description": info.get("description", ""),
            "signal_type": info.get("signal_type", ""),
        })
    return jsonify(result)


@app.route("/api/debug", methods=["POST"])
def debug_agent():
    """
    调试 Agent 接口

    POST /api/debug
    Body: {"agent_name": "财务分析Agent", "stock_code": "600519"}
    """
    data = request.get_json(force=True)
    agent_name = data.get("agent_name", "")
    stock_code = data.get("stock_code", "").strip()

    if not agent_name:
        return jsonify({"error": "请选择 Agent"}), 400
    if not stock_code:
        return jsonify({"error": "请输入股票代码"}), 400

    if agent_name not in AVAILABLE_AGENTS:
        return jsonify({"error": f"Agent [{agent_name}] 未找到，请在 app.py 中注册"}), 400

    info = AVAILABLE_AGENTS[agent_name]

    try:
        agent = load_agent(info["module"], info["class"])
    except Exception as e:
        return jsonify({
            "error": f"加载 Agent 失败：{str(e)}",
            "traceback": traceback.format_exc(),
        }), 500

    try:
        signal = agent.analyze(stock_code)
    except Exception as e:
        return jsonify({
            "error": f"Agent 执行失败：{str(e)}",
            "traceback": traceback.format_exc(),
        }), 500

    # 把 Signal 对象转成字典
    if hasattr(signal, "to_dict"):
        result = signal.to_dict()
    else:
        result = {
            "direction": getattr(signal, "direction", "unknown"),
            "confidence": getattr(signal, "confidence", 0.0),
            "reasoning": getattr(signal, "reasoning", ""),
            "source": getattr(signal, "source", agent_name),
        }

    # 提取 reasoning_steps（存储在 meta 中）
    if hasattr(signal, "meta") and signal.meta:
        result["reasoning_steps"] = signal.meta.get("reasoning_steps", [])

    # 附带 Agent 的已加载 Skill 列表
    if hasattr(agent, "list_skills"):
        result["loaded_skills"] = agent.list_skills()

    return jsonify({"success": True, "result": result})


@app.route("/api/technical_debug", methods=["POST"])
def debug_technical_agent():
    """
    Technical Agent 专项测试接口。

    POST /api/technical_debug
    Body: {
      "stock_code": "600519",
      "data_mode": "live|offline|sample",
      "fusion_threshold": 0.6,
      "ohlcv_rows": [{date, open, high, low, close, volume}, ...]
    }
    """
    data = request.get_json(force=True)
    stock_code = data.get("stock_code", "").strip()
    data_mode = data.get("data_mode", "live")

    if not stock_code:
        return jsonify({"error": "请输入股票代码"}), 400

    config = {
        "fusion_threshold": float(data.get("fusion_threshold", 0.6) or 0.6),
    }

    if data_mode == "live":
        config["use_live_data"] = True
        config["adjust"] = data.get("adjust") or "qfq"
        for key in ("start", "end", "freq", "adjust"):
            if data.get(key):
                config[key] = data[key]
    elif data_mode == "offline":
        config["use_live_data"] = False
        config["allow_synthetic_ohlcv"] = True
    elif data_mode == "sample":
        rows = data.get("ohlcv_rows") or []
        if not isinstance(rows, list) or not rows:
            return jsonify({"error": "sample 模式需要提供非空 ohlcv_rows 数组"}), 400
        config["ohlcv_rows"] = rows
    else:
        return jsonify({"error": f"未知 technical data_mode: {data_mode}"}), 400

    try:
        from agents.technical.agent import TechnicalAgent

        agent = TechnicalAgent(config=config)
        signal = agent.analyze(stock_code)
        result = signal.to_dict() if hasattr(signal, "to_dict") else dict(signal)
        if hasattr(agent, "list_skills"):
            result["loaded_skills"] = agent.list_skills()
        meta = result.get("meta", {}) or {}
        analysis_reports = meta.get("analysis_reports") or meta.get("reports") or {}
        company_report = analysis_reports.get("company_evolution_analysis", {}) if isinstance(analysis_reports, dict) else {}
        return jsonify({
            "success": True,
            "result": result,
            "config": config,
            "technical_reports": analysis_reports,
            "technical_debug": {
                "data_mode": data_mode,
                "data_status": meta.get("data_status"),
                "rows_count": meta.get("rows_count"),
                "data_period": meta.get("data_period", {}),
                "analysis_start_date": meta.get("analysis_start_date"),
                "analysis_end_date": meta.get("analysis_end_date"),
                "primary_skill": meta.get("technical_agent_policy", {}).get("primary_skill"),
                "final_signal_aligned_with_run_models": meta.get("technical_agent_policy", {}).get("final_signal_aligned_with_run_models"),
                "report_order": meta.get("report_order", []),
                "report_parts": list(analysis_reports.keys()) if isinstance(analysis_reports, dict) else [],
                "company_data_source": (company_report.get("summary", {}) or {}).get("source"),
                "company_data_source_meta": company_report.get("data_source_meta", {}),
            },
        })
    except Exception as e:
        return jsonify({
            "error": f"Technical Agent 执行失败：{str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


@app.route("/api/orchestrate", methods=["POST"])
def orchestrate():
    """
    编排全流程：调用所有专家Agent + 仲裁

    POST /api/orchestrate
    Body: {"stock_code": "600519"}
    """
    data = request.get_json(force=True)
    stock_code = data.get("stock_code", "").strip()

    if not stock_code:
        return jsonify({"error": "请输入股票代码"}), 400

    try:
        from agents.orchestrator.agent import OrchestratorAgent
        orchestrator = OrchestratorAgent(config={})

        # 注册所有专家Agent
        for name, info in AVAILABLE_AGENTS.items():
            try:
                agent = load_agent(info["module"], info["class"])
                orchestrator.register_expert(agent)
            except Exception as e:
                logger.error(f"注册专家Agent [{name}] 失败：{e}")

        # 执行编排
        result = orchestrator.analyze(stock_code)

        return jsonify({
            "success": True,
            "result": {
                "decision": result.decision,
                "direction": result.direction,
                "confidence": result.confidence,
                "position_ratio": result.position_ratio,
                "reasoning": result.reasoning,
                "signals_summary": result.signals_summary,
                "risks": result.risks,
                "reasoning_chain": result.reasoning_chain,
                "scope_trace": result.scope_trace,
            }
        })
    except Exception as e:
        return jsonify({
            "error": f"编排执行失败：{str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


@app.route("/api/reload", methods=["POST"])
def reload_agents():
    """重新加载 Agent 注册表（开发时不用重启服务）"""
    import agents.signal
    importlib.reload(agents.signal)
    return jsonify({"success": True, "message": "已重新加载"})


# ── 数据 Skill 测试接口 ─────────────────────────────────

DATA_SKILLS = {
    "腾讯财经K线": {
        "type": "skill_script",
        "module": "skills.data.tencent_technical.scripts.fetch_kline",
        "function": "fetch_kline_with_indicators",
        "default_params": {"stock_code": "600519", "k_type": "day", "num": 60},
        "params_example": {"k_type": "day", "num": 60},
        "param_docs": {
            "k_type": "K线周期；可选 day / week / month / m1 / m5 / m15 / m30 / m60",
            "num": "拉取条数；日K 最多 640，分钟K 最多 320",
        },
        "description": "获取K线数据（OHLCV）+ 技术指标（MA/BOLL/RSI）",
        "result_type": "kline",
        "requires_stock": True,
    },
    "东方财富财务": {
        "module": "data_sources.eastmoney",
        "class": "EastMoneyDataSource",
        "test_method": "get_financial_data",
        "default_params": {"stock_code": "600519"},
        "params_example": {},
        "param_docs": {},
        "description": "获取三大财务报表（资产负债表/利润表/现金流量表）",
        "result_type": "json",
        "requires_stock": True,
    },
    "AkShare 资金流全景": {
        "module": "data_sources.akshare",
        "class": "AkshareDataSource",
        "test_method": "get_fundflow_snapshot",
        "default_params": {
            "stock_code": "600519",
            "indicator": "今日",
            "flow_limit": 10,
            "sector_top_n": 10,
            "concept_limit": 10,
        },
        "params_example": {
            "indicator": "今日",
            "flow_limit": 10,
            "sector_top_n": 10,
            "concept_limit": 10,
        },
        "param_docs": {
            "indicator": "板块资金统计口径；可选 今日 / 5日 / 10日",
            "flow_limit": "个股资金流与大盘资金流返回最近多少条记录",
            "sector_top_n": "行业资金榜、概念资金榜各展示前多少条",
            "concept_limit": "个股概念标签最多返回多少条",
        },
        "description": "一次返回个股基础信息、个股主力资金、相关板块资金、大盘主力资金与北向资金概览",
        "result_type": "json",
        "requires_stock": True,
    },
}


@app.route("/api/data_skills", methods=["GET"])
def list_data_skills():
    """返回所有可测试的数据 Skill"""
    result = []
    for name, info in DATA_SKILLS.items():
        result.append({
            "name": name,
            "description": info.get("description", ""),
            "default_params": info.get("default_params", {}),
            "params_example": info.get("params_example", {}),
            "param_docs": info.get("param_docs", {}),
            "result_type": info.get("result_type", "json"),
            "requires_stock": info.get("requires_stock", True),
        })
    return jsonify(result)


@app.route("/api/test_skill", methods=["POST"])
def test_data_skill():
    """
    测试数据 Skill 接口

    POST /api/test_skill
    Body: {"skill_name": "腾讯财经K线", "stock_code": "600519", "params": {...}}
    """
    data = request.get_json(force=True)
    skill_name = data.get("skill_name", "")
    stock_code = data.get("stock_code", "").strip()

    if not skill_name:
        return jsonify({"error": "请选择数据 Skill"}), 400

    if skill_name not in DATA_SKILLS:
        return jsonify({"error": f"数据 Skill [{skill_name}] 未找到"}), 400

    info = DATA_SKILLS[skill_name]

    # 构建参数
    params = dict(info.get("default_params", {}))
    if stock_code:
        params["stock_code"] = stock_code
    extra = data.get("params", {})
    params.update(extra)

    try:
        skill_type = info.get("type", "class")
        if skill_type == "skill_script":
            # Skill 脚本模式：直接调用函数
            mod = importlib.import_module(info["module"])
            func = getattr(mod, info["function"])
            result = func(**params)
        else:
            # 类模式：实例化后调用方法
            mod = importlib.import_module(info["module"])
            cls = getattr(mod, info["class"])
            instance = cls()
            method = getattr(instance, info["test_method"])
            result = method(**params)
    except Exception as e:
        return jsonify({
            "error": f"执行失败：{str(e)}",
            "traceback": traceback.format_exc(),
        }), 500

    return jsonify({
        "success": True,
        "skill_name": skill_name,
        "params": params,
        "result": result,
    })


def _enrich_tencent_kline(result: dict) -> dict:
    """为腾讯K线数据补充计算 MA/BOLL/RSI 指标"""
    kline = result.get("kline", [])
    if not kline:
        return result

    closes = [item["close"] for item in kline if item.get("close") is not None]

    for i, item in enumerate(kline):
        # MA
        ma_values = {}
        for p in [5, 10, 20, 60]:
            if i >= p - 1 and len(closes) >= p:
                window = closes[i - p + 1:i + 1]
                ma_values[f"ma{p}"] = round(sum(window) / p, 3)
            else:
                ma_values[f"ma{p}"] = None
        item["ma"] = ma_values

        # BOLL
        period = 20
        if i >= period - 1 and len(closes) >= period:
            window = closes[i - period + 1:i + 1]
            middle = sum(window) / period
            variance = sum((c - middle) ** 2 for c in window) / period
            std = variance ** 0.5
            item["boll"] = {
                "upper": round(middle + 2 * std, 3),
                "middle": round(middle, 3),
                "lower": round(middle - 2 * std, 3),
            }
        else:
            item["boll"] = {"upper": None, "middle": None, "lower": None}

        # RSI
        changes = [closes[j] - closes[j - 1] for j in range(1, len(closes))]
        rsi_values = {}
        for p in [6, 12, 14, 24]:
            if i >= p and i <= len(changes):
                window = changes[i - p:i]
                gains = [c for c in window if c > 0]
                losses = [-c for c in window if c < 0]
                avg_gain = sum(gains) / p if gains else 0
                avg_loss = sum(losses) / p if losses else 0
                if avg_loss == 0:
                    rsi_values[f"rsi{p}"] = 100.0
                else:
                    rsi_values[f"rsi{p}"] = round(100 - 100 / (1 + avg_gain / avg_loss), 2)
            else:
                rsi_values[f"rsi{p}"] = None
        item["rsi"] = rsi_values

    result["indicators"] = ["ma", "boll", "rsi"]
    return result


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("\n" + "=" * 60)
    print("  AI Renaissance - Agent 本地调试工具")
    print("  8 Agent + N Skill 架构 · 麦肯锡风格")
    print("=" * 60)
    print("\n  浏览器打开：http://localhost:8080")
    print("  按 Ctrl+C 停止服务\n")
    app.run(host="0.0.0.0", port=8080, debug=True)
