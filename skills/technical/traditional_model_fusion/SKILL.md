---
name: traditional-model-fusion
description: 对个股、指数、ETF 或 OHLCV CSV 运行专家二组“四模型传统技术指标融合”分析。使用本工程的 fusion_traditional_models Python 程序只生成可复核 JSON 结果，再由大模型读取 JSON 并按中文模板生成融合结果解读报告。适用于用户要求测试股票、输出融合信号、解释四模型结果、生成技术面融合结果解读报告的场景。
---

# 传统模型融合 Skill

## 一、定位

本 Skill 是“工程代码 + 大模型解读”的组合流程：

- Python 工程负责确定性计算：抓取或读取行情、运行四个模型、生成融合 JSON。
- 大模型负责解释性写作：读取 JSON，理解总信号、子模型投票、风险、冲突和证据，按本 Skill 的模板写成中文评估解读报告。
- 不要让大模型凭空判断股票，也不要只按文字规则输出结论；必须先得到工程程序生成的 JSON。
- 工程不再生成固定 Python Markdown 报告；所有 `.md` 解读报告都应由大模型基于 JSON 进行评估、归纳和表达。

适用边界：

- 只分析行情数据和技术指标，不直接分析基本面、财报、新闻、估值或行业景气。
- `direction` 表示技术面方向倾向，不等于买卖指令。
- 如果数据不足、数据源异常、复权口径不明、模型冲突或风险偏高，必须提示人工复核。

## 二、输入要求

用户至少提供以下一种输入：

- 股票代码模式：股票代码、开始日期、结束日期，最好补充标的名称。
- CSV 模式：本地 OHLCV 文件路径，字段建议包含 `date, open, high, low, close, volume`；`open` 可缺，但不建议缺。

默认口径：

- 频率默认日线。
- 复权默认 `none`，即不复权。
- 如果复权口径没有确认，在解读报告中写入“不确定性”。
- 样本建议不少于 60 个交易日；趋势模型更建议 80 至 120 个交易日。

## 三、执行流程

按顺序执行：

1. 明确标的名称、代码、日期范围、数据来源、复权口径。
2. 进入包含 `fusion_traditional_models/` 的工程根目录。
3. 确认依赖已安装；如缺少依赖，运行：

```powershell
python -m pip install -r requirements.txt
```

4. 如果使用股票代码拉取行情，确认 EastMoney `ut` 已配置；如果没有，可在当前 PowerShell 会话设置：

```powershell
$env:EASTMONEY_UT="fa5fd1943c7b386f172d6893dbfba10b"
```

5. 运行 Python 程序生成 JSON。股票代码模式：

```powershell
python -m fusion_traditional_models.cli --code <股票代码> --start <YYYY-MM-DD> --end <YYYY-MM-DD> --pretty --json-output "reports\<标的名>_<股票代码>_融合测试结果.json"
```

CSV 模式：

```powershell
python -m fusion_traditional_models.cli --csv "<OHLCV文件路径.csv>" --pretty --json-output "reports\<标的名>_融合测试结果.json"
```

6. 读取生成的 JSON 文件，重点读取：

- `fused_signal`
- `model_signals`
- `validation_report`

7. 由大模型根据 JSON 生成中文评估解读报告，并写入：

```text
reports\<标的名>_<股票代码>_融合结果解读.md
```

8. 不要使用 `--markdown-output` 或固定 Python Markdown 报告；本工程 CLI 只负责输出 JSON，`.md` 解读报告由大模型按本模板写入文件。

## 四、四模型调用关系

Python 程序会把同一份 OHLCV 数据送入四个模型：

| 模型 | 工程实现 | 主要作用 |
|---|---|---|
| 量价模型 | `fusion_traditional_models.models.volume_price` | 判断量价配合、资金推动、VWAP 偏离和 CMF |
| 趋势模型 | `fusion_traditional_models.models.trend_tracking` | 判断 ADX 趋势环境、MA 与 MACD 方向 |
| 震荡模型 | `fusion_traditional_models.models.oscillator` | 判断 RSI、KDJ、BOLL、MACD、ROC 的动能和超买超卖 |
| 钝化/背离模型 | `fusion_traditional_models.models.trend_application` | 判断 KDJ/RSI 钝化、顶背离、底背离等风险提示 |

四个原始 Skill 或文档是规则来源；当前真正被调用和复现的是上述 Python 实现。

## 五、融合逻辑

默认基础权重：

| 模型 | 基础权重 |
|---|---:|
| 趋势模型 | 0.35 |
| 量价模型 | 0.30 |
| 震荡模型 | 0.25 |
| 钝化/背离模型 | 0.10 |

方向映射：

```text
bullish = +1
bearish = -1
neutral = 0
```

单模型投票：

```text
vote = effective_weight * signed(direction) * adjusted_confidence
adjusted_confidence = confidence * risk_penalty
```

风险惩罚：

- `risk_level = high`：乘以 `0.6`
- `risk_level = medium`：乘以 `0.8`
- `needs_human_review = true`：再乘以 `0.6`

最终方向：

- `total_vote >= 0.60`：`bullish`
- `total_vote <= -0.60`：`bearish`
- 其他情况：`neutral`

门控规则：

- 若趋势模型判断 `ADX < 20`，趋势模型有效权重降至不高于 `0.20`。
- 若 ADX 不可用，不能说成 `ADX < 20`，只能说“趋势环境无法确认”。
- 若震荡模型多空冲突且 `needs_human_review = true`，融合结果应转为保守或显著降低置信度。
- 任一模型高风险或需要人工复核，融合层应传播风险提示。

## 六、大模型解读原则

生成解读报告时必须遵守：

- 先读 JSON，不要只读 Markdown 固定报告。
- 不要把 `neutral` 解读为“看空”；它通常表示“没有达到做多或做空阈值”。
- 先解释 `total_vote` 是否跨过 `threshold`，再解释为什么跨过或没跨过。
- 区分“模型没有确认”和“模型方向冲突”。
- 把子模型的 `vote`、`confidence`、`risk_level`、`needs_human_review` 放在一起解释，不要只看方向。
- 如果 `risk_level = high`，必须解释高风险来自哪个模型、哪个证据或哪个工程限制。
- 如果 `needs_human_review = true`，必须说明人工复核点。
- 如果 JSON 中有 `validation_report.conflicts`，必须逐条解释冲突。
- 如果 JSON 中有 `validation_report.gates_triggered`，必须逐条解释门控影响。
- 如果某些指标不可用，必须说明“不可用”的原因和对结论的影响，不要伪造数值。

## 七、大模型评估解读报告模板

大模型根据 JSON 生成 `.md` 解读报告时，使用以下结构。可以根据实际 JSON 增删小节，但不要遗漏核心判断。

```markdown
# <标的名>（<股票代码>）传统模型融合结果解读

## 1. 一句话结论

- 融合总信号：<direction>
- 置信度：<confidence>
- 风险等级：<risk_level>
- 是否需要人工复核：<needs_human_review>
- 核心解释：<用 2-4 句话说明为什么是这个结论>

## 2. 这不是简单看多或看空

说明 `neutral`、`bullish` 或 `bearish` 的真实含义。
如果是 `neutral`，必须说明是“未跨过阈值”还是“多空冲突导致保守”。

## 3. 融合投票是怎么来的

| 模型 | 方向 | 置信度 | 风险 | 有效权重 | 投票分 | 主要说明 |
|---|---|---:|---|---:|---:|---|
| 量价模型 |  |  |  |  |  |  |
| 趋势模型 |  |  |  |  |  |  |
| 震荡模型 |  |  |  |  |  |  |
| 钝化/背离模型 |  |  |  |  |  |  |

解释 `total_vote`、`threshold` 和最终方向之间的关系。

## 4. 四个子模型分别在说什么

### 4.1 量价模型

解释方向、证据、风险、对融合结果的贡献。

### 4.2 趋势模型

解释 ADX、MA、MACD 等证据。
如果 ADX 不可用，说明趋势环境无法确认，以及这会如何影响结论。

### 4.3 震荡模型

解释 RSI、KDJ、BOLL、MACD、ROC 的共振或分化。

### 4.4 钝化/背离模型

解释是否存在钝化、顶背离、底背离，以及它主要是方向信号还是风险提示。

## 5. 风险和人工复核点

列出高风险来源、人工复核原因、数据口径不确定性、工程实现限制。

## 6. 门控与冲突

说明本次是否触发门控规则。
说明是否存在模型间方向冲突。
如果没有冲突，也要说明“没有直接多空冲突，但存在未确认或风险折扣”。

## 7. 对结果的使用建议

说明这个结果适合如何使用。
必须写明：该结果不是交易指令，建议结合更长周期、基本面、消息面和人工复核。

## 8. 后续改进建议

从数据、模型、融合规则、回测验证四个角度提出后续改进。
```

## 八、输出要求

完成一次股票分析后，至少交付两个文件：

- JSON 结果文件：`reports\<标的名>_<股票代码>_融合测试结果.json`
- 大模型评估解读报告：`reports\<标的名>_<股票代码>_融合结果解读.md`

向用户汇报时说明：

- JSON 是工程程序生成的原始结构化结果。
- 大模型解读报告是根据 JSON 生成的中文解释，不是固定 Python 模板。

## 九、质量检查

输出前检查：

- 是否实际运行了 `fusion_traditional_models.cli`。
- 是否生成 JSON 文件。
- 是否读取 JSON 后再写解读报告。
- 解读报告是否解释了 `direction`、`confidence`、`risk_level`、`needs_human_review`。
- 解读报告是否解释了 `total_vote` 和 `threshold`。
- 解读报告是否覆盖四个子模型。
- 解读报告是否说明门控、冲突、风险、人工复核点。
- 是否避免把 `neutral` 误写成看空。
- 是否避免伪造 JSON 中不存在的指标数值。
- 是否明确说明“不是交易指令”。

## 十、失败处理

- 缺少依赖：运行 `python -m pip install -r requirements.txt`。
- 无法联网拉取行情：提示用户提供 CSV，或让用户在本机 PowerShell 运行命令。
- 行情数据不足：生成保守结论，写明样本不足。
- ADX 不可用：写成“趋势环境无法确认”，不要写成“ADX 小于 20”。
- JSON 不存在：先重新运行 Python 程序，不要直接写解读报告。
- JSON 字段缺失：说明字段缺失，并在解读中标注不确定性。

## 十一、后续改进方向

- 完整工程化 SAR 和 Ichimoku 防守层。
- 将 ADX、ATR、DI 改为 Wilder 平滑口径。
- 把子模型关键证据自动聚合到 `fused_signal.meta.evidence`。
- 将固定权重升级为场景权重。
- 建立多标的回测集，验证阈值 `0.60` 和风险惩罚系数是否合理。
