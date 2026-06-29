# 财务 Agent 回测

本目录存放财务 Agent 的回测资产，不属于 `financial_report_analysis` 运行时 Skill。

目录职责：

- `run_backtest.py`：固定样本池回测执行器。
- `sample_pool_v1.csv`：第一版固定样本池。
- `records/`：回测记录和 Markdown 结果报告。
- `iteration_logs/`：基于回测结论形成的后续迭代记录。
- `output/financial_backtest/`：本地逐样本 JSON 审计数据和三表缓存，继续不提交 Git。

## 执行

从仓库根目录运行：

```bash
.venv/bin/python -m agents.financial.backtests.run_backtest
```

如果只允许使用本地缓存，运行：

```bash
.venv/bin/python -m agents.financial.backtests.run_backtest --require-cache
```

执行器会：

- 固定读取 `sample_pool_v1.csv`；
- 读取或缓存 51 家公司所需历史三表；
- 对每个公司、每个信号季度调用 `FinancialAgent.analyze()`；
- 按下一季度单季归母净利润同比方向生成真实标签；
- 将 Markdown 回测报告写入 `agents/financial/backtests/records/financial_agent_backtest_latest.md`；
- 将逐样本 JSON 审计数据和三表缓存写入 `output/financial_backtest/`，不提交 Git。

默认执行方式是 live fetch 工具：当本地缓存不存在或不完整时，会从东方财富数据源拉取缺失报告期。`--require-cache` 是离线复现模式：缓存缺失或不完整时直接失败，不请求线上数据。

## 回测记录字段

每次共享给组员的回测记录至少包含：

- 日期；
- 财务 Agent 版本；
- 回测执行人；
- 回测样本池；
- 回测周期；
- 回测结果报告。

当前默认执行人为“简简简水粽”。财务 Agent 版本来自 `agents.financial.FINANCIAL_AGENT_VERSION`。

当前历史数据来自执行日可见的东方财富结构化报表，不是公告日冻结的
历史快照。报告会显式披露这一限制；在历史快照层建立前，本结果应视为
基线回测，不能完全排除财务重述造成的未来数据泄漏。当前仓库只提交
样本池、执行器和版本化报告，不提交完整历史三表快照；如需严格复现某次
回测，应使用同一份本地缓存运行 `--require-cache`，或后续单独建设固定
历史输入快照。

Markdown 报告遵循以下展示规则：

- 除系统名、文件格式、股票代码和交易所缩写外，正文使用中文；
- 展示回测口径、样本池、覆盖率、准确率、置信度分档、混淆矩阵和分组结果；
- 误判分析只按同类问题汇总数量、占比、共性原因和建议方向，不列逐样本明细；
- 逐样本证据仅保存在本地 JSON 审计文件中。

## 主指标

主指标：置信度大于 0.7 的财务 Signal 对下一季度归母净利润同比方向的判断准确率。

最小可用版本目标：不低于 70%。

当前记录仍是 draft 阶段基线，不表示财务 Agent 已达到最小可用版本目标。

## 覆盖率护栏

高置信覆盖率＝高置信 Signal 数量÷可评估样本数。

该指标用于防止只输出少量高置信样本造成准确率虚高。最小可用版本阶段先披露，不设硬阈值。

## 分档校准

按置信度分档统计命中率：

| 档位 | 样本 |
|---|---|
| 0.5-0.6 | 低置信但可记录 |
| 0.6-0.7 | 中置信 |
| >0.7 | 高置信，进入主指标 |

高档命中率应显著高于低档，否则说明置信度规则需要重校准。

## 样本要求

- 第一版固定使用 `sample_pool_v1.csv` 中的 51 家 A 股公司。
- 覆盖 26 个 AI 硬件细分，每个细分 1 至 2 家。
- 包含存储芯片/模组和机器人核心部件。
- 每家公司使用 2024Q1 至 2025Q4 连续 8 个信号季度。
- 保留置信度不高于 0.7 的样本日志，便于复盘但不计入主指标。
- 金融类主体不纳入本框架回测。

样本选择、生命周期配额、标签定义和防偏差规则见：

`docs/superpowers/specs/2026-06-24-financial-backtest-ai-hardware-pool-design.md`
