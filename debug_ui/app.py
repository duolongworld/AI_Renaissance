"""
AI Renaissance - Agent 本地调试工具（麦肯锡风格）

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


# ── Agent 注册表（小白只需在这里添加自己的 Agent）────────────────
# 格式：{"显示名称": {"module": "模块路径", "class": "类名"}}
AVAILABLE_AGENTS = {
    "财务专家Agent": {
        "module": "agents.research.financial_report.agent",
        "class": "FinancialReportAgent",
        "owner": "duolong",
        "description": "调用七步验证链（Skills），深度财报质量分析",
    },
    "舆情监控Agent": {
        "module": "agents.perception.sentiment.agent",
        "class": "SentimentAgent",
        "owner": "jerryyu",
        "description": "抓取东方财富股吧帖子，通过关键词分析市场情绪",
    },
    "行情数据Agent": {
        "module": "agents.perception.market_data.agent",
        "class": "MarketDataAgent",
        "owner": "jerryyu",
        "description": "从腾讯自选股获取K线、MA/BOLL/RSI指标、筹码分布",
    },
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
        })
    return jsonify(result)


@app.route("/api/debug", methods=["POST"])
def debug_agent():
    """
    调试 Agent 接口
    
    POST /api/debug
    Body: {"agent_name": "现金流验证Agent", "stock_code": "600519"}
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

    return jsonify({"success": True, "result": result})


@app.route("/api/reload", methods=["POST"])
def reload_agents():
    """重新加载 Agent 注册表（开发时不用重启服务）"""
    import importlib
    import agents.signal
    importlib.reload(agents.signal)
    return jsonify({"success": True, "message": "已重新加载"})


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("\n" + "=" * 60)
    print("  AI Renaissance - Agent 本地调试工具")
    print("  麦肯锡风格 · 简洁 · 高效")
    print("=" * 60)
    print("\n  浏览器打开：http://localhost:8080")
    print("  按 Ctrl+C 停止服务\n")
    app.run(host="0.0.0.0", port=8080, debug=True)
