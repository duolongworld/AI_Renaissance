# Industrial Sentinel — Agent 与 CLI 边界指南

> 本文档说明 Industrial Sentinel 在主项目 Agent 模式和独立 CLI 调试模式下的职责边界。

---

## 一、项目 Agent 模式

主项目调用链路为：

```text
IndustryAgent
  -> data_sources.industrial_sentinel
  -> industrial_sentinel.runtime.run_industrial_sentinel()
  -> agents.signal.Signal
  -> Orchestrator
```

项目级 `IndustryAgent` 的正式产物是标准 `Signal` 和结构化 `meta`，不生成、不落盘、不返回 HTML 报告路径。

### 输入

支持以下输入：

- 股票代码：如 `000700.SZ`
- 股票简称：如 `模塑科技`
- 行业词：如 `机器人`、`光模块`
- preset：如 `robotics`、`optical-module`

股票代码输入会尝试调用项目 `data_sources/` 获取行业景气数据和财务数据；行业词或 preset 输入只用于选择分析框架，不代表真实景气结论。

### 输出

必须返回标准 `Signal`：

```python
{
    "direction": "bullish | bearish | neutral",
    "confidence": 0.0,
    "reasoning": "...",
    "signals": [],
    "meta": {
        "needs_data": True,
        "degradation_reasons": [],
        "data_quality": "complete | incomplete | missing",
        "data_source": {}
    }
}
```

如果 runtime 返回缺字段、非法方向或非法置信度，`IndustryAgent` 必须返回 neutral Signal，并在 `meta` 中标记 `needs_human_review=True`。

---

## 二、数据层职责

真实 fetching、parsing、provider 适配和缓存属于项目 `data_sources/`：

- `data_sources/industrial_sentinel.py`：行业 Agent 的复合数据源入口
- `data_sources/industry_sentiment.py`：行业板块景气数据
- `data_sources/eastmoney.py`：财务数据
- `data_sources/industry_preset_detection.py`：行业映射辅助查询

Skill runtime 只消费标准化后的数据，不在 `skills/industry/industrial_sentinel/` 内新增联网抓数逻辑，也不把 provider 结果写回 skill 目录。

数据缺失时，runtime 输出低置信降级结果，并在 `meta` 中提供：

- `needs_data`
- `degradation_reasons`
- `missing_fields`
- `data_collection_tasks`
- `confidence_cap_reason`

---

## 三、方法论输入

行业景气度和拐点判断应优先依赖行业级与同业篮子数据，而不是单一公司财报。

### System A：行业景气度与拐点

优先输入：

- 行业需求增速
- 行业订单或排产变化
- 行业价格趋势
- 行业库存与产能利用率
- 政策催化剂
- 同业收入、毛利率、现金流的共振情况

System A 不应把单家公司财报直接当作行业景气度结论。

### System B：个股类型

个股财务数据用于判断标的类型：

- 成长型
- 周期型
- 价值型
- 主题型
- 混合型

System B 不输出交易计划、仓位建议或目标价。

---

## 四、独立 CLI 调试模式

`./run.sh` 和 `core/pipeline.py` 保留给手工调试、演示和 HTML 报告生成。

CLI 调试模式可以读取：

```text
data/<code>_real_data.json
```

也可以生成：

```text
reports/*.html
```

这些文件不是 Orchestrator 主流程接口。主项目只消费 `Signal`。

---

## 五、数据补充清单

当 `Signal.meta.needs_data=True` 时，优先补充以下数据：

| 层级 | 字段类型 | 示例 |
|------|----------|------|
| 行业级 | 需求增速、价格、订单、库存、产能利用率 | 光模块需求增速、HBM 价格趋势 |
| 同业篮子 | 同业收入增速、毛利率中位数、现金流趋势 | 多家公司财报汇总 |
| 公司级 | 营收、毛利率、研发投入、现金流、资产负债 | 个股类型判定 |
| 催化剂 | 政策、技术代际、客户验证、产能投放 | 行业拐点验证 |

每个数据点都应带来源、日期和口径说明。搜不到的数据必须标记缺失，不要编造。

---

## 六、检查清单

提交或接入前确认：

- [ ] Agent 模式不生成 HTML
- [ ] Agent 模式不写 `skills/industry/industrial_sentinel/data/`
- [ ] provider 逻辑只在 `data_sources/`
- [ ] preset 命中不被当作真实景气结论
- [ ] 数据不足时有 `needs_data` 和降级原因
- [ ] `Signal.from_dict()` 异常有 neutral 兜底
