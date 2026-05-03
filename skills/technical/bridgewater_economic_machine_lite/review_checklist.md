# Review Checklist

- [ ] SKILL.md 有 YAML front matter
- [ ] 不包含 API key、数据源 registry、抓数脚本要求
- [ ] 明确说明本 Skill 不负责寻找/抓取数据源
- [ ] 输入要求清楚
- [ ] 分析步骤完整
- [ ] 四象限规则清楚
- [ ] 债务周期规则清楚
- [ ] 标准 Signal JSON 符合项目字段
- [ ] signals 是 List[str]，不是对象列表
- [ ] meta 包含 output_version、skill_version、skill_name、owner_group、target、period、time_horizon、risk_level
- [ ] meta.evidence 使用 source_type/source_name/date/metric/value/comparison/note
- [ ] 缺数据时 neutral + 低置信度 + human review
- [ ] 没有个股买卖建议

- [ ] Q1/Q2/Q3/Q4/Mixed/缺失数据样例能通过 `tests/validate_signal_outputs.py`
- [ ] `long_debt_pressure` 等枚举值不超出 SKILL.md 标准输出定义
