# Pipeline 指南

## 9 步流水线详解

Industrial Sentinel V4.4 的核心执行流程，输入股票代码即可输出完整分析报告。

```
Input: 股票代码/名称
  │
  ▼ Step 1: 股票-行业映射
  │   输入: 688313.SH / 仕佳光子
  │   输出: 命中行业、产业链位置、preset模板
  │
  ▼ Step 2: 行业数据获取 (L1→L4 降级)
  │   输出: 5 个核心指标 + 置信度 + 来源层级
  │
  ▼ Step 3: 数据防火墙校验
  │   输出: 清洗后的纯行业级字段（禁止公司特定数据）
  │
  ▼ Step 4: 五态拐点判定
  │   输出: state_name + color + confidence
  │
  ▼ Step 5: 产业拐点评分 (V4.3)
  │   输出: 0-100 分 + 五级等级
  │
  ▼ Step 6: System B 自适应评分 (≥55 分激活)
  │   输出: stock_type + adaptive_weights + conviction_grade
  │
  ▼ Step 7: 交易计划生成
  │   输出: 三阶段止盈 + 硬止损规则
  │
  ▼ Step 8: HTML 仪表盘注入
  │   输出: 完整报告文件
  │
  ▼ Step 9: 输出文件路径
```

## System B 激活规则

| System A 评分 | 拐点状态 | System B | 说明 |
|--------------|---------|----------|------|
| ≥ 55 分 | 拐点初期 / 拐点确认 | ✅ 激活 | 输出个股分析 + 交易计划 |
| < 55 分 | 任意 | ❌ 休眠 | 输出「行业景气度不足，个股分析跳过」 |

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
| `无法识别股票 'xxx'` | 映射表未命中 | 检查 `data/mappings/stock-to-industry-optical.json` |
| 产业链结构缺失 | preset 未加载 | 确认 `--preset` 参数或 JSON 中 `preset` 字段 |
| HTML 生成失败 | 模板文件缺失 | 确认 `templates/pipeline-output.html` 存在 |
| System B 未激活 | 数据不足 | 补充 `industry` + `revenue_growth` + `rd_ratio` 字段 |

## 测试

```bash
python3 tests/test_pipeline.py
```

验证项：
1. HTML 文件生成（>5000 字节）
2. 产业链结构卡片
3. System A：生命周期判定 + 拐点状态（五态模型，无评分）
4. System B：个股类型判定（无交易计划/无仓位建议）
5. 数据溯源表
6. 执行时间 < 60 秒

## 与其他触发方式的关系

- 流水线是 V4.4 的**后台执行引擎**，不改变现有 `/景气度` 触发词
- 当前阶段：手动执行 `./run.sh <代码>`，生成 HTML 后发给用户
- 未来可将触发词直接对接 `run.sh` 或 `pipeline.py`
