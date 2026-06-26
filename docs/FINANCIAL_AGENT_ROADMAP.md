# 财务 Agent 迭代路线

## 1. 文档定位

本文记录财务 Agent 的阶段性迭代目标、优先级、依赖关系、执行方案和验收标准。

适用范围：

- `agents/financial/`
- `skills/financial/financial_report_analysis/`
- 财务 Agent 使用的 `data_sources/` 与 `skills/data/`
- `tests/financial/`

本文不是当前实现状态清单。实际能力以代码和测试为准，导航信息见 `docs/AGENT_MATRIX.md`。

## 2. 当前基线

截至 2026-06-24，财务 Agent 已具备以下能力：

- 继承 `BaseAgent`，加载 `financial` 领域 Skill，并输出标准 `Signal`。
- 通过可注入的数据源获取当前、上一和上上报告期的三张财务报表。
- 执行财报质量七步验证链。
- 支持累计利润表和现金流量表的单季拆分。
- 输出证据、红旗、置信度拆解、附加检查和 `data_gaps`。
- 三张表缺失或遇到不适用金融行业时，降为中性并触发人工复核。

当前主要限制：

- `financial-report-analysis` 仍为 `draft`。
- 回测目录只定义指标口径，没有真实回测执行器和样本集。
- 现有测试只覆盖少量局部行为，不能证明方向准确率和置信度校准有效。
- 订单、产能、产品线、客户供应商和关联方等关键字段仍主要表现为 `data_gaps`。
- 行业差异只存在于说明文档，没有形成可执行、可测试的配置。
- `analyze_report.py` 同时承担归一化、指标计算、规则、置信度和 Signal 构建，维护边界偏重。

## 3. 迭代原则

1. **先验证，再加规则。** 在真实回测建立前，不继续扩张经验阈值和财务子 Skill。
2. **先补证据，再调置信度。** 数据缺失导致的判断问题，应优先在数据层解决。
3. **保持架构边界。** 数据获取和解析放在 `data_sources/`；财务判断放在分析 Skill；Agent 只负责加载、调用、编排和封装。
4. **结果可复现。** 回测必须固定样本、数据截止日、标签口径和版本信息，禁止未来数据泄漏。
5. **渐进式行业化。** 先以通用框架建立基线，再根据回测结果引入行业配置。
6. **重构不能改变结果。** 模块拆分必须以固定样本快照和回归测试保护行为。

## 4. 优先级总览

| 优先级 | 阶段 | 核心目标 | 主要产物 |
|---|---|---|---|
| P0 | 真实回测与基线 | 证明方向判断和置信度是否有效 | 样本集、回测执行器、基线报告 |
| P0 | 关键数据闭环 | 补齐需求真实性和扩张质量证据 | 聚合数据源、公告字段提取、数据契约 |
| P1 | 行业配置化 | 将行业差异变成可执行规则 | `industry_profiles`、行业样本池 |
| P1 | 回归测试体系 | 防止规则与数据迭代引入回归 | `tests/financial/` 测试集 |
| P2 | 运行时代码拆分 | 降低单文件复杂度和修改风险 | 独立运行时模块、薄 CLI |
| P2 | 解释层增强 | 支持 Orchestrator 展示和人工复核 | `meta.explanation` |

依赖顺序：

```text
真实回测
  -> 根据误判和 data_gaps 确定数据优先级
  -> 补齐关键数据
  -> 行业配置化并重新回测
  -> 固化回归测试
  -> 模块拆分
  -> 解释层增强
```

## 5. P0：真实回测与基线

### 目标

验证以下核心指标：

- `accuracy@confidence>0.7`
- `coverage@confidence>0.7`
- 各置信度分档的实际命中率
- bullish、bearish、neutral 的混淆矩阵
- 按行业、报告类型和数据完整度分组的表现

MVP 目标沿用财务 Skill 定义：`accuracy@confidence>0.7 >= 70%`。准确率必须同时披露 coverage，避免通过少量高置信样本制造虚高结果。

### 执行方案

样本池第一版设计见 `docs/superpowers/specs/2026-06-24-financial-backtest-ai-hardware-pool-design.md`，机器可读名单见 `skills/financial/financial_report_analysis/backtest/sample_pool_v1.csv`。

1. 在 `skills/financial/financial_report_analysis/backtest/` 增加：
   - 样本清单和格式说明；
   - 历史输入快照生成器；
   - 下一季度归母净利润同比方向标签生成器；
   - 回测执行器；
   - JSON 和 Markdown 指标报告器。
2. 每条样本至少记录：
   - 股票代码、行业、报告期、公告日期；
   - 数据截止时间和数据源版本；
   - Agent 输出的 `direction`、`confidence`、`data_gaps`；
   - 下一季度归母净利润同比实际方向；
   - 是否可评估及排除原因。
3. 第一轮使用 3 个以上行业、每个行业 4 个以上季度，打通约 40 至 60 个样本。
4. 第二轮扩展到 200 个以上样本，用于置信度校准和行业差异判断。
5. 复用 `agents/orchestrator/calibration.py` 的通用数据结构或指标实现时，保持财务专项标签口径独立。

### 验收标准

- 同一版本、同一样本可重复生成相同报告。
- 样本输入只使用信号产生时已经公开的数据。
- 报告包含 accuracy、coverage、混淆矩阵、置信度分桶和分组表现。
- 高置信准确率未达到目标时，Skill 不升级为稳定状态。
- 每个误判可以追溯到输入快照、规则结果和数据缺口。

## 6. P0：关键数据闭环

### 目标

优先解决直接影响“需求真实性”和“扩张质量”的数据缺口。

建议字段优先级：

1. 已签订单、在手订单。
2. 产能扩张计划、项目投产进度、产能利用率。
3. 产品线收入、同比/环比和毛利率。
4. 前五大客户、前五大供应商集中度。
5. 关联方客户和供应商交易占比。
6. 折旧摊销及资本开支覆盖指标。
7. 同行标杆池和指标分位数。

实际开发顺序应由首轮回测中的高频误判和 `data_gaps` 统计决定。

### 执行方案

- 保留 `EastMoneyDataSource` 作为结构化三表来源。
- 使用 `CninfoDataSource` 获取年报、季报和公告原文。
- 在 `data_sources/` 增加公告字段提取和财务数据聚合实现。
- 在 `skills/data/` 记录调用参数、稳定输出字段、来源、单位、报告期和失败格式。
- 通过 `config` 将聚合数据源注入 `FinancialAgent`。
- 原文提取失败时保留三表分析能力，并明确返回缺失原因。

### 验收标准

- 新字段具备来源、报告期、单位和提取状态。
- 数据源失败返回稳定字典，不把提供方细节泄漏到 Agent。
- 缺失字段继续进入 `meta.data_gaps`，不得用行业常识补数。
- 新字段对方向或置信度的影响必须通过回测验证。

## 7. P1：行业配置化

### 目标

把 `references/industry_adaptations.md` 中的行业差异转为可执行、可测试的配置。

第一批 profile：

- 制造与硬科技
- 消费与零售
- 软件、互联网与平台
- 重资产与周期
- 医药
- 地产与建筑

每个 profile 至少定义：

- 必需字段；
- 通用阈值的覆盖值；
- 行业特殊红旗；
- 替代指标；
- 不适用条件；
- 回测样本池。

### 执行方案

- 新建独立的 `industry_profiles` 配置模块，规则实现不得散落在 Agent 中。
- 行业识别失败时使用通用 profile，并在 `meta` 中标记。
- 银行、保险和券商继续保持不适用，不在本阶段强行兼容。
- 每引入一个 profile，先建立对应样本集，再调整阈值。

### 验收标准

- 每个 profile 有独立测试和回测结果。
- 行业阈值来源和调整理由可追溯。
- 同一输入切换 profile 时，差异仅来自明确配置。
- 通用 profile 仍可处理未知行业并安全降级。

## 8. P1：回归测试体系

### 目标

将财务领域正式测试统一放到 `tests/financial/`，覆盖 Agent、Skill runtime 和模型规则。

最低测试清单：

- `FinancialAgent.analyze()` 返回合法 `Signal`。
- 数据源可以通过 `config` 注入。
- 三张表任一缺失时强制中性且 `confidence <= 0.4`。
- 银行、保险和券商触发不适用降级。
- 高研发商业化阶段不会因单期亏损直接触发错误高风险。
- bullish、bearish、neutral 的方向边界。
- 累计数拆分单季和环比计算。
- 同比与环比冲突时置信度降档。
- `data_gaps` 的生成和消除。
- 行业 profile 的阈值覆盖。
- 数据源超时、空数据和部分失败降级。
- Signal 顶层契约和关键 `meta` 字段。

### 验收标准

- 财务领域正式测试全部位于 `tests/financial/`。
- 每个已知误判在修复前先形成回归样本或测试。
- CI 可以单独执行财务测试和回测烟雾测试。

## 9. P2：运行时代码拆分

### 目标

将当前单文件运行时拆成职责明确的模块，同时保持输出兼容。

建议结构：

```text
skills/financial/financial_report_analysis/
├── runtime/
│   ├── normalize.py
│   ├── metrics.py
│   ├── stages.py
│   ├── rules.py
│   ├── additional_checks.py
│   ├── confidence.py
│   └── signal_builder.py
└── scripts/
    └── analyze_report.py
```

边界：

- `normalize.py`：把数据源稳定字段转为财务分析字段。
- `metrics.py`：纯指标计算。
- `stages.py`：业务阶段识别。
- `rules.py`：七步链和红旗判断。
- `additional_checks.py`：订单、产能、产品线和客户供应商检查。
- `confidence.py`：证据评分和校准后的置信度计算。
- `signal_builder.py`：组装标准 `Signal` 字典。
- `analyze_report.py`：薄 CLI 和兼容入口。

### 验收标准

- 固定回测样本在重构前后的输出一致。
- `FinancialAgent` 的调用接口不变。
- 模块间通过稳定字典或明确数据模型交互。
- 不把真实数据抓取逻辑移入 Skill runtime。

## 10. P2：解释层增强

### 目标

在不改变顶层 `Signal` 契约的前提下，为 Orchestrator 和人工复核提供稳定解释。

建议增加：

```json
{
  "meta": {
    "explanation": {
      "conclusion": "",
      "supporting_evidence": [],
      "counter_evidence": [],
      "data_gaps": [],
      "human_review_points": []
    }
  }
}
```

### 验收标准

- 解释内容完全由结构化分析结果生成。
- 每条支持证据和反证可以追溯到 `meta.evidence`。
- 不重复制造第二套方向或置信度字段。
- Orchestrator 可以直接展示，而不需要重新解释财务规则。

## 11. 暂缓事项

在真实回测建立前，暂缓：

- 将营运资金、盈利能力、合同负债等继续拆成多个独立运行时 Skill。
- 继续增加未经验证的经验阈值。
- 自动调整 Orchestrator 的财务专家权重。
- 让同行分位数直接参与方向评分。
- 为银行、保险和券商强行复用当前七步链。

## 12. 里程碑

### M1：回测可运行

- 40 至 60 个历史样本。
- 可重复生成第一份基线报告。
- 输出误判分类和 `data_gaps` 排名。

### M2：关键证据闭环

- 至少补齐两类高频关键数据。
- 对比补数据前后的准确率、coverage 和置信度校准。

### M3：行业化

- 至少三个行业 profile 投入运行。
- 每个 profile 有独立样本和回归测试。

### M4：稳定化

- 财务测试迁入 `tests/financial/`。
- runtime 完成模块拆分。
- 固定样本回归无差异。
- 达到约定回测门槛后，再评估将 Skill 状态从 `draft` 升级。

## 13. 每轮迭代交付要求

每个迭代 PR 应包含：

1. 本轮解决的误判类型或数据缺口。
2. 修改涉及的 Agent、Skill、数据源和测试边界。
3. 新增或更新的样本与测试。
4. 回测前后对比。
5. 尚未解决的限制。
6. 对架构文档和 `docs/AGENT_MATRIX.md` 的同步更新。
