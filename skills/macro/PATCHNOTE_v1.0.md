# Macro Skill v1.0 — Patch Notes

> **版本**: v1.0 | **日期**: 2026-05-21 | **分支**: `feat/macro-agent`  
> **状态**: 可运行，使用 mock 数据（实时数据未接入）

---

## 1. 流水线完成度

| 层 | 模块 | 状态 | 说明 |
|---|---|---|---|
| Layer 0 | 双经济体追踪 | ✅ 可运行 | 静态 mock 数据，支持 LLM 增强 |
| Layer 1 | CAI/FCI 计算 | ✅ 可运行 | 纯数值计算，mock 数据 |
| Layer 2 | 周期定位 | ✅ 可运行 | 支持政策维度调节、债务周期 |
| Layer 2.5 | 枢纽变量 | ✅ 可运行 | 汇率+商品比值+宏观三角，→ Layer 4 已连通 |
| Layer 3 | 市场定价提取 | ✅ 可运行 | 5类指标中美对照 |
| Layer 4 | 预期差信号引擎 | ✅ 可运行 | 类型A/B/C信号，含 Layer 2.5 接入 |
| Layer 4.5 | 反身性修正 | ✅ 可运行 | 压力/生命周期/范式三重修正 |
| Layer 5 | 资产配置 | ✅ 可运行 | Beta(风险平价+周期象限调整)+Alpha(预期差偏离) |

**数据状态**: 数据来源为 `build_complete_mock_data()`（2024-06-28 历史数据），实时数据待接入。波动率使用静态 fallback，历史信号持久化未实现。

**运行验证**（2026-05-21）:

```
direction: bearish | confidence: 80%
信号: A股 低配4% | 中债 配置57% | 南华工业 配置9% | 黄金 配置18% | 美股 配置12%
```

---

## 2. 待完成事项

### P0 — 数据层接入

> 详细数据清单见 [`_workspace/spec/input_data_spec.md`](_workspace/spec/input_data_spec.md)。

当前 mock 数据仅覆盖部分维度，完整流水线需接入以下数据：

| 优先级 | 数据项 | 影响的层 |
|---|---|---|
| P0 | Layer 0/1 原始指标（PMI、社融、CPI、10Y收益率等） | Layer 0, 1, 2, 3 |
| P0 | CAI/FCI z-score 历史滚动窗口计算 | Layer 1, 2 |
| P0 | 各资产 3 年滚动年化波动率 | Layer 5 Beta 层 |
| P0 | CESI（花旗经济意外指数） | Layer 4 类型A信号 |
| P1 | CFTC 非商业持仓 + ETF 资金流 | Layer 4.5 仓位集中度 |
| P1 | 历史信号持久化存储 | Layer 4 信号衰减与复核 |
| P1 | 政策文本（新华社/国常会/央行货政报告） | Layer 2 政策维度打分 |
| P2 | 期货远月/近月价差（铜、原油） | Layer 3 商品库存周期 |

### P1 — 框架待确认问题

> 完整问题清单及状态见 [`_workspace/spec/框架待解决问题清单.md`](_workspace/spec/框架待解决问题清单.md)。

以下问题影响代码中的量化逻辑，需专家4组补充量化标准：

| 问题编号 | 描述 | 影响位置 | 优先级 |
|---|---|---|---|
| **问题5** | 长期债务周期"末端/下行特征"的量化判定标准 | `layer2` `debt_cycle` 判定 | 高 |
| **问题7** | 信号衰减公式（指数衰减 vs 线性衰减） | `layer4` `apply_signal_decay` | 高 |
| **问题15** | USD/CNH 方向得分在 ±0.5σ~±1.0σ 之间的处理规则 | `layer2_5` `calculate_cnh_direction` | 高 |
| 问题19 | 反身性压力计子指标数据可得性 | `layer4_5` `analyze_reflexivity` | 高 |
| 问题20 | 逻辑生命周期各阶段量化判定标准 | `layer4_5` `analyze_reflexivity` | 高 |
| 问题1 | 传导强度量化方法 | `layer0` `analyze_bilateral_tracking` | 中 |
| 问题2 | 交互层次判定逻辑量化阈值 | `layer0` | 中 |
| 问题8 | 信号相关性降权算法 | `layer4` | 中 |
| 问题18 | 多异常场景同时触发时的优先级规则 | `agent.py` 异常处理 | 中 |

### P2 — 框架中未实现的模块

| 模块 | 描述 | 对应框架章节 |
|---|---|---|
| Layer 4 类型A信号 | CESI 高频意外指数 | 框架第758-761行 |
| Layer 4.5 仓位集中度 | CFTC 非商业净头寸 z-score | 框架第1568-1578行 |
| Layer 4.5 范式稳定性 | 跨资产相关性结构断裂监测 | 框架第1580-1595行 |
| Layer 5 行业景气映射 | 框架第1004-1009行行业轮动表 | `calculate_industry_allocation` |
| Layer 2.5 传导通道警报 | 6条关键传导通道 | 框架第1073-1088行 |

---

## 3. LLM 接口可增强的方向

`agent.py` 中已预留 `_call_llm_for_layer` 接口，`self._llm_client` 和 `self.get_skill()` 均可正常调用。以下几个场景可立即接入：

| 场景 | 当前状态 | LLM 可替代的逻辑 |
|---|---|---|
| **Layer 0 智能解读** | 静态维度得分，硬编码阈值 | 综合 PMI + 政策 + 流动性给出动态交互判断 |
| **Layer 2 象限模糊区** | CAI 接近 0 时纯数值无法判定 | 结合新闻事件和政策信号做综合判定 |
| **Layer 4 信号复核** | 仅数值判断"连续2周反向" | 解读具体宏观事件是否真的反转了信号逻辑 |
| **推理摘要生成** | 当前仅输出配置比例数字串 | 生成完整逻辑推导叙述（衰退→债券权重↑的原因） |

---

## 4. 合作者需要提供的支持

| 角色 | 职责 | 对接文件 |
|---|---|---|
| **数据工程师** | 接入 `data_sources/` 的真实宏观数据 | [`_workspace/spec/input_data_spec.md`](_workspace/spec/input_data_spec.md) |
| **Quant** | 验证/重写 `calculate_beta_weights` 波动率计算 | `layer5_asset_allocation/scripts/analyzer.py` |
| **领域专家** | 补充框架中标记"待确认"的量化判定标准 | [`_workspace/spec/框架待解决问题清单.md`](_workspace/spec/框架待解决问题清单.md) |
| **后端/数据** | 搭建历史信号持久化存储 | `layer4_expected_diff/scripts/analyzer.py` |

---

## 5. 修改的文件清单

```
agents/macro/agent.py
    _run_layer4:         新增 layer25_result 参数，移到 Layer 2.5 之后执行
    _run_layer5:        新增 volatility_data fallback 构造并传入
    _summarize_reasoning_chain:  signal_parts[:3] → [:8]，显示全部资产

skills/macro/layer4_expected_diff/scripts/analyzer.py
    analyze_expected_diff:      新增 layer25_output 参数
    calculate_type_c_signals:   新增 layer25_output 参数
                               + 全球宏观三角信号
                               + USD/CNH 汇率信号
                               + 铜金比极端低估信号

skills/macro/layer5_asset_allocation/scripts/analyzer.py
    + ASSET_NAME_MAPPING, _normalize_asset_name()
    calculate_beta_weights:     新增 cycle_position, debt_cycle 参数
                               + 框架表7.3象限调整
                               + 长期债务周期战略调节
    calculate_alpha_deviation:  强度阈值 50→35
                               + related_assets 中文名规范化映射
    _determine_confidence:      改为基于偏离总量计算
    _generate_signals:          移除阈值筛选，始终输出全部资产
    analyze_asset_allocation:   从 layer2_output 提取象限和债务周期
    ```

---

## 6. TODO — 测试与回测框架

> 确保后续每次修改不影响框架核心功能，需搭建完整的单测与回测基础设施。

### 6.1 单元测试（pytest）

需覆盖的核心函数（`skills/macro/` 各 `analyzer.py`）：

| 文件 | 测试目标 | 验收标准 |
|---|---|---|
| `layer2/scripts/analyzer.py` | `analyze_cycle_positioning` | 给定 CAI/FCI → 正确返回 quadrant + debt_cycle |
| `layer4/scripts/analyzer.py` | `analyze_expected_diff` + `calculate_type_c_signals` | mock layer25_output → Type C 信号非空 |
| `layer5/scripts/analyzer.py` | `calculate_beta_weights` | 衰退象限下债券权重 > 股票权重 |
| `layer5/scripts/analyzer.py` | `calculate_alpha_deviation` | 存在高强度信号 → net_deviation 非零 |
| `layer5/scripts/analyzer.py` | `_determine_confidence` | 偏离总量 > 0.20 → confidence >= 0.85 |

### 6.2 数据 Fixture

- 构造标准化 mock 数据 fixture，覆盖：复苏、过热、滞胀、衰退四个象限 + 债务周期上行/末端各两种场景
- 确保每次单测使用同一 fixture，可复现历史运行结果
- 参考当前 `build_complete_mock_data()`，将其迁移至 `tests/fixtures/` 目录

### 6.3 回归测试（回测框架）

| 目标 | 说明 |
|---|---|
| **分层输出稳定性** | 修改任意一层后，其他层的 `output["meta"]["confidence"]` 变化不超过 ±0.05 |
| **最终资产权重合理性** | 各资产权重和 = 100% ± 0.01，无负权重，各资产权重 ∈ [0%, 100%] |
| **象限切换一致性** | 当 CAI/FCI 从衰退象限切换至复苏象限，债券权重应下降，股票权重应上升 |
| **Layer 2.5 接入验证** | `layer25_result` 传入 Layer 4 后，Type C 信号条数 > 0 |

### 6.4 实施计划

1. 在 `tests/` 下建立 `test_macro_layers.py`，按层拆分测试用例
2. 将 `build_complete_mock_data()` 抽取为 `tests/fixtures/mock_data.py`，支持参数化象限
3. 配置 CI：每次 PR 触发 pytest，确保所有单测通过
4. 后续接入真实数据后，增加 `tests/backtest/` 目录，用历史数据验证框架预测能力
