# Pipeline 指南

## 执行链路

Industrial Sentinel 有两种使用模式：

- 项目 `IndustryAgent` 模式：返回标准 `Signal` 与结构化 `meta`，不生成 HTML。
- 独立 CLI 模式：`./run.sh` / `core/pipeline.py` 可生成 HTML 报告，供手工调试和演示。

项目接入链路如下：

```
Input: 股票代码/股票名/行业词/preset
  │
  ▼ Step 1: 输入归一化
  │   输出: stock_code / stock_name / industry / preset + 本地 preset 路由
  │
  ▼ Step 2: data_sources 获取数据
  │   输出: industry_signals / peer_basket_signals / company_signals
  │   降级: 实时 provider → 缓存 → preset_only 框架 fallback
  │
  ▼ Step 3: runtime 构建 real_data
  │   输出: 行业级信号优先，同业篮子其次，个股信号只给 System B
  │
  ▼ Step 4: System A
  │   输出: 生命周期 + 五态拐点 + 景气方向
  │
  ▼ Step 5: System B
  │   输出: 个股类型 + adaptive_weights
  │
  ▼ Step 6: Signal
      输出: direction / confidence / reasoning / signals / meta
```

## 降级规则

| 场景 | 行为 |
|------|------|
| 实时 provider 成功 | 使用真实行业/财务数据，写入缓存 |
| provider 失败但缓存存在 | 使用缓存，并在 `meta.data_source` 标记来源 |
| provider 和缓存都失败，但命中 preset | 返回 `preset_only`，低置信度 neutral，`needs_data=True` |
| preset 也未命中 | 返回缺数降级原因，低置信度 neutral |

## System B 边界

System B 只负责个股类型判定（成长/周期/价值/主题/混合）和自适应权重提示，不生成交易计划、仓位建议或止损止盈规则。

## HTML 输出结构

| 区块 | 内容 |
|------|------|
| 产业链结构 | 上/中/下游 + 各环节景气度卡片 |
| System A — 生命周期 | 导入期/成长期/成熟期/衰退期判定 + 论据 |
| System A — 拐点状态 | 五态判定结果（拐点前/初期/确认/晚期/后）+ 监测指标 |
| System B — 个股类型 | 类型识别（成长/周期/价值/主题/混合）+ 论据 |
| 数据溯源表 | 每个数字的来源标注 + 时间戳 + 置信度 |

## 用法

```bash
# Shell 启动器（推荐）
./run.sh 688313.SH
./run.sh 仕佳光子

# 直接调用 Python
python3 core/pipeline.py 688313.SH
```

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `无法识别股票 'xxx'` | preset 路由未命中 | 检查 `core/auto_detect_preset.py` 或补充 `data/mappings/stock-to-preset.json` |
| 产业链结构缺失 | preset 未加载 | 确认 `--preset` 参数或 JSON 中 `preset` 字段 |
| HTML 生成失败 | 模板文件缺失 | 确认 `templates/pipeline-output.html` 存在 |
| System B 未激活 | 数据不足 | 补充 `industry` + `revenue_growth` + `rd_ratio` 字段 |

## 测试

```bash
./.venv/bin/python -m pytest tests/industry -q
```

重点验证：
1. Agent/runtime 路径返回结构化 Signal，不返回 HTML 路径
2. System A 优先使用行业级信号
3. 数据缺失时返回 `needs_data` 和降级原因
4. CLI pipeline 仍可生成 HTML 报告
