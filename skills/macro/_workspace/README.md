# 专家4组工作区（宏观分析）

> 本目录是专家4组（宏观）的非正式工作区，用于存放草稿、讨论记录和中间资料。
> 
> **本目录下的文件不参与运行时 Skill 加载。**
> 
> 正式 Skill 请放在 `skills/macro/{skill_name}/SKILL.md`。

---

## 📁 目录结构

```
skills/macro/_workspace/
├── raw/                          # 原始文档
│   └── v3/                       # V3版本原始资料
│       ├── 宏观组分析框架3.0.docx  # 原始需求文档（Word格式）
│       └── framework_full.md       # 框架完整Markdown版本
│
├── spec/                         # 规范文档
│   ├── requirement.md             # ✅ 需求文档（宏观分析6层流水线）
│   ├── input_data_spec.md         # ✅ 输入数据规范（给数据组同事）
│   ├── 框架待解决问题清单.md       # ✅ 框架待解决问题清单
│   └── macro_framework.html       # ✅ 宏观框架HTML可视化版本
│
├── test/                         # 测试目录
│   └── (待补充)
│
└── README.md                     # 本文档
```

---

## 📊 当前进度

### ✅ 已完成

| 任务 | 文件 | 说明 |
|---|---|---|
| 需求文档 | `spec/requirement.md` | 宏观分析6层流水线完整需求（Layer 0-5） |
| 输入数据规范 | `spec/input_data_spec.md` | 给数据组同事的文档，定义所需原始输入数据 |
| 框架待解决问题清单 | `spec/框架待解决问题清单.md` | 记录框架中需要明确的问题点 |
| 宏观框架HTML版本 | `spec/macro_framework.html` | 可视化展示6层流水线架构 |

### ⏳ 进行中

| 任务 | 状态 | 说明 |
|---|---|---|
| 数据接口Skill定义 | 🔄 待启动 | 根据 `input_data_spec.md` 创建 `skills/data/macro_indicators/SKILL.md` |
| 数据获取实现 | 🔄 待启动 | 实现 `data_sources/macro_indicators.py` |
| 分析Skill实现 | 🔄 待启动 | 实现 `skills/macro/{skill_name}/SKILL.md` |
| 测试用例编写 | 🔄 待启动 | 补充 `test/` 目录下的测试文件 |

### ❌ 待完成

| 任务 | 优先级 | 说明 |
|---|---|---|
| 宏观Agent实现 | P0 | 实现 `agents/macro/agent.py`（继承BaseAgent） |
| Layer权重回测校准 | P1 | 需求文档中标注"权重待回测校准"的指标 |
| 信号衰减公式验证 | P1 | Layer 4衰减系数需要历史数据拟合 |
| 资产配置映射规则 | P1 | Layer 5资产映射需要明确规则 |

---

## 🎯 下一步计划

### 阶段1：数据接口定义（本周）
1. 根据 `input_data_spec.md` 创建数据接口Skill
   - `skills/data/macro_indicators/SKILL.md`
2. 实现数据获取逻辑
   - `data_sources/macro_indicators.py`

### 阶段2：分析Skill实现（下周）
1. 按Layer拆分实现分析Skill：
   - `skills/macro/layer0_data_monitoring/SKILL.md`
   - `skills/macro/layer1_state_scoring/SKILL.md`
   - `skills/macro/layer2_policy_sentiment/SKILL.md`
   - `skills/macro/layer2.5_cross_asset/SKILL.md`
   - `skills/macro/layer3_expected_difference/SKILL.md`
   - `skills/macro/layer4_signal_arbitration/SKILL.md`
   - `skills/macro/layer5_asset_allocation/SKILL.md`

### 阶段3：Agent实现与测试（下下周）
1. 实现 `agents/macro/agent.py`
2. 编写测试用例
3. 集成测试

---

## 📝 工作规则

1. **定稿内容必须迁移到正式Skill目录**
   - `_workspace/spec/` 下的文档定稿后，必须迁移到 `skills/macro/{skill_name}/SKILL.md`
   - 数据接口定义定稿后，必须迁移到 `skills/data/{data_interface}/SKILL.md`

2. **定期清理过时草稿**
   - 每月清理一次 `_workspace/` 目录
   - 已迁移到正式目录的内容可以从 `_workspace/` 删除

3. **文档更新原则**
   - 需求变更时，同步更新 `spec/requirement.md` 和相关的Skill文档
   - 数据接口变更时，同步更新 `spec/input_data_spec.md` 和数据接口Skill

---

## 📚 参考资料

- 项目架构：`docs/ARCHITECTURE.md`
- Agent实现指南：`docs/AGENT_GUIDE.md`
- 分析Skill模板：`docs/ANALYSIS_SKILL_TEMPLATE.md`
- 数据Skill模板：`docs/DATA_SKILL_TEMPLATE.md`
- Agent矩阵：`docs/AGENT_MATRIX.md`

---

*最后更新：2026-05-12*
