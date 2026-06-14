<p align="center">
  <img src="https://img.shields.io/badge/python-3.9%2B-green" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="MIT">
</p>

# Industrial Sentinel

**AI 原生产业链景气度分析框架。**

框架提供推理规则，项目数据层提供标准化输入。两者协作完成从数据校验到景气度判定的流程。

```bash
/景气度 002916.SZ
```

---

## 这是什么

一个方法论驱动的产业链中观分析框架。解决两个问题：

- **数据源不稳定** — Skill 不直接抓数，真实 fetching/parsing/provider 逻辑由项目 `data_sources/` 承担
- **结论不可审计** — 每一步判定条件透明可查，不是黑箱评分

**一句话：把你对产业链的判断方法论代码化，让任何 AI Agent 都能执行。**

---

## 快速开始

```bash
# 本 skill 位于 AI_Renaissance 项目 skills/industry/industrial_sentinel/ 目录下
cd skills/industry/industrial_sentinel

# 对你的 AI Agent 说一句话
/景气度 002916.SZ
```

项目级 IndustryAgent 自动完成：识别产业链 → 调用项目数据源 → 校验数据质量 → 判断景气度与拐点 → 返回结构化 `Signal`。

数据不足时，系统会返回 `needs_data`、缺失字段和采集任务清单；人工或上游数据源补齐后，再运行即可得到更高置信度结果。

---

## 如何工作

```
┌─────────────────────────────────────────┐
│              框架（本仓库）                │
│  • 9 条产业链预设模板                     │
│  • 五态拐点模型（规则透明）                │
│  • 生命周期判定                           │
│  • 个股类型分类（5 种，决策树）            │
│  • Standalone HTML 仪表盘报告             │
├─────────────────────────────────────────┤
│         项目数据层 data_sources/           │
│  • provider 获取/解析/缓存                  │
│  • 输出标准化 industry/company signals     │
└─────────────────────────────────────────┘
```

**设计选择：Skill 不直接联网抓数。** 真实 provider、解析和缓存放在项目 `data_sources/`；Skill 只消费标准化后的行业与个股信号。这样能保持框架稳定，也符合主项目的数据层边界。

---

## 输出

项目级接入时，正式输出是标准 `Signal`：`direction`、`confidence`、`reasoning`、`signals` 和结构化 `meta`。不生成、不落盘、不返回 HTML 报告路径。网络或 provider 不可用时，数据层会先尝试缓存，再降级到本地 preset 路由；preset 只用于选择分析框架，不代表真实景气结论。

独立 CLI / 手工调试模式运行 `./run.sh` 或 `core/pipeline.py` 时，可生成 HTML 仪表盘报告，包含：

| 区块 | 内容 |
|------|------|
| 产业链结构 | 上游/中游/下游卡片：利润占比、核心玩家、壁垒、议价权 |
| 景气度判定 | 行业周期 / 供需拐点 / 政策催化剂，每项标注来源与日期 |
| 拐点状态 | 五态模型（拐点前→初期→确认→晚期→衰退）+ 信号匹配详情 |
| 生命周期 | 导入期/成长期/成熟期/衰退期 + 判定依据 |
| 个股类型 | 成长型/周期型/价值型/主题型/混合型 + 跟踪指标 |

---

## 支持的产业链

| 层级 | 预设模板 | 代表标的 |
|------|---------|---------|
| 💡 能源 | `ai-energy` | 液冷、HVDC、算力租赁 |
| 🔲 芯片 | `ai-chip` `semiconductor-equipment` `storage` | GPU/ASIC、HBM、设备 |
| 🏗️ 基础设施 | `optical-module` `ai-infrastructure` `pcb` | 光模块、服务器、PCB |
| 🧠 模型 | `ai-model` | 大模型训练/推理、Agent、端侧推理 |
| 🤖 应用 | `robotics` | 减速器、执行器、传感器 |

---

## 方法论溯源

| 来源 | 方法论 | 本框架映射 |
|------|--------|-----------|
| 高盛 | 经济周期四阶段 × 行业轮动 | 五态拐点模型 |
| 桥水 | 四象限 + 不合成单一指标 | 三维度独立展示 |
| 花旗 | 行业周期定位 | 产业链生命周期判定 |
| 摩根士丹利 | Q-C-G 轮动 | 个股类型分类 |
| 麦肯锡 | MECE 拆解 | 产业链结构卡片 |
| 波特 | 价值链分析 | 价值分配与议价权 |

---

## 技术栈

Python 3.9+。独立方法论框架尽量只依赖标准库；接入项目主流程时，通过 `data_sources/` 使用项目已有 provider 与依赖。项目 Agent 输出 JSON/Signal；CLI 模式可输出 HTML。

兼容任何能读写文件、执行 shell 的 AI Agent（Claude Code、Codex、Hermes Agent、Cursor 等）。

---

## 文档

| 想看什么 | 读哪个 |
|---------|--------|
| 项目接入与 CLI 使用文档 | `SKILL.md` |
| 独立调试数据补充指南 | `references/ai-agent-guide.md` |
| 方法论详细说明 | `references/framework-structure.md` |
| 数据字段规范 | `references/data-requirements.md` |
| 判断映射规则 | `references/methodology-mapping.md` |

---

## License

MIT © 2026
