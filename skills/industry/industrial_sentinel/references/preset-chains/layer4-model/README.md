# Layer 4: AI模型层

## ai-model 预设

提供 AI 模型产业链的完整三层分析框架：

- **上游**: 算力基础设施（GPU集群）、训练数据/标注、基础模型架构
- **中游**: 闭源大模型（GPT/Claude/文心）、开源大模型（Llama/通义/DeepSeek）、模型微调服务
- **下游**: AI Agent/应用、终端推理/端侧模型

交叉验证覆盖上述上下游环节及外部指标（API调用价格趋势、开源模型MMLU分数）。

## 使用方式

```python
from runtime import run_industrial_sentinel
result = run_industrial_sentinel("BIDU")  # 百度 → ai-model preset
```
