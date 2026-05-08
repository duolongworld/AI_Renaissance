---
name: cninfo
description: 巨潮资讯网(cninfo.com.cn)A 股法定披露公告数据契约 — 年报/季报/中报/三季报/临时公告 PDF + PyMuPDF 全文 Markdown。真实抓取逻辑由独立开源工具 use_cninfo 实现,本仓库通过 data_sources/cninfo.py 适配 CLI 输出。
owner_group: 开发3组(数据)
domain: data
status: draft
---

# 巨潮资讯网公告数据契约 Skill

## 1. 适用范围

所属小组:开发3组(数据)

适用任务:
- 描述从巨潮资讯网(cninfo.com.cn)获取 A 股上市公司法定披露公告所需的数据契约
- 提供两类查询能力:(a) 单股指定财年的定期报告本体(年报/一季报/中报/三季报);(b) 单股时间窗的全部公告列表
- 输出包含 PDF 直链路径 + PyMuPDF 提取的 Markdown 全文,供财务分析/事件追踪/舆情前置等 Skill 消费
- 适合 A 股全市场(沪/深/创业板/科创板/北交所),回溯历史可至 2021 年

边界说明:
- 本 Skill **只描述数据契约**,真实抓取逻辑在外部独立开源工具 [`use_cninfo`](https://github.com/rollysys/use_cninfo)
- 适配薄包装位于 `data_sources/cninfo.py`(`CninfoDataSource`),内部 subprocess 调 `cninfo` CLI 并解析 JSON
- 数据源是法定披露平台,不存在"代表性偏差",但 cninfo 接口 `pageSize` 服务端硬限 30,长时间窗会触发翻页,建议每次窗口 ≤ 1 个月
- 部分 PDF 是扫描件(主要是会计师审计意见 / 内控鉴证),`extracted_pages=0` 时 md 正文为空,本 Skill 不内置 OCR
- 同一份报告可能有 2 条记录(announcementId 不同 PDF 内容相同),需在调用方按 `(stock_code, ann_date, title)` 去重
- 二次访问命中本地缓存(`~/.cache/cninfo/`,可被 `$CNINFO_CACHE_DIR` 覆盖),秒级返回不发网络

## 2. 执行数据源

真实数据获取逻辑位于:

```text
data_sources/cninfo.py   # 薄 shim,subprocess 调 use_cninfo CLI
```

推荐调用方式:

```python
from data_sources import CninfoDataSource

source = CninfoDataSource()

# 拿茅台 2024 年报本体
r = source.get_periodic_report(stock_code="600519", year=2024, kind="annual")

# 拿茅台 2025-04 全月公告(仅列表)
r = source.get_announcements(stock_code="600519", since="2025-04-01", until="2025-04-30")

# 拿茅台 2025-04 全月公告并下载 + 解析全文
r = source.get_announcements(
    stock_code="600519", since="2025-04-01", until="2025-04-30", download=True,
)
```

前置依赖(用户在 Agent 运行环境装好):

```bash
# 必装
git clone https://github.com/rollysys/use_cninfo.git
cd use_cninfo && pip install -e .

# 可选(启用 search 标签过滤,本契约暂未暴露,后续扩展)
git clone https://github.com/rollysys/announcement_filter.git
cd announcement_filter && pip install -e .
```

`cninfo` 命令需要在 PATH 中(`pip install -e .` 自动配置)。`CninfoDataSource` 初始化时若未找到 CLI 会输出 warning,所有方法返回 `status: error` 并在 `error` 字段提示安装命令。

## 3. 输入参数

### `get_periodic_report(stock_code, year, kind, force=False)`

#### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|---|---|---|---|
| stock_code | string | 6 位股票代码(无后缀) | `"600519"` |
| year | int | 报告所属财年 | `2024` |
| kind | string | 报告类型:`annual` / `q1` / `h1` / `q3` | `"annual"` |

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| force | bool | `False` | 忽略本地缓存重新下载并重新解析 |

### `get_announcements(stock_code, since, until, download=False)`

#### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|---|---|---|---|
| stock_code | string | 6 位股票代码 | `"600519"` |
| since | string | 起始日期 `YYYY-MM-DD` | `"2025-04-01"` |
| until | string | 截止日期 `YYYY-MM-DD` | `"2025-04-30"` |

#### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| download | bool | `False` | `True` 时下载并 PyMuPDF 解析每份 PDF |

## 4. 输出格式

### `get_periodic_report` 成功

```json
{
  "status": "success",
  "stock_code": "600519",
  "fetch_time": "2026-05-04T17:30:00",
  "report": {
    "ann_id": "1222993920",
    "sec_code": "600519",
    "ts_code": "600519.SH",
    "ann_date": "20250403",
    "title": "贵州茅台2024年年度报告",
    "category": "01010503||010113||010301",
    "pdf_url": "http://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF",
    "pdf_path": "/Users/x/.cache/cninfo/pdf/600519.SH/20250403__1222993920.pdf",
    "md_path":  "/Users/x/.cache/cninfo/md/600519.SH/20250403__1222993920.md",
    "meta_path": "/Users/x/.cache/cninfo/meta/1222993920.json",
    "total_pages": 143,
    "extracted_pages": 143,
    "text_chars": 176373,
    "cache_hit": false
  }
}
```

`md_path` 指向的文件含 YAML frontmatter(`ann_id / ts_code / sec_code / sec_name / ann_date / title / category / source / total_pages / extracted_pages / text_chars`)+ PyMuPDF 提取的全文 Markdown,直接可读。

### `get_announcements` 成功

```json
{
  "status": "success",
  "stock_code": "600519",
  "since": "2025-04-01",
  "until": "2025-04-30",
  "fetch_time": "2026-05-04T17:30:00",
  "total": 18,
  "announcements": [
    {
      "ann_id": "1222993920",
      "sec_code": "600519",
      "ann_date": "20250403",
      "title": "贵州茅台2024年年度报告",
      "adjunct_size_kb": 3542
    }
  ]
}
```

`download=True` 时每条 announcement 额外含 `cache_hit / md_path / pages / text_chars` 字段。

### 失败

```json
{
  "status": "error",
  "stock_code": "600519",
  "error": "..."
}
```

常见 `error`:
- `` `cninfo` 命令未安装。装一下: ... ``
- `cninfo CLI 超时 (120s)`
- `OrgIdNotFound: orgId not found for sec_code=XXX`(代码错 / 已退市 / cninfo 接口变)
- `no annual report body found for ... year=YYYY`(报告期窗口外 / 只有摘要无本体)

## 5. 数据边界

**法定属性**:cninfo 是中国证监会指定的 A 股法定信息披露平台,所有上市公司必须在此披露,无遗漏风险。

**频次限制**:
- cninfo 接口 `pageSize` 服务端硬限 30,长时间窗会自动翻页(本工具内部已处理)
- 单页响应 ~0.2-0.3s,建议调用方控制窗口长度避免超时
- 5 次/秒连发实测无限流,但持续大批量建议加 sleep,详见上游 `docs/gotchas.md`

**缓存语义**:
- 默认本地长期缓存(`~/.cache/cninfo/`),pdf + md + meta 三件齐全才算命中
- `force=True` 跳过缓存重新下载
- `cninfo cache prune --older-than 365d` 可手动清理(本契约未暴露,直接命令行)

**已知陷阱**(继承自上游):
- 同一公告可能有 2 条记录,需调用方去重
- 部分 2024-06 前的老 PDF URL 可能 404,失败重试 3 次后跳过
- 部分 PDF 是扫描件,`extracted_pages=0`,md 正文为空但 PDF 已落盘

完整陷阱清单见 [`use_cninfo/docs/gotchas.md`](https://github.com/rollysys/use_cninfo/blob/main/docs/gotchas.md)。

## 6. 调用示例

```python
from data_sources import CninfoDataSource

source = CninfoDataSource()

# 场景 1:为财务分析 Agent 拿茅台 2024 年报全文
r = source.get_periodic_report("600519", 2024, "annual")
if r["status"] == "success":
    md_path = r["report"]["md_path"]
    with open(md_path, encoding="utf-8") as f:
        annual_report_text = f.read()
    # 喂给下游分析 Skill ...

# 场景 2:为事件追踪 Agent 拿最近 30 天的所有公告标题
from datetime import date, timedelta
today = date.today()
r = source.get_announcements(
    "600519",
    since=(today - timedelta(days=30)).isoformat(),
    until=today.isoformat(),
)
titles = [a["title"] for a in r["announcements"]]

# 场景 3:批量预热缓存(下载 + 解析,后续访问秒级)
r = source.get_announcements(
    "600519", since="2025-04-01", until="2025-04-30", download=True,
)
```

## 7. 与已有数据源的关系

| 已有 | 数据 | cninfo 与之关系 |
|---|---|---|
| `EastMoneyDataSource` | 三大表结构化数据(资产负债/利润/现金流) | **互补**。东方财富给数字,cninfo 给原文。年报正文里有"管理层讨论与分析 / 关键审计事项 / 重大合同"等结构化字段无法替代的内容 |
| `EastMoneyGubaDataSource` | 散户帖子(舆情) | **互补**。cninfo 是机构口径(法定披露),股吧是散户口径(情绪) |

cninfo 的典型消费方:
- 财务分析 Agent:直接读年报"管理层讨论与分析"段对账三大表
- 事件追踪 Agent:监听单股近 30 天公告标题,识别减持/重组/关联交易等事件
- 舆情前置 Agent:用 cninfo 公告作为"事实锚",再去股吧看散户对该事件的反应
