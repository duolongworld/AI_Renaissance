---
name: arbitration-methodology
description: 开发2组仲裁方法论Skill。基于桥水经济机器模型的场景化专家权重体系，支持三种模式：(1)场景设计与权重配置迭代；(2)7专家Signal仲裁执行（含场景自动选择、评分制匹配、共识/分歧标注、贡献追踪）；(3)权重回测校准。当用户讨论仲裁权重、场景选择逻辑、match_signals规则、仓位公式设计、权重校准或标准化推理链时调用。
owner_group: 开发2组（Orchestrator）
domain: orchestration
status: active
agent_created: true
---

# 仲裁方法论 Skill

## 1. 适用范围

### 适用任务

- 设计或迭代三个市场场景（牛市/熊市/震荡市）的专家权重配置
- 对 7 个专家组的 Signal 执行场景选择与加权仲裁
- 用历史信号数据校准权重数值（理论锚定 + 实证微调）
- 生成包含共识/分歧标注和贡献追踪的标准化推理链
- 维护场景识别规则（match_signals）和仓位公式

### 边界说明

- 本 Skill 负责场景规则定义和权重配置，不分析原始市场数据（CPI、K线、VIX 等）
- 权重数值为"研究驱动的理论值"，标注为占位初稿，后续需回测校准
- 不替代风控层——仓位上限仅为场景建议，最终决策权在用户
- 场景选择基于 7 个专家组的 Signal（方向 + 置信度），不读取原始行情
- 方法论理论依据详见 `references/methodology.md`

## 2. 模式判定

| 触发条件 | 模式 | 说明 |
|:---|:---|:---|
| 用户讨论权重设计、场景规则、仓位公式 | **模式A：场景设计与权重配置** | 迭代场景参数 |
| 用户要求执行仲裁、分析信号、生成推理链 | **模式B：信号仲裁执行** | 运行仲裁引擎 |
| 用户提供历史信号数据、要求校准权重 | **模式C：权重校准** | 回测校准 |

## 3. 模式A：场景设计与权重配置

当用户需要新增场景、调整权重或修改仓位公式时执行。

### 3.1 加载当前配置

读取以下文件了解现状：
- `agents/orchestrator/scenarios/bull_market.py`
- `agents/orchestrator/scenarios/bear_market.py`
- `agents/orchestrator/scenarios/range_market.py`
- `references/weights.md`（权重设计速查表）

### 3.2 变更检查清单

每次修改权重或场景规则时，逐项确认：

- [ ] 权重方向（升/降/平）是否与桥水框架对该场景的定义一致
- [ ] 每个权重数值是否有可追溯的研究理由（标注于 `_BASE_WEIGHTS` 的 reason 字段）
- [ ] 仓位系数和上限是否符合该场景的风险特征
- [ ] match_signals 条件是否正确反映该场景的信号特征
- [ ] 场景风险提示是否覆盖该场景的典型风险
- [ ] `scenario_profile.py` 基类接口未被破坏
- [ ] `scenario_selector.py` 选择逻辑无需修改（新场景自动注册）

### 3.3 权重设计规则

权重方向由理论框架决定（详见 `references/methodology.md`）：

```
牛市（增长↑ + 通胀↓ + 风险压缩）:
  提权: 技术面、资金流、产业分析
  不变: 宏观面
  降权: 财务面、舆情组、风险面

熊市（风险溢价扩张）:
  提权: 风险面、财务面、产业分析、宏观面
  降权: 资金流、舆情组、技术面

震荡市（三维度均衡）:
  提权: 产业分析、风险面、资金流
  不变: 宏观面
  降权: 财务面、舆情组、技术面
```

具体数值见 `references/weights.md`。

### 3.4 新增场景模板

新增场景需继承 `ScenarioProfile` 并实现 6 个方法：

```python
class NewScenario(ScenarioProfile):
    @property
    def name(self) -> str: ...
    @property
    def display_name(self) -> str: ...
    @property
    def description(self) -> str: ...
    
    _BASE_WEIGHTS: Dict[str, Tuple[float, str]] = {...}
    
    def get_weight(self, expert_type, market_data=None) -> Tuple[float, str]: ...
    def match_signals(self, signals) -> Tuple[float, str, Dict]: ...
    def get_position_ratio(self, confidence, direction) -> Tuple[float, str]: ...
    def get_scenario_risks(self) -> List[str]: ...
    def get_confidence_threshold(self) -> Optional[float]: ...
```

新增后注册到 `scenarios/__init__.py` 的 `_SCENARIOS` 列表。

## 4. 模式B：信号仲裁执行

当用户要求对 7 个专家 Signal 执行仲裁时，按以下步骤执行。

### 4.1 收集专家 Signal

调用 7 个专家 Agent 获取 Signal，每个 Signal 包含：
- `direction`: bullish/bearish/neutral
- `confidence`: 0.0-1.0
- `signal_type`: technical/fundflow/macro/financial/industry/news/risk

### 4.2 场景自动选择

调用 `agents/orchestrator/scenario_selector.py` 的 `ScenarioSelector.select(signals)`：

```python
from agents.orchestrator.scenario_selector import ScenarioSelector
selector = ScenarioSelector()
selection = selector.select(signals)
```

选择逻辑：三个场景逐一调用 `match_signals()` 计算 0-1 匹配分，按分数排名，最高分 ≥ 0.5 的选中。

匹配置信度计算：

| 条件 | 公式 |
|:---|:---|
| 唯一高质量匹配（score≥0.6，与第二名差距≥0.15） | `confidence = score × 0.8` |
| 弱匹配（0.5 ≤ score < 0.6） | `confidence = score × 0.6` |
| 多场景竞争（两名分数差 < 0.15） | `confidence = score × 0.6` |
| 无匹配（score < 0.5） | 降级为默认等权 |

### 4.3 信号筛选与加权

使用选中场景的权重配置：

1. 按置信度阈值筛选 Signal（默认 0.6，震荡市覆盖为 0.45）
2. 每 Signal 综合权重 = `confidence × signal.weight × expert_weight`
3. 按方向汇总看多/看空加权得分
4. 判定方向：看多占比 > 60% → bullish，看空 > 60% → bearish，否则 neutral

### 4.4 生成标准化推理链

调用 `agents/orchestrator/reasoning_chain.py` 构建：

```python
from agents.orchestrator.reasoning_chain import build_standardized_chain
chain = build_standardized_chain(signals, scenario, direction, confidence,
                                  position_ratio, position_formula, risks,
                                  weight_reasons, execution_trace,
                                  bullish_score, bearish_score)
```

输出包含共识分析、贡献追踪、风险分类的结构化链。

### 4.5 仓位计算

使用选中场景的仓位公式：`position = min(confidence × COEFFICIENT, CAP)`

## 5. 模式C：权重校准

当用户提供历史信号数据（Signal 预测 + 后续实际方向）时执行。

### 5.1 准备历史数据

每条记录包含：`expert_type`, `scenario`, `predicted_direction`, `predicted_confidence`, `actual_direction`, `timeliness_days`

### 5.2 执行校准

```python
from agents.orchestrator.calibration import CalibrationEngine
engine = CalibrationEngine(alpha=0.3)  # 70% 理论 + 30% 数据
engine.load_anchor_weights()
engine.load_records(records)
report = engine.run_full_calibration()
print(engine.format_report(report))
```

### 5.3 审查与更新

校准引擎不自动覆盖场景文件。审查报告后：

1. 检查方向冲突标记（理论方向与实证方向不一致的）
2. 检查区间违规（融合值超出 ±30% 区间的）
3. 检查样本外验证（训练 vs 验证得分差距 > 0.15 的）
4. 手动将确认后的权重更新到对应场景文件

## 6. 核心规则速查

### 6.1 match_signals 评分规则

| 场景 | 条件数 | 聚合方式 | 阈值 |
|:---|:---:|:---|:---:|
| 牛市 | 3（宏观/风控/信号偏多） | `(c1+c2+c3)/3` | ≥ 0.5 |
| 熊市 | 3（宏观/风控/信号偏空） | `(c1+c2+c3)/3` | ≥ 0.5 |
| 震荡市 | 3（中性/均衡/冲突） | 取 top-2 平均 | ≥ 2 条件 > 0.5 |

每条件评分逻辑：
- 方向匹配 + conf ≥ 0.5 → score = conf
- 方向匹配 + conf < 0.5 → score = conf × 0.6
- 不匹配或无信号 → 0
- 风控缺失 → 0.3（部分分）

### 6.2 三场景权重速查

| 专家 | 牛市 | 熊市 | 震荡市 |
|:---|:---:|:---:|:---:|
| 技术面 | 1.3 ↑ | 0.5 ↓↓ | 0.5 ↓↓ |
| 资金流 | 1.2 ↑ | 0.9 ↓ | 1.2 ↑ |
| 产业分析 | 1.05 ↑ | 1.10 ↑ | 1.20 ↑↑ |
| 宏观面 | 1.0 → | 1.1 ↑ | 1.0 → |
| 财务面 | 0.7 ↓ | 1.2 ↑ | 0.9 ↓ |
| 舆情组 | 0.7 ↓ | 0.65 ↓ | 0.75 ↓ |
| 风险面 | 0.5 ↓ | 1.6 ↑↑ | 1.2 ↑ |

权重理由详见 `references/weights.md`。

### 6.3 仓位公式速查

| 场景 | 系数 | 上限 | 公式 |
|:---|:---:|:---:|:---|
| 牛市 | 0.60 | 0.40 | `min(0.95×0.60=0.57, 0.40)` |
| 熊市 | 0.25 | 0.15 | `min(0.95×0.25=0.24, 0.15)` |
| 震荡市 | 0.35 | 0.20 | `min(0.44×0.35=0.15, 0.20)` |

### 6.4 风险分类规则

| 类型 | 标记 | 行为 |
|:---|:---|:---|
| 阻塞性 | 🔒 | 强制 hold（信号不足、Agent 大规模失败） |
| 信息性 | 🔴 | 供参考，不阻塞交易 |
| 提示性 | ⚠️ | 供参考，不阻塞交易 |
| 场景风险 | 无标记 | 场景固有风险（如牛市追高风险） |

## 7. 标准输出

### 7.1 仲裁结果 JSON

```json
{
  "decision": "buy",
  "direction": "bullish",
  "confidence": 0.95,
  "position_ratio": 0.40,
  "signals_summary": {"total": 7, "bullish": 6, "bearish": 0, "neutral": 1},
  "risks": ["🔴 风控信号: ...", "牛市追高风险"],
  "standardized_chain": {
    "scenario_info": {"name": "bull_market", "display_name": "牛市场景"},
    "consensus": {
      "consensus_direction": "bullish",
      "consensus_ratio": 0.86,
      "divergence_type": "none"
    },
    "contributions": [
      {"signal_type": "technical", "contribution_ratio": 0.24, "is_top_contributor": true}
    ],
    "direction_analysis": {"bullish_score": 4.27, "bearish_score": 0.0},
    "final_decision": {"action": "buy", "direction": "bullish", "confidence": 0.95}
  }
}
```

### 7.2 校准报告结构

```json
{
  "meta": {"generated_at": "...", "alpha": 0.3, "total_records": 1260},
  "adjustments": {
    "bull_market": {
      "technical": {"anchor_weight": 1.3, "blended_weight": 1.32, "adjustment": 0.02}
    }
  },
  "constraints": {"direction_violations": [], "band_violations": [], "passed": true}
}
```

## 8. 质量检查

输出前逐项确认：

- [ ] 场景选择已完成——选中场景的非默认等权
- [ ] 权重已从场景对象加载（非硬编码）
- [ ] 每个权重附带可追溯理由
- [ ] 共识分析正确标注——共识方向、共识占比、分歧类型
- [ ] 贡献追踪完整——每专家一行，含贡献占比
- [ ] 方向判定规则明确——看多/看空占比与阈值逻辑
- [ ] 仓位计算触达上限时已标注（"触及上限 X"）
- [ ] 风险已按阻塞性/信息性/场景分类
- [ ] `standardized_chain` 可 JSON 序列化
- [ ] `reasoning_chain`（文本链）与 `standardized_chain`（结构化链）数据一致

## 文件索引

| 文件 | 用途 |
|:---|:---|
| `agents/orchestrator/scenario_profile.py` | 场景基类（6 问接口 + 评分辅助方法） |
| `agents/orchestrator/scenario_selector.py` | 场景选择器（v2 评分制） |
| `agents/orchestrator/arbitration.py` | 仲裁引擎（11 步流水线） |
| `agents/orchestrator/agent.py` | Orchestrator 入口 |
| `agents/orchestrator/calibration.py` | 权重校准引擎 |
| `agents/orchestrator/reasoning_chain.py` | 标准化推理链 |
| `scenarios/bull_market.py` | 牛市场景 |
| `scenarios/bear_market.py` | 熊市场景 |
| `scenarios/range_market.py` | 震荡市场景 |
| `references/methodology.md` | 方法论理论依据（桥水框架 + 研究来源） |
| `references/weights.md` | 权重设计速查表（三场景权重 + 仓位公式） |
| `tests/test_e2e_orchestrator.py` | E2E 验证 |
| `tests/test_calibration.py` | 校准验证 |

