"""
AI Renaissance - Agent 本地调试工具（麦肯锡风格）

8 Agent + N Skill 架构

运行方式：
    python debug_ui/app.py

然后在浏览器打开 http://localhost:8080
"""

from flask import Flask, render_template, request, jsonify
import sys
import os
import importlib
import traceback

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), "templates"),
            static_folder=os.path.join(os.path.dirname(__file__), "static"))

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
        "description": "新闻情感分析、社交情绪追踪、情绪交易信号",
        "signal_type": "news",
    },
    "风险预警Agent": {
        "module": "agents.risk.agent",
        "class": "RiskAgent",
        "owner": "专家7组",
        "description": "尾部风险识别、仓位上限、守住不爆仓的底线",
        "signal_type": "risk",
    },
    "行情数据Agent": {
        "module": "agents.perception.market_data.agent",
        "class": "MarketDataAgent",
        "owner": "jerryyu",
        "description": "从腾讯自选股获取K线、MA/BOLL/RSI指标、筹码分布",
    }
    # ↓ 小白在这里添加你自己的 Agent ↓
    # "你的Agent名": {
    #     "module": "agents.research.你的路径.agent",
    #     "class": "你的Agent类名",
    #     "owner": "你的名字",
    #     "description": "一句话描述",
    # },

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
