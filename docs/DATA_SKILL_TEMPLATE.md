# 数据 Skill 模板

> 面向开发3组。数据 Skill 用来描述数据源接口说明：输入参数、输出字段、失败格式、数据边界和调用示例。真实抓取和解析逻辑放在 `data_sources/`。

数据 Skill 和专家分析 Skill 分开维护：

- 数据 Skill：说明“能拿到什么数据、字段是什么、失败时怎么返回”。
- 专家分析 Skill：说明“拿到数据后如何判断、如何生成 Signal”。

---

## 推荐目录

```text
skills/data/{data_interface}/SKILL.md
```

示例：

```text
skills/data/eastmoney_guba/SKILL.md
```

真实执行代码放在：

```text
data_sources/{provider_or_dataset}.py
```

示例：

```text
data_sources/eastmoney_guba.py
```

---

## SKILL.md 模板

````markdown
---
name: [data-interface-name]
description: [一句话说明提供什么数据、给谁消费。说明真实数据源代码位置。]
owner_group: 开发3组（数据）
domain: data
status: draft
---

# [数据接口说明中文名称]

## 1. 适用范围

适用任务：
- [这个数据接口说明提供什么数据]
- [哪些 Agent / 分析 Skill 会消费这些数据]
- [适合什么标的和时间范围]

边界说明：
- [数据源代表性偏差]
- [反爬、限流、缺失、延迟等风险]
- [本 Skill 只说明数据接口，不做分析判断]

## 2. 执行数据源

真实数据获取逻辑位于：

```text
data_sources/[provider_or_dataset].py
```

推荐调用方式：

```python
from data_sources import [DataSourceClass]

source = [DataSourceClass]()
data = source.[method_name](...)
```

## 3. 输入参数

### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|---|---|---|---|
| stock_code | string | 股票代码 | "600519" |

### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| pages | int | 2 | 抓取页数 |

## 4. 输出格式

```json
{
  "status": "success",
  "source": "",
  "fetch_time": "",
  "data": []
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | success 或 error |
| fetch_time | string | 数据获取时间 |

### 错误输出

```json
{
  "status": "error",
  "error": "",
  "data": []
}
```

## 5. 数据获取流程

1. [标准化输入]
2. [调用外部接口或页面]
3. [解析字段]
4. [去重/清洗/截断]
5. [返回结构化数据]

## 6. 质量检查

- 是否写清楚真实数据源代码位置
- 是否写清楚必填和可选参数
- 是否写清楚成功和错误输出格式
- 是否说明字段含义和单位
- 是否说明数据源偏差、限流和失败场景
- 是否有最小调用示例
````

---

## 与专家分析 Skill 的区别

数据 Skill 不输出 `direction`、`confidence` 或投资 `Signal`。这些字段属于专家分析 Skill，由 `docs/ANALYSIS_SKILL_TEMPLATE.md` 规范。
