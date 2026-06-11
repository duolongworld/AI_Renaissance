# 外部大模型接入说明

本文说明如何把用户自己的外部大模型服务接入 AI Renaissance。当前已接入 Orchestrator 可选 LLM 仲裁；共享调用入口也为后续专家 Agent 显式接入预留。默认运行方式仍是 `rule_based`。

## 配置原则

当前 CLI 配置入口是 `main.py --config`，默认读取 `config/default.yaml`，并由 `yaml.safe_load` 解析，所以外部大模型示例也沿用 `config/*.yaml`。

真实 URL、API key、token 可以写在私有配置里，但不能提交到仓库。已提交的 `config/llm.example.yaml` 只提供占位值；本地调试时复制成 `config/llm.private.yaml` 后再填写真实值。

`main.py --config` 会读取一个完整配置文件，不会自动和 `config/default.yaml` 合并。`config/llm.example.yaml` 因此是一份完整运行配置示例，不是补丁片段。

`llm.model` 是共享模型配置。它只在显式启用 LLM 的配置中生效，不代表系统默认调用大模型。

## 本地配置

复制示例配置，并在运行时通过 `--config` 显式指定：

```powershell
Copy-Item config/llm.example.yaml config/llm.private.yaml
```

`config/llm.private.yaml` 已被忽略，不应提交。把占位值替换成你自己的模型地址和 key：

```yaml
confidence_threshold: 0.6
bullish_weight: 1.0
bearish_weight: 1.0
risk_coefficient: 0.2
agent_timeout_seconds: 120

llm:
  model:
    provider: openai_compatible
    model_name: your-model-name
    base_url: https://your-llm-gateway.example.com/v1
    api_key: your-api-key

orchestrator:
  arbitration_mode: llm_framework
  llm_arbitration:
    skills:
      - name: llm_arbitration_policy
        path: skills/orchestrator/llm_arbitration_policy/SKILL.md
    mcp_servers: []
```

`mcp_servers` 可以为空；此时 LLM 只读取专家 Signals、编排 trace 和仲裁 Skill。

运行：

```powershell
python main.py --stock 600519 --config config/llm.private.yaml
```

## 专家 Agent 复用

后续专家 Agent 如需接入 LLM，建议复用统一入口；具体是否接入由各专家 Agent 的业务设计决定。

```python
from agents.llm import create_llm_client

agent.set_llm_client(create_llm_client(config))
```

当前宏观 Agent 已有 `set_llm_client()` 预留接口。其他专家 Agent 后续如需接入，也应保持自己的 `analyze(stock_code) -> Signal` 契约不变。

## CI 和部署

如果 CI 或部署平台不希望在配置文件里保存真实值，也可以使用环境变量名：

```yaml
llm:
  model:
    provider: openai_compatible
    model_name: your-model-name
    base_url_env: AI_RENAISSANCE_LLM_BASE_URL
    api_key_env: AI_RENAISSANCE_LLM_API_KEY
```

运行环境需要提供对应变量：

```powershell
$env:AI_RENAISSANCE_LLM_BASE_URL="https://your-llm-gateway.example.com/v1"
$env:AI_RENAISSANCE_LLM_API_KEY="your-api-key"
```

## 安全要求

- 不提交 `config/*.private.yaml`。
- 不在已提交文件里写真实 `api_key`、`base_url`、token 或 header。
- 如果发生误提交，立即撤销凭据并重新生成。
