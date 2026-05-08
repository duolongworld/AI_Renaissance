---
name: akshare-fundflow-snapshot
description: 基于 AkShare 的资金流全景数据契约，一次返回个股基础信息、个股主力资金、相关行业/概念板块资金、大盘主力资金与北向资金概览；真实执行逻辑位于 data_sources/akshare.py。
owner_group: 开发3组（数据）
domain: data
status: draft
---

# AkShare 资金流全景数据契约 Skill

## 1. 适用范围

适用任务：
- 为 `agents/fundflow/agent.py` 提供一份可直接消费的资金流全景快照
- 同时获取个股基础信息、个股主力资金流向、相关行业 / 概念板块资金、大盘主力资金、北向资金概览
- 避免把资金流分析依赖拆成多个零散 Skill，降低调用复杂度

边界说明：
- 本 Skill 只描述数据契约，不直接产出投资判断
- 底层仍由多个 AkShare 接口拼装，但对上层只暴露一个统一入口
- 某个子模块失败时，顶层结果仍可能返回 `success`，调用方需要检查各子模块自己的 `status`

## 2. 执行数据源

真实数据获取逻辑位于：

```text
data_sources/akshare.py
```

推荐调用方式：

```python
from data_sources import AkshareDataSource

source = AkshareDataSource()
data = source.get_fundflow_snapshot(
    stock_code="600519",
    indicator="今日",
    flow_limit=10,
    sector_top_n=10,
    concept_limit=10,
)
```

## 3. 输入参数

### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|---|---|---|---|
| stock_code | string | 6 位 A 股股票代码，支持 `SH/SZ/BJ` 前缀 | `"600519"` |

### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| indicator | string | `"今日"` | 板块资金口径，仅支持 `今日` / `5日` / `10日` |
| flow_limit | int | 20 | 个股资金流与大盘主力资金返回最近多少条记录 |
| sector_top_n | int | 20 | 行业 / 概念资金榜返回前多少条 |
| concept_limit | int | 10 | 个股概念标签最多返回多少条 |

## 4. 输出格式

```json
{
  "status": "success",
  "source": "akshare",
  "dataset": "fundflow_snapshot",
  "fetch_time": "2026-05-06T00:00:00",
  "stock_code": "600519",
  "basic_info": {
    "status": "success",
    "profile": {
      "股票代码": "600519",
      "股票名称": "贵州茅台",
      "总市值": 1734131271029.85,
      "所属行业": "白酒Ⅱ"
    }
  },
  "stock_fund_flow": {
    "status": "success",
    "summary": {
      "最新主力净流入": -1381366192.0,
      "近5日主力净流入": -2068522512.0
    }
  },
  "sector_fund_flow": {
    "status": "success",
    "stock_context": {
      "stock_code": "600519",
      "stock_name": "贵州茅台",
      "industry": "白酒Ⅱ",
      "concepts": ["白酒", "超级品牌"]
    }
  },
  "market_fund_flow": {
    "status": "success",
    "northbound": {
      "trade_date": "2026-05-05",
      "northbound_net_buy": 0.0
    }
  }
}
```

### 错误输出

```json
{
  "status": "error",
  "source": "akshare",
  "dataset": "fundflow_snapshot",
  "error": "akshare 未安装，请先执行 `pip install akshare`"
}
```

## 5. 数据获取流程

1. 标准化输入股票代码
2. 获取个股基础信息：市值、行业、概念标签、指数归属
3. 获取个股主力资金流向：主力 / 超大单 / 大单 / 中单 / 小单
4. 获取行业 / 概念板块资金排名，并筛出该股票相关板块
5. 获取大盘主力资金与最新交易日北向 / 南向资金概览
6. 聚合为单一 `fundflow_snapshot` 结果返回

## 6. 子模块说明

统一 Skill 内部包含 4 个子数据块：

- `basic_info`：个股基础信息、市值、所属行业、概念热度、入选指数
- `stock_fund_flow`：个股主力资金历史序列与摘要
- `sector_fund_flow`：行业 / 概念资金榜及该股关联板块
- `market_fund_flow`：大盘主力资金走势与北向资金概览

调用方建议：
- 先读 `basic_info.profile` 建立个股画像
- 再读 `stock_fund_flow.summary` 判断主力资金趋势
- 再读 `sector_fund_flow.related_*` 判断是否处于板块风口
- 最后用 `market_fund_flow.northbound` 判断市场环境顺风或逆风

## 7. 质量检查

- 统一一个 Skill 暴露给上层，避免重复注册和多次选取
- 已写明子模块结构，便于 Agent 精准读取
- 已保留中文字段，便于 debug_ui 直接展示
- 可直接通过 `debug_ui` 的单一入口测试
