---
name: eastmoney-guba
description: 东方财富股吧帖子数据契约（标题、正文、阅读数、回复数、发布时间）。真实抓取逻辑在 data_sources/eastmoney_guba.py，本 Skill 说明输入参数、输出格式和使用边界。
owner_group: 开发3组（数据）
domain: data
status: draft
---

# 东方财富股吧数据契约 Skill

## 1. 适用范围

所属小组：开发3组（数据）

适用任务：
- 描述从东方财富股吧（guba.eastmoney.com）获取指定个股帖子列表所需的数据契约
- 提供结构化帖子数据（标题、正文、阅读数、回复数、发布时间等），供上游情绪分析 Skill 使用
- 支持热门帖子和最新帖子两种列表
- 热门帖子可额外抓取正文内容

边界说明：
- 本 Skill **只负责说明数据契约**，不做任何情绪分析或判断
- 真实抓取逻辑由 `data_sources/eastmoney_guba.py` 中的 `EastMoneyGubaDataSource.get_posts()` 执行
- 数据源为东方财富股吧公开页面，用户偏散户，存在数据代表性偏差
- 爬取受反爬策略影响，可能偶尔失败或返回不完整数据
- 本 Skill 不处理限流/代理，调用方需自行处理大规模抓取场景

## 2. 输入参数

### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| stock_code | string | 股票代码（6位数字，支持带 SH/SZ 前缀） | "600519"、"SZ300757" |
| pages | int | 每种列表（热门/最新）抓取的页数 | 2 |

### 可选参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| fetch_content | bool | true | 是否为热门帖子抓取正文 |
| timeout | int | 10 | 单次请求超时（秒） |

## 3. 输出格式

返回结构化的帖子列表：

```json
{
  "status": "success",
  "stock_code": "600519",
  "fetch_time": "2025-05-03T17:00:00",
  "total_posts": 284,
  "posts": [
    {
      "post_id": "1234567890",
      "title": "茅台要起飞了",
      "author": "股友ABC",
      "reads": 5230,
      "replies": 42,
      "post_time": "05-03 14:30",
      "url": "https://guba.eastmoney.com/news,600519,1234567890.html",
      "source_type": "hot",
      "content": "今天放量突破，主力资金进场..."
    },
    {
      "post_id": "9876543210",
      "title": "跌吧跌吧",
      "author": "股友XYZ",
      "reads": 120,
      "replies": 3,
      "post_time": "05-03 15:20",
      "url": "https://guba.eastmoney.com/news,600519,9876543210.html",
      "source_type": "latest",
      "content": ""
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| post_id | string | 帖子唯一ID |
| title | string | 帖子标题 |
| author | string | 作者昵称 |
| reads | int | 阅读数 |
| replies | int | 回复数 |
| post_time | string | 发布时间（格式 MM-DD HH:mm） |
| url | string | 帖子完整URL |
| source_type | string | "hot"（热门帖子）或 "latest"（最新帖子） |
| content | string | 帖子正文（仅热门帖子且 fetch_content=true 时抓取，最新帖子为空串） |

### 错误输出

```json
{
  "status": "error",
  "stock_code": "600519",
  "error": "requests 库未安装",
  "posts": []
}
```

## 4. 数据获取流程

1. **标准化股票代码**：去除 SH/SZ 前缀，统一为6位数字
2. **抓取热门帖子列表**：访问 `guba.eastmoney.com/list,{code},99_{page}.html`，解析帖子标题、作者、阅读数、回复数、发布时间
3. **抓取最新帖子列表**：访问 `guba.eastmoney.com/list,{code}_{page}.html`，同上解析
4. **去重**：基于 post_id 去重（热门和最新列表可能有重叠）
5. **抓取正文**（可选）：对 source_type="hot" 的帖子，逐条抓取正文内容，截取前500字
6. **返回结构化数据**

## 5. 反爬注意事项

- 使用标准浏览器 User-Agent
- 设置 Referer 为 `https://guba.eastmoney.com/`
- 单次请求间隔建议 ≥0.5s
- 单次抓取建议不超过 5 页（100条）
- 如遇频繁失败，自动降级（减少页数或跳过正文抓取）

## 6. 依赖

- Python 3.8+
- requests 库
- re（正则表达式，用于HTML解析）

## 7. 关联 Skill

本 Skill 为数据契约层，其输出供以下分析层 Skill 消费：
- **market_emotion_discovery**（skills/news/market_emotion_discovery）：市场情绪极端发现，消费本 Skill 提供的帖子数据进行情绪分析
