# 迭代日志

## [2026-05-20] V4.5 — 初始发布

**Industrial Sentinel 产业链中观分析框架**

- 三维度独立展示（产业链景气度/拐点/生命周期）
- 真实数据驱动，删除所有算法评分
- 方法论框架设计：用户搜索数据 → 填入JSON → 框架自动推理
- 自动产业链检测（多轮查询+关键词匹配）
- 五态拐点模型 + 生命周期判定 + System B个股类型判定
- 产业链结构卡片（上游/中游/下游）
- 已覆盖5个产业链preset：光通信、AI能源、AI芯片、AI基础设施、机器人

**交付物：**
- `SKILL.md` — 框架定义
- `core/pipeline.py` — 端到端流水线
- `core/system_a.py` — 五态拐点 + 生命周期判定
- `core/system_b.py` — 个股类型判定
- `core/auto_detect_preset.py` — 自动产业链检测
- `references/data-requirements.md` — 必填数据清单
- `references/methodology-mapping.md` — 推理规则映射
- `references/data-standardization.md` — 数据标准化指南
- 5个产业链YAML模板（`data/presets/` + `references/preset-chains/`）

---

*V4.5 为初始发布版本。后续迭代将在此记录。*
