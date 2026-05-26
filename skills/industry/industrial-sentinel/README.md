<p align="center">
  <img src="https://img.shields.io/badge/version-V4.5-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.9%2B-green" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="MIT">
  <img src="https://img.shields.io/badge/dependencies-zero-lightgrey" alt="Zero Dependencies">
</p>

# Industrial Sentinel

**AI 原生产业链景气度分析框架。**

框架提供推理规则，AI Agent 提供数据搜索。两者协作，一句话完成从数据采集到景气度判定的全流程。

```bash
/景气度 002916.SZ
```

---

## 这是什么

一个方法论驱动的产业链中观分析框架。解决两个问题：

- **数据源不稳定** — 不硬编码 API，只告诉 AI "搜什么、怎么校验"
- **结论不可审计** — 每一步判定条件透明可查，不是黑箱评分

**一句话：把你对产业链的判断方法论代码化，让任何 AI Agent 都能执行。**

---

## 快速开始

```bash
# 本 skill 位于 AI_Renaissance 项目 skills/industry/industrial-sentinel/ 目录下
cd skills/industry/industrial-sentinel

# 对你的 AI Agent 说一句话
/景气度 002916.SZ
```

AI Agent 自动完成：识别产业链 → 搜索数据 → 展示给你确认 → 回填 → 校验 → 生成报告。

第一次运行数据为空，AI 读取自动生成的搜索任务清单，用自己的搜索能力逐项查找财报、研报、新闻，你确认后写入，再跑即出完整报告。

---

## 如何工作

```
┌─────────────────────────────────────────┐
│              框架（本仓库）                │
│  • 11 条产业链预设模板                    │
│  • 五态拐点模型（规则透明）                │
│  • 生命周期判定                           │
│  • 个股类型分类（5 种，决策树）            │
│  • HTML 仪表盘报告                        │
├─────────────────────────────────────────┤
│         AI Agent（使用者自备）             │
│  • 读任务清单 → 搜索 → 展示 → 用户确认     │
│  • 不绑特定 API，用 Agent 已有搜索能力     │
└─────────────────────────────────────────┘
```

**设计选择：框架不内置数据源。** 硬编码 API 是技术债。把搜索方向告诉 AI，AI 用自己随时可用的工具去获取——框架稳定，数据获取弹性。用户始终在回路中确认数据质量。

---

## 输出

运行后生成 HTML 仪表盘报告，包含：

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

Python 3.9+，零外部依赖（仅标准库）。JSON 数据格式，HTML 输出。

兼容任何能读写文件、执行 shell 的 AI Agent（Claude Code、Codex、Hermes Agent、Cursor 等）。

---

## 文档

| 想看什么 | 读哪个 |
|---------|--------|
| 完整使用文档 | `SKILL.md` |
| AI 自动执行指南 | `references/ai-agent-guide.md` |
| 方法论详细说明 | `references/V4.5-框架结构.md` |
| 数据字段规范 | `references/data-requirements.md` |
| 判断映射规则 | `references/methodology-mapping.md` |
| 版本演进 | `docs/version-history.md` |

---

## License

MIT © 2026
