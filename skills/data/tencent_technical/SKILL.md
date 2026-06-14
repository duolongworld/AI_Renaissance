---
name: tencent-technical
description: 通过腾讯财经 API 获取股票 K线数据（日/周/月/分钟），并计算技术指标（MA均线、BOLL布林带、RSI相对强弱）。支持 A股（沪深）、港股、美股。作为数据获取层 Skill，供技术分析 Agent 或其他需要行情数据的模块调用。当用户需要获取股票行情、K线图数据、技术指标（均线、布林带、RSI）时使用此 Skill。
owner_group: 开发3组（数据）
domain: data
status: stable
---

# 腾讯财经 K线数据获取 Skill

## 实现位置

本 Skill 只描述腾讯财经 K 线数据接口和输出形态；真实 HTTP 请求、响应解析、指标计算实现位于：

```python
data_sources.tencent_technical
```

`skills/data/tencent_technical/scripts/fetch_kline.py` 仅作为薄包装保留历史导入路径和 CLI 入口，不承载核心数据源逻辑。

推荐业务代码直接调用：

```python
from data_sources.tencent_technical import fetch_kline, fetch_kline_with_indicators

raw = fetch_kline("600519", k_type="day", num=120)
with_indicators = fetch_kline_with_indicators("600519", k_type="day", num=120)
```

兼容旧脚本路径的 CLI 调试方式：

```bash
python skills/data/tencent_technical/scripts/fetch_kline.py --stock_code 600519 --k_type day --num 120
```

## 1. 适用范围

所属小组：开发3组（数据）

适用任务：
- 从腾讯财经（ifzq.gtimg.cn）获取指定个股的 K线行情数据（OHLCV）
- 支持市场：A股（上交所/深交所）、港股、美股
- 支持日K、周K、月K、1/5/15/30/60分钟K线（前复权）
- 基于K线原始数据计算技术指标：MA均线、BOLL布林带、RSI相对强弱指数
- 提供结构化 JSON 输出，供技术分析 Agent 消费

边界说明：
- 本 Skill **只负责数据获取和技术指标计算**，不做任何交易判断
- 腾讯 API 只返回 OHLCV 原始数据，MA/BOLL/RSI 为本地计算
- API 为非官方公开接口，可能随时变更，建议控制请求频率
- 日K最多获取 640 条，分钟K最多获取 320 条
- 港美股 API 覆盖度可能不及 A 股，部分代码可能无数据

## 2. 输入材料

### 必填输入

- 股票代码，支持以下格式（大小写不敏感）：

| 市场 | 代码格式 | 示例 |
|------|---------|------|
| A股上交所 | 6位数字（6开头），可选 sh 前缀 | `600519`、`sh688981` |
| A股深交所 | 6位数字（0/3开头），可选 sz 前缀 | `000001`、`sz300750` |
| 港股 | 5位以内数字，可选 hk 前缀 | `00700`、`hk09988` |
| 美股 | 字母 ticker，可选 us 前缀 | `AAPL`、`usTSLA` |

- K线周期（day/week/month/m1/m5/m15/m30/m60）

### 可选输入

- 获取数量（默认 120，日K最多 640，分钟K最多 320）
- 技术指标选择（默认 ma,boll,rsi，逗号分隔）

### 缺失处理

- 如果股票代码无法识别，输出 `status: "error"`，`kline: []`
- 如果 API 请求失败，输出 `status: "error"`，附错误信息
- 如果 K线数据不足计算某个指标，对应字段输出 `null`

## 3. 分析步骤

1. 标准化股票代码（自动识别 A股/港股/美股 → sh/sz/hk/us 前缀格式）
2. 根据 K线周期选择对应 API 端点
3. 调用腾讯财经 API 获取 OHLCV 原始数据
4. 解析响应，提取 date/open/close/high/low/volume
5. 按 indicators 参数计算技术指标：
   - MA：收盘价的 N 周期滑动平均
   - BOLL：MA20 ± 2×标准差
   - RSI：基于涨跌幅的相对强弱指数
6. 输出结构化 JSON

## 4. 判断规则

本 Skill 为数据获取层，不产出交易方向判断。技术指标的计算规则如下：

- **MA5/MA10/MA20/MA60**：数据不足 N 条时输出 null
- **BOLL(20,2σ)**：至少需要 20 条数据，不足时 upper/middle/lower 均为 null
- **RSI6/RSI12/RSI24**：至少需要 N+1 条数据（计算涨跌幅），不足时输出 null
- **成交量**：输出统一为 A 股常用口径“手”。腾讯日 K 对科创板 `sh688***` 原始字段可能返回“股”，运行时会先除以 100 归一为“手”，并保留 `volume_raw` / `volume_raw_unit` 便于排查口径。

## 5. 标准输出

示例输出（贵州茅台 600519，日K，30条）：

```json
{
  "status": "success",
  "stock_code": "sh600519",
  "k_type": "day",
  "fetch_time": "2025-05-03T17:00:00",
  "total": 30,
  "indicators": ["ma", "boll", "rsi"],
  "kline": [
    {
      "date": "2025-04-25",
      "open": 1600.0,
      "close": 1610.5,
      "high": 1620.0,
      "low": 1595.0,
      "volume": 230030416,
      "ma": {
        "ma5": 1605.0,
        "ma10": 1598.0,
        "ma20": 1590.0,
        "ma60": 1550.0
      },
      "boll": {
        "upper": 1650.0,
        "middle": 1600.0,
        "lower": 1550.0
      },
      "rsi": {
        "rsi6": 65.2,
        "rsi12": 58.7,
        "rsi14": 56.1,
        "rsi24": 55.3
      }
    }
  ]
}
```

错误输出：

```json
{
  "status": "error",
  "stock_code": "600519",
  "error": "requests 库未安装",
  "kline": []
}
```

## 6. 技术指标计算公式

### MA（简单移动平均）

```
MA(N) = 最近N个周期收盘价之和 / N
```

计算周期：MA5、MA10、MA20、MA60

### BOLL（布林带）

```
中轨 = MA(20)
标准差 = 最近20个周期收盘价的总体标准差
上轨 = 中轨 + 2 × 标准差
下轨 = 中轨 - 2 × 标准差
```

### RSI（相对强弱指数）

```
涨幅 = max(收盘价变化, 0)
跌幅 = max(-收盘价变化, 0)
平均涨幅 = N周期涨幅的简单平均
平均跌幅 = N周期跌幅的简单平均
RSI(N) = 100 × 平均涨幅 / (平均涨幅 + 平均跌幅)
```

计算周期：RSI6、RSI12、RSI14、RSI24

## 7. 依赖

- Python 3.8+
- requests 库（HTTP 请求）
- json（标准库，响应解析）

## 8. 关联 Skill

本 Skill 为数据获取层，其输出供以下分析层 Skill 消费：
- **技术指标分析 Skill**（skills/technical/）：趋势判定、量价分析、动量信号
- **资金流向分析 Skill**（skills/fundflow/）：量价配合分析

## 9. 测试样例

### A股正面样例：数据充足

输入：stock_code=600519, k_type=day, num=60
预期：status=success，kline 有 60 条，最后一条的 ma/boll/rsi 均有值

### 港股正面样例

输入：stock_code=00700, k_type=day, num=120
预期：status=success，代码标准化为 hk00700，kline 有数据

### 美股正面样例

输入：stock_code=AAPL, k_type=day, num=120
预期：status=success，代码标准化为 usaapl，kline 有数据（取决于 API 覆盖）

### 边界样例：数据不足

输入：stock_code=600519, k_type=day, num=10
预期：status=success，kline 有 10 条，ma5 有值但 ma60 为 null，boll 为 null

### 错误样例：无效代码

输入：stock_code=999999
预期：status=error，kline=[]

### 已有前缀样例

输入：stock_code=hk00700, k_type=week, num=50
预期：status=success，保留 hk00700 前缀，返回周K数据
