---
name: industrial_sentinel
description: |
  产业链中观分析框架。三维度独立展示：产业链景气度、产业链拐点、产业链生命周期。
  基于项目数据层注入的财报数据与行业数据，输出可溯源的结构化分析。
  System B 仅做个股类型判定（成长/周期/价值/主题/混合），不写交易计划。
  触发词：景气度、/景气度。
---

# Industrial Sentinel | 产业链中观分析框架

**Trigger:** 当用户提到"景气度"、"/景气度"时激活。

---

## 1. 快速开始

> 本 skill 位于 [AI_Renaissance](https://github.com/duolongworld/AI_Renaissance) 项目 `skills/industry/industrial_sentinel/` 目录下，由 Agent 通过 `runtime.py` 调用。

### 1.1 环境准备

```bash
# 进入 skill 目录（在 AI_Renaissance 项目根目录下）
cd skills/industry/industrial_sentinel

# 运行分析（支持代码/简称）
./run.sh 002916.SZ
./run.sh 深南电路
```

**前置依赖**：Python 3.9+。独立方法论框架尽量只依赖标准库；项目集成模式通过 `data_sources/` 使用主项目已有 provider 与依赖。

### 1.2 触发方式

**常见触发词**：`/景气度 [代码]`、`景气度 [行业/个股]`

输入股票代码、简称、行业词或 preset 时，项目级 `IndustryAgent` 会先做输入归一化，再调用项目 `data_sources/` 获取或注入标准化数据，最后由 `runtime.py` 输出行业景气度、拐点状态、生命周期、个股类型和产业链结构摘要。

项目级 `IndustryAgent` 接入时只返回标准 `Signal` 和结构化 `meta`，不生成、不落盘、不返回 HTML 报告路径。HTML 仅用于 `./run.sh` / `core/pipeline.py` 的独立 CLI 或人工调试模式。

**CLI 完整输出**（默认）：
- 产业链结构卡片（上游/中游/下游）
- 产业链景气度判定（行业周期/供需拐点/政策催化剂）
- 拐点状态（五态模型）
- 生命周期阶段
- System B 个股类型判定
- HTML 仪表盘报告

**如需轻量版**（只看产业链结构）：
```bash
./run.sh <code> --lite
```

### 1.3 项目级执行流程（关键）

**这是本 skill 的核心设计：Skill 不直接联网抓数，项目数据层负责 provider 获取、解析和缓存。**

当主项目调用 `IndustryAgent.analyze()` 后，应按以下流程执行：

```
Step 1: IndustryAgent 识别输入类型
        → stock_code / stock_name / industry / preset

Step 2: stock_code 输入调用 data_sources.industrial_sentinel
        → 获取行业景气数据、财务数据、缓存状态与降级原因

Step 3: industry / preset 输入只做框架路由
        → 不把 preset 命中当作真实景气结论

Step 4: runtime.py 消费标准化 industry_result / financial_data / config
        → 生成 direction / confidence / reasoning / signals / meta

Step 5: IndustryAgent 包装为标准 Signal
        → Signal 构造异常时返回 neutral，并标记 needs_human_review
```

**重要**：
- 不要在 Skill 内新增 provider 抓数逻辑
- 真实 fetching/parsing/provider 放在项目 `data_sources/`
- 数据缺失时输出低置信降级结果、`needs_data`、缺失字段和采集任务，不编造行业景气度
- HTML 只属于 CLI / 人工调试路径，不进入 Orchestrator 主流程

---

## 2. 核心架构

### 2.1 三维度独立展示

当前框架不合成单一“产业拐点指数”，三个维度各自独立展示：

| 维度 | 核心问题 | 展示形式 |
|------|---------|---------|
| **产业链景气度** | 行业当前景气如何？ | 三维度描述（行业周期/供需拐点/政策催化剂）+ 真实数据 |
| **产业链拐点** | 处于五态模型的哪个阶段？ | 五态判定 + 信号匹配详情 |
| **产业链生命周期** | 行业处于生命周期的哪个阶段？ | 大卡片（导入期/成长期/成熟期/衰退期） |

**禁止项**：
- 三维评分（周期/供需/政策数值评分）
- 生命周期推断评分
- 任何没有真实出处的数字

**必须项**：
- 每个数字标注来源（财报/研报/新闻/机构）
- 每个数字标注时间
- 产业链景气度判断必须基于真实数据推断，并明确标注推断依据
- 如数据缺失，直接标注"数据缺失"，不得用算法填充

### 2.2 System A — 行业景气度与拐点判断

**输入**：标准化行业数据与同业/个股验证数据。System A 只消费行业级信号，System B 才消费个股级信号。

**活跃子维度**（景气度分析）：

| 子维度 | 核心问题 | 数据来源 |
|--------|---------|---------|
| **行业周期** | 行业处于生命周期的哪个阶段？ | 产业链结构、技术成熟度、渗透率曲线 |
| **供需拐点** | 供需是否出现结构性反转？ | 订单backlog、产能利用率、库存天数、价格趋势 |
| **政策催化剂** | 政策是否进入密集释放期？ | 产业补贴、准入壁垒、技术标准、试点推广 |

**休眠子维度**（保留接口但不展示）：
- 宏观环境（GDP/PMI/CPI）
- 产业链验证（上下游同步共振）

**输出**：
- 拐点状态：拐点前 / 拐点初期 / 拐点确认 / 拐点晚期 / 拐点后衰退
- 生命周期阶段：导入期 / 成长期 / 成熟期 / 衰退期
- 信号匹配详情（具体参数 + 置信度 + 数据来源层级）
- 异动分析（偏离度/异常检测）
- 中轴共振（多维度信号一致性评估）

**数据防火墙**：System A 禁止输入任何公司特定数据。允许：行业订单增速、行业产能利用率、行业价格趋势。禁止：某公司订单增速、某公司现金流、某公司市场份额。

### 2.3 System B — 个股类型判定

**定位**：不做交易计划，不做仓位建议，只做类型判定。

**判定规则**：

| 类型 | 判定条件 |
|------|---------|
| **成长型** | 营收增速≥25%，或2025全年营收增速≥50%；研发投入占比≥5%；处于高景气赛道 |
| **周期型** | 营收增速<25%但净利润波动大；毛利率随行业周期波动；重资产运营模式 |
| **价值型** | 营收增速<15%；ROE稳定≥10%；股息率≥2%；PE低于行业中位数 |
| **主题型** | 营收增速不稳定；受政策/事件驱动；基本面与股价背离 |
| **混合型** | 兼具两种以上特征；或多业务板块分属不同类型 |

**输出**：
- 个股类型（成长型/周期型/价值型/主题型/混合型）
- 判定理由（3-5句话）
- 核心矛盾（一句话提炼）
- 跟踪指标（5个后续需关注的指标）
- 风险清单（5个核心风险）

**禁止**：
- 不写交易计划（建仓区间、加仓触发、止盈止损）
- 不给仓位建议
- 不给目标价

### 2.4 产业链结构区块

**展示形式**：3张卡片（上游·材料与芯片 / 中游·模块与器件 / 下游·设备与云厂商）

**每张卡片包含**：
- 利润占比
- 核心玩家
- 壁垒/现状
- 议价权

**底部增加**：
- 价值分配总结
- 标的定位

优先使用 `references/preset-chains/` 中的产业链 preset；未覆盖行业应返回清晰的 `needs_data` 和补充任务，不返回空白结构冒充完整分析。

---

## 3. 数据层原则

### 3.1 数据来源层级

| 层级 | 名称 | 数据源 | 置信度基准 |
|------|------|--------|-----------|
| **L1** | 官方/财报 | 公司财报、交易所公告 | 90分 |
| **L2** | 券商研报 | 券商研究报告 | 70分 |
| **L3** | 行业新闻 | 产业新闻、公司公告 | 50分 |
| **L4** | 知识库 | 历史数据、分析框架 | 30分 |

### 3.2 数据处理铁律

1. **禁止MOCK数据**：数据缺失则标注"数据缺失"，不得编造数字
2. **禁止评分数字**：不展示三维评分、不推断生命周期阶段评分、不用算法打分
3. **来源必填**：每个数据点必须携带 source + source_url + source_type + date
4. **时间标注**：所有数据必须标注获取时间
5. **数据验证**：CLI 调试时先用 `scripts/validate_data.py` 检查数据完整性；项目 Agent 通过 `Signal.meta` 暴露数据质量

### 3.3 数据补充流程

**核心设计**：框架本身不爬数据。项目级接入时，缺失数据应由 `data_sources/` 或上游数据服务补齐；独立 CLI 调试时，才使用本地数据模板与采集任务清单。

**项目级流程**：

```bash
# 1. data_sources/ 获取或注入标准化行业数据与财务数据
# 2. IndustryAgent 将数据传入 runtime.py
# 3. runtime.py 输出 Signal 字典与 data_collection_tasks
# 4. Orchestrator 只消费标准 Signal，不依赖本地 JSON 或 HTML
```

**CLI / 手工调试流程**：
```bash
# 首次运行：数据为空 → 生成采集任务清单 → 提示补充缺失字段
./run.sh <code>

# 手工或调试工具补齐 data/<code>_real_data.json 后再次运行：
./run.sh <code>
# → 生成 CLI HTML 报告
```

**任务清单包含什么**（以光模块为例）：

| 字段 | 内容 |
|------|------|
| `task_id` | 唯一标识，如 `signal_barometric_InP衬底价格_0` |
| `layer` | 所属维度（System A五态/产业链结构/生命周期/System B个股） |
| `chinese_queries` | 中文搜索词列表，如 `["光模块 InP衬底价格 2026", "光模块 InP衬底价格 最新数据"]` |
| `english_queries` | 英文搜索词（备用） |
| `source_priority` | 数据来源优先级，如 `["行业研报/券商调研", "行业协会/咨询机构", "公司公告"]` |
| `required_level` | ★必填 / ☆推荐 / ○可选 |
| `freshness` | 时效要求，如 "最近30天行业数据" / "最近季度财报（90天内）" |
| `validation_rule` | 校验规则，如 ">30%为高毛利，环比改善↑" |
| `fallback_strategy` | 搜不到时的降级策略，如 "用往期财报毛利率推算趋势" |
| `field_path` | 回填路径，如 `industry_signals.industry_price_yoy` |

**数据质量校验**：

补充数据时必须执行：
1. **来源校验**：数字必须有 `source`（财报/研报/新闻/公告）和 `date`（YYYY-MM-DD）
2. **时效校验**：超过90天的数据标注"数据老化"
3. **优先级校验**：优先使用 `source_priority` 排第一的来源
4. **缺失降级**：搜不到时用 `fallback_strategy`，绝不编造
5. **趋势标注**：按 `validation_rule` 标注数值趋势（↑/↓/→）

### 3.4 CLI 手动数据准备流程（备选）

以下流程只用于 `./run.sh` / `core/pipeline.py` 的独立调试，不是项目级 Agent 主流程：

```bash
# 1. 使用你的AI搜索工具搜索财报和行业数据
# 搜索示例："<code> Q1 2026 财报 营收 毛利率"

# 2. 生成空白模板
python scripts/generate_data_template.py <code> --name <名称> --industry <行业> --position <产业链位置>

# 3. 填入搜索到的数据
# 编辑 data/<code>_real_data.json

# 4. 验证数据完整性
python scripts/validate_data.py <code>

# 5. 生成报告
./run.sh <code>
```

---

## 4. 五态拐点模型

### 4.1 状态定义

| 状态 | 判定条件 | 研究含义 |
|------|---------|---------|
| **拐点前** | 信号<2个匹配，或营收增速<10% | 观察等待，补充验证数据 |
| **拐点初期** | 2-3个信号匹配，营收增速10-20% | 重点跟踪新增信号 |
| **拐点确认** | 4-5个信号匹配，营收增速≥20% | 提高行业关注优先级 |
| **拐点晚期** | 5-6个信号匹配但增速放缓 | 关注过热和反转风险 |
| **拐点后衰退** | 信号反转≥2个 | 降低关注，等待新周期证据 |

### 4.2 信号匹配详情

展示具体参数（产能利用率%、库存天数等）及其置信度+数据来源层级，禁止抽象评分。

---

## 5. 方法论溯源

本框架与以下方法论耦合：

| 来源 | 方法论 | 本框架映射 |
|------|--------|----------|
| **高盛** | 经济周期四阶段×行业轮动 | 五态拐点模型（宏观→产业链降维） |
| **桥水** | 四象限+不合成单一指标 | 三维度独立展示（景气度/拐点/生命周期各自独立） |
| **花旗** | 行业周期定位 | 产业链生命周期（渗透率曲线→技术代际+产能周期） |
| **摩根士丹利** | Q-C-G轮动+估值锚定 | System B类型判定 |
| **麦肯锡** | MECE拆解 | 产业链结构卡片（上游/中游/下游） |
| **波特** | 价值链分析 | 价值分配与议价权分析 |

---

## 6. 常见问题与排障

### 6.1 数据缺失

**现象**：报告中出现"数据缺失"
**解决**：
1. 项目级 Agent：检查 `Signal.meta.needs_data`、`degradation_reasons` 和 `data_collection_tasks`
2. 通过 `data_sources/` 或上游数据服务补齐行业级、同业篮子和公司财务字段
3. CLI 调试：可运行 `python scripts/validate_data.py <code>`，补齐 `data/<code>_real_data.json` 后重新运行 `./run.sh <code>`

### 6.2 行业识别失败

**现象**："无法识别行业"
**解决**：检查 `core/auto_detect_preset.py` 的本地 preset 路由与 `data_sources/` 返回的行业字段。

### 6.3 产业链结构不显示

**现象**：产业链结构区块空白
**解决**：优先使用 `references/preset-chains/` 中的 preset YAML；未覆盖行业应新增对应 preset 结构，不要在主流程中返回空白结构冒充完整分析。

---

## 7. 维护原则

- 行业模块不维护独立发布节奏，迭代跟随主项目。
- Skill 不直接联网抓数或落盘 provider 结果，真实数据获取统一放在 `data_sources/`。
- System A 与 System B 的数据边界必须清晰：行业级信号判断景气度，个股级信号判断标的类型。

---

## 8. 文件结构

```text
industrial_sentinel/
├── README.md                    # 项目首页
├── SKILL.md                     # 本文件
├── runtime.py                   # Agent 调用入口（run_industrial_sentinel）
├── run.sh                       # 启动脚本
├── core/
│   ├── pipeline.py              # 主流水线（4步）
│   ├── system_a.py              # 五态拐点判定 + 生命周期判定
│   ├── system_b.py              # 个股类型判定
│   ├── auto_detect_preset.py    # 本地 preset 路由
│   └── data_collection_guide.py # AI数据采集任务生成器
├── scripts/
│   ├── generate_data_template.py # CLI 数据模板生成器
│   └── validate_data.py         # 数据验证器
├── data/
│   └── mappings/                # 股票→行业映射表
│       ├── stock-to-industry-optical.json
│       └── ...
├── references/
│   ├── framework-structure.md   # 方法论详细文档
│   ├── industry-benchmark-database.yaml  # 行业基准数据库
│   ├── stock-to-industry-mapping.json    # 股票→行业映射
│   ├── data-requirements.md     # 数据字段清单
│   ├── methodology-mapping.md   # 数据→判断映射规则
│   ├── data-standardization.md  # 数据标准化指南
│   └── preset-chains/           # 黄仁勋AI五层蛋糕预设
│       ├── layer1-energy/
│       │   └── ai-energy.yaml           # 能源/散热/电力
│       ├── layer2-chip/
│       │   ├── ai-chip.yaml             # AI芯片/先进封装
│       │   ├── semiconductor-equipment.yaml  # 半导体设备/材料
│       │   └── storage.yaml             # 存储/HBM
│       ├── layer3-infrastructure/
│       │   ├── optical-module.yaml      # 光通信/光模块
│       │   ├── ai-infrastructure.yaml   # 服务器/数据中心
│       │   └── pcb.yaml                 # PCB/覆铜板/载板
│       ├── layer4-model/
│       │   └── ai-model.yaml            # 大模型/训练推理
│       └── layer5-application/
│           └── robotics.yaml            # 机器人/具身智能
├── templates/
│   └── pipeline-output.html     # HTML报告模板
└── reports/                     # CLI 运行时生成报告，项目接入不依赖
```

---

*方法论详细说明请参阅 `references/framework-structure.md`*

---

## 附录：维护者代码陷阱

**陷阱0：不要在 Skill runtime 里建数据抓取引擎。**
真实 provider、解析、缓存和离线 fallback 都放在项目 `data_sources/`。Skill runtime 只消费标准化后的 `industry_signals`、`peer_basket_signals` 和 `company_signals`。

**陷阱1：preset 路由不是景气结论。**
命中 `robotics`、`optical-module` 等 preset 只能选择分析框架；没有真实行业数据时必须低置信度降级并标记 `needs_data`。

**陷阱2：项目 Agent 不输出 HTML。**
HTML 只属于 `./run.sh` 或 `core/pipeline.py` 的 CLI/人工调试路径；`IndustryAgent` 只返回标准 `Signal` 与结构化 `meta`。

**陷阱3：System A / System B 数据边界。**
System A 消费行业级信号和同业篮子，System B 才消费个股财务信号。不要用单家公司财报直接代表行业景气度。

**陷阱4：Signal 构造必须兜底。**
runtime 返回缺字段、非法方向或非法置信度时，Agent 必须返回 neutral Signal，并在 `meta` 中标记 `needs_human_review`。
