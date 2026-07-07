---
name: tushare-financial
description: 基于 Tushare Pro 的财务数据和行情数据接口说明。通过个人 token 鉴权，可获取财务三大表、日线行情、资金流向和个股基础信息；调用能力取决于个人 Tushare 账号积分等级。真实执行逻辑位于 data_sources/tushare_source.py。
owner_group: 开发3组（数据）
domain: data
status: draft
---

# Tushare Pro 数据接口说明

## 1. 适用范围

适用任务：
- 为财务 Agent（`agents/financial/`）提供标准化的财务三大表数据（资产负债表、利润表、现金流量表）
- 为技术 Agent（`agents/technical/`）提供日线行情数据
- 为资金流向 Agent（`agents/fundflow/`）提供个股资金流向数据（需较高权限等级）
- 为宏观 Agent（`agents/macro/`）提供个股基础信息

边界说明：
- Tushare 是第三方数据平台，需注册并获取个人 token（https://tushare.pro）
- **调用能力取决于个人 token 的积分等级**。积分越高，可调用的接口越多、频率越高
- 免费注册用户默认有 120 积分，可调用非复权日线和个股基础信息
- 财务三大表接口需要 2000 积分以上
- 资金流向（moneyflow）接口需要 2000 积分以上
- 本 Skill 只说明数据契约，不产出投资判断。Token 由用户自行配置

## 2. 前置准备

1. 注册 Tushare 账号：https://tushare.pro
2. 在「个人主页 - 接口TOKEN」复制 token
3. 设置环境变量：

```bash
export TUSHARE_TOKEN=your_token_here
```

或在项目根目录创建 `.env` 文件：

```text
TUSHARE_TOKEN=your_token_here
```

也可以通过构造参数传入：

```python
from data_sources import TushareDataSource
source = TushareDataSource(token="your_token_here")
```

**推荐做法**：首次使用先调用 `get_token_status()` 验证 token 是否有效。

## 3. 执行数据源

真实数据获取逻辑位于：

```text
data_sources/tushare_source.py
```

推荐调用方式：

```python
from data_sources import TushareDataSource

# 方式一：从环境变量读取 token
source = TushareDataSource()

# 方式二：显式传入 token
source = TushareDataSource(token="your_token")

# 验证 token
status = source.get_token_status()

# 获取数据
data = source.get_financial_data("600519")
```

## 4. 接口一览

### 4.1 基类接口（DataSourceBase）

| 方法 | 说明 | 最低积分 |
|------|------|---------|
| `get_financial_data(stock_code, report_date=None)` | 财务三大表 | 2000 |
| `get_market_data(stock_code, period="daily")` | 日线行情 | 120 |
| `get_fund_flow_data(stock_code)` | 个股资金流向 | 2000 |

### 4.2 便捷方法

| 方法 | 说明 | 最低积分 |
|------|------|---------|
| `get_stock_basic(stock_code)` | 个股基础信息 | 120 |
| `get_income(stock_code, report_date=None)` | 利润表 | 2000 |
| `get_balance(stock_code, report_date=None)` | 资产负债表 | 2000 |
| `get_cashflow(stock_code, report_date=None)` | 现金流量表 | 2000 |
| `get_token_status()` | 验证 token 是否有效 | 120 |
| `has_token()` | 检查是否已配置 token | — |

### 4.3 股票代码格式

支持多种输入格式，内部自动转为 tushare 格式：

| 输入 | tushare 格式 | 说明 |
|------|-------------|------|
| `600519` | `600519.SH` | 上交所，6 位数字 |
| `000001` | `000001.SZ` | 深交所主板 |
| `300750` | `300750.SZ` | 创业板 |
| `SH600519` | `600519.SH` | 带前缀 |
| `SZ000001` | `000001.SZ` | 带前缀 |
| `600519.SH` | `600519.SH` | tushare 原生格式 |

## 5. 输入参数

### get_financial_data

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| stock_code | string | 是 | — | 股票代码 |
| report_date | string | 否 | 最近一个季末 | 报告期，格式 `YYYYMMDD`，如 `20240930` |

### get_market_data

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| stock_code | string | 是 | — | 股票代码 |
| period | string | 否 | `"daily"` | 周期，当前仅支持 daily |

## 6. 输出格式

### 6.1 财务三大表（get_financial_data）

```json
{
  "status": "success",
  "source": "tushare",
  "dataset": "financial_data",
  "fetch_time": "2026-07-07T14:30:00",
  "stock_code": "600519.SH",
  "end_date": "20260331",
  "income": [
    {
      "ts_code": "600519.SH",
      "end_date": "20260331",
      "total_revenue": 50000000000.0,
      "operate_profit": 35000000000.0,
      "n_income": 25000000000.0,
      "basic_eps": 20.0,
      "total_revenue_yoy": 15.5,
      "n_income_yoy": 12.3
    }
  ],
  "balance": [
    {
      "ts_code": "600519.SH",
      "total_assets": 300000000000.0,
      "total_liab": 50000000000.0,
      "total_hldr_eqy_exc_min_int": 250000000000.0
    }
  ],
  "cashflow": [
    {
      "ts_code": "600519.SH",
      "n_cashflow_act": 20000000000.0,
      "free_cashflow": 15000000000.0
    }
  ]
}
```

**部分成功场景**：如果某个子表因权限不足获取失败，`status` 仍为 `success`，但失败的子表字段为 `null`，同时 `warnings` 中会指出：

```json
{
  "status": "success",
  "warnings": ["利润表获取失败（可能权限不足）"],
  "income": null,
  "balance": [...],
  "cashflow": [...]
}
```

### 6.2 错误输出

```json
{
  "status": "error",
  "source": "tushare",
  "dataset": "financial_data",
  "error": "未配置 Tushare token。获取方式：1) 注册 Tushare 账号 https://tushare.pro 2) 在「个人主页 - 接口TOKEN」获取 token 3) 设置环境变量：export TUSHARE_TOKEN=your_token 或通过构造参数传入"
}
```

### 6.3 token 状态检查

```json
{
  "status": "success",
  "source": "tushare",
  "dataset": "token_status",
  "message": "token 有效，Tushare 连接正常"
}
```

## 7. 数据获取流程

1. 检查 tushare 和 pandas 依赖是否已安装
2. 检查 token 是否已配置（环境变量 / `.env` / 构造参数）
3. 惰性初始化 `ts.pro_api(token)`
4. 标准化股票代码为 tushare 格式
5. 调用对应 Pro API 接口
6. DataFrame → dict 列表转换，NaN → null
7. 统一返回 `{status, source, dataset, fetch_time, ...}` 格式

## 8. 权限等级说明

Tushare Pro 采用阶梯式积分制度，不同积分等级可调用的接口不同。

### 积分门槛表（官方权威）

| 积分 | 频次 | 可调用接口 | 获取方式 |
|------|------|-----------|---------|
| **120**（注册即送） | 50 次/分钟，8000 次/天 | `stock_basic`、`daily`（非复权日线） | 免费注册 |
| **2000+** | 200 次/分钟，100000 次/天/API | 以上全部 + `income`、`balancesheet`、`cashflow`、`moneyflow` | 200 元加入 QQ 会员群 |
| **5000+** | 500 次/分钟，无上限 | 常规数据全部开放 | 500 元 或 微信专业群 |
| **10000+** | 500 次/分钟 | + 特色数据（盈利预测、筹码分布等） | 1000 元 |
| **15000+** | 500 次/分钟 | 特色数据无总量限制 | 1500 元 |

### 本模块接口积分要求对照

| 本模块方法 | Tushare 接口 | 免费 (120) | 2000 积分 | 备注 |
|-----------|-------------|:---:|:---:|------|
| `get_stock_basic()` | `stock_basic` | ✅ | ✅ | 上市日期、行业、地区 |
| `get_market_data()` | `daily` | ✅ | ✅ | 非复权日线 OHLCV |
| `get_financial_data()` | `income`/`balancesheet`/`cashflow` | ❌ | ✅ | 财务三大表 |
| `get_fund_flow_data()` | `moneyflow` | ❌ | ✅ | 超大单/大单/中单/小单资金流向 |
| `get_token_status()` | 任意基础接口 | ✅ | ✅ | 仅探测可用性 |

### 快速升级路径

- **200 元** → QQ 会员群（群号 1059991854）→ 获得 2000 积分 → 解锁财务三大表 + 资金流向
- **500 元** → 微信专业用户群 → 获得 5000 积分 → 常规数据无限制
- 注册入口及充值：https://tushare.pro/weborder/#/permission

## 9. 质量检查

- 已写清楚 token 配置方式（环境变量 / .env / 构造参数）
- 已写清楚各接口的最低积分要求
- 已写清楚成功和错误输出格式
- 已说明部分成功（子表失败）的输出格式
- 已有 token 状态检查方法
- 统一使用基类 `DataSourceBase` 规范
