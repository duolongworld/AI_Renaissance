---
name: market-ohlcv
description: 统一 OHLCV 行情数据接口说明。通过 data_sources.market_ohlcv 加载标准 CSV、EastMoney K 线，并在未配置 EASTMONEY_UT 或 EastMoney 不可用时自动兜底到 data_sources.tencent_technical。供 technical Agent 和传统模型融合等分析 Skill 获取行情数据。本目录只保留 Skill 说明，不再提供 scripts/ohlcv_loader.py 包装入口。
owner_group: 开发3组（数据）
domain: data
status: stable
---

# Market OHLCV 统一行情接口 Skill

## 定位

本 Skill 只描述数据接口、调用方式、输出字段和边界，不承载真实抓取/解析逻辑。真实实现位于：

```python
data_sources.market_ohlcv
```

技术分析 Skill 或 Agent 需要行情数据时，应直接调用 `data_sources.market_ohlcv`，不要在 `skills/technical/` 内实现数据源细节，也不要再通过 `skills/data/market_ohlcv/scripts/ohlcv_loader.py` 中转；该旧包装入口已移除。

当前运行时边界：

- `data_sources/`：真实 HTTP 请求、CSV 解析、字段归一化、数据源兜底策略。
- `skills/data/market_ohlcv/SKILL.md`：接口契约说明，供 Agent/Skill 作者理解如何调用。
- `skills/technical/`：只做技术分析，不持有行情数据源实现。

## 推荐调用方式

### 直接函数调用

```python
from data_sources.market_ohlcv import load_rows_from_code, load_ohlcv_csv

rows, uncertainties = load_rows_from_code(
    code="600519",
    start="2026-01-01",
    end="2026-05-23",
    freq="D",
    adjust="none",
)
```

### 类封装调用

```python
from data_sources.market_ohlcv import MarketOhlcvDataSource

source = MarketOhlcvDataSource()
rows, uncertainties = source.load_rows_from_code("600519", "2026-01-01", "2026-05-23")
```

### CSV 调用

```python
from data_sources.market_ohlcv import load_ohlcv_csv

rows = load_ohlcv_csv("/path/to/ohlcv.csv")
```

## 接口

### `load_rows_from_code(code, start, end, freq="D", adjust="none")`

统一股票代码行情入口。优先 EastMoney，失败或未配置 `EASTMONEY_UT` 时兜底到 Tencent Technical。

参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | `str` | 是 | 股票代码，如 `600519`、`000001`、`300750` |
| `start` | `str` | 是 | 开始日期，格式 `YYYY-MM-DD` |
| `end` | `str` | 是 | 结束日期，格式 `YYYY-MM-DD` |
| `freq` | `str` | 否 | K 线周期：`D`/`W`/`M`，默认 `D` |
| `adjust` | `str` | 否 | 复权口径，默认 `none`；Tencent 兜底对复权口径存在近似说明 |

返回：

```python
Tuple[List[Dict], List[str]]
```

- 第一个元素 `rows`：标准化 OHLCV 行情数组。
- 第二个元素 `uncertainties`：数据源选择、复权口径、异常兜底等不确定性说明。

每条 row 至少包含：

```json
{
  "date": "2026-05-22",
  "open": 1300.0,
  "high": 1310.0,
  "low": 1280.0,
  "close": 1290.2,
  "volume": 49157.0
}
```

可选字段：`amount`、`turnover_rate`、`turnover`、`money`。

`uncertainties` 示例：

```python
[
    "未配置 EASTMONEY_UT，使用 data_sources.tencent_technical 行情数据源。",
    "Tencent 行情接口默认返回 qfq/前复权日线，可能与 EastMoney none 口径存在差异。",
    "行情来源：tencent_technical:sh600519",
]
```

### `load_ohlcv_csv(path)`

加载本地 CSV。

必需列：

```text
date, high, low, close, volume
```

可选列：

```text
open, amount, turnover, money, turnover_rate
```

如果缺少必需列，会抛出 `ValueError`。

### `fetch_ohlcv_eastmoney(code, start, end, *, freq="D", adjust="none", config)`

EastMoney K 线底层入口。通常不建议业务代码直接调用，除非需要显式传入 `EastMoneyConfig`。

### `fetch_ohlcv_tencent(code, start="", end="", *, freq="D", adjust="none", limit=None)`

Tencent Technical 兜底入口。通常由 `load_rows_from_code()` 自动调用；当需要直接验证腾讯行情覆盖情况时可以单独使用。

### `MarketOhlcvDataSource`

轻量类封装，提供：

- `load_csv(path)`
- `load_rows_from_code(code, start, end, *, freq="D", adjust="none")`

## 数据源策略

1. 如果配置了环境变量 `EASTMONEY_UT`，优先调用 EastMoney。
2. 如果 EastMoney 失败或返回空数据，自动兜底到 Tencent Technical。
3. 如果未配置 `EASTMONEY_UT`，直接调用 Tencent Technical。
4. 上层 Agent/Skill 应把 `uncertainties` 透传到 `meta.uncertainties`，不要静默吞掉数据口径差异。

## 调用方约定

- `TechnicalAgent` 实时行情模式应使用 `data_sources.market_ohlcv.load_rows_from_code()`。
- `traditional_model_fusion` 通过 `fusion_traditional_models.data_adapters` 兼容旧内部导入，但最终仍代理到 `data_sources.market_ohlcv`。
- 新代码不得重新引入 `skills/data/market_ohlcv/scripts/ohlcv_loader.py` 或同类中转包装。
- 如果测试需要固定数据，优先通过 Agent config 注入 `ohlcv_rows`，或使用 `load_ohlcv_csv()` 加载本地 CSV。

## 边界

- 本 Skill 不产生 `direction/confidence` 等投资判断字段。
- `adjust="none"` 时，Tencent 兜底接口可能返回前复权近似口径，调用方应读取 `uncertainties`。
- 数据源异常、样本不足、复权口径不一致，应由上层分析 Skill 在 meta 中传播不确定性。
- 非官方公开行情接口可能变更；当 HTTP 请求失败或返回空数据时，上层应允许降级为 neutral/needs_human_review，而不是假设数据完整。
