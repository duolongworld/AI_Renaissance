# Bug修复记录 — Hermes Agent 集成

## Bug 1: validate_data.py — 数字字段字符串兼容

**文件**: `scripts/validate_data.py`  
**位置**: `_validate_data_quality()` 方法，约 L138-149  
**现象**: `TypeError: '>' not supported between instances of 'str' and 'int'`  
**根因**: `revenue_growth`、`gross_margin` 等字段填入非数字值时，直接参与算术比较  
**修复**: 用 `try/except` 包裹，`float()` 转换失败时跳过比较

## Bug 2: pipeline.py — 生命周期判定数字格式化

**文件**: `core/pipeline.py`  
**位置**: `determine_lifecycle_from_real_data()` 函数，约 L155-186  
**现象**: `ValueError: Unknown format code 'f' for object of type 'str'`  
**根因**: 多处 `f"{rev_growth:.0f}%"` 格式化假设值是数字  
**修复**: 添加 `_safe_num()` 辅助函数，非数字值时用字符串展示替代数字格式化

## 正确数据填充规范

**缺失数值字段应填 `null`，非 `"数据缺失"`：**

```json
// ✅ 正确
"revenue_growth": null,
"revenue_growth_source": "需补充: Q1 2026 财报数据"

// ❌ 错误（会导致 pipeline 崩溃）
"revenue_growth": "数据缺失",
```

**定性字段可保留字符串**（如 `order_backlog`、`capex_plan`）。

## 修复后验证

修复后 `_real_data.json` 可同时包含数字字段（参与算术运算）和字符串字段（纯展示），pipeline 正常完成全流程：

```
Step 2: 生命周期: 成长期
Step 3: 拐点状态: 拐点确认
Step 4: System B 类型: 混合型
V4.5 流水线完成 ✅
```

## Bug 3: system_a.py — `search_broker_reports` confidence 未初始化

**文件**: `core/system_a.py`  
**位置**: `search_broker_reports()` 函数，约 L707-711  
**现象**: `UnboundLocalError: cannot access local variable 'confidence' where it is not associated with a value`  
**影响**: L2 数据获取全部静默失败，降级到 L3，导致 ABF 载板 demo 断言失败  
**根因**: `confidence -= 15` 在赋值前使用  
**修复**: 添加 `confidence = 80` 初始化

## Bug 4: system_b.py — demo 输出 KeyError

**文件**: `core/system_b.py`  
**位置**: `__main__` demo 块，约 L540, L565  
**现象**: `KeyError: 'key_features'` — `get_stock_type_description()` 返回 `key_metric`，demo 代码用了旧 key 名  
**修复**: 改为 `desc.get('key_features', desc.get('key_metric', ''))` 兼容两种 key

## Bug 5: system_a.py — 数据防火墙公司名检测过窄

**文件**: `core/system_a.py`  
**位置**: `COMPANY_NAME_SUFFIXES` 元组 + `COMPANY_SUFFIX_PATTERN` 正则，约 L1345-1368  
**现象**: 测试 5/6 失败 — "某公司"、"某光模块公司" 未被拦截  
**根因**: ① `COMPANY_NAME_SUFFIXES` 缺少通用后缀 "公司"；② 正则 `[\u4e00-\u9fff]{2,}` 要求至少 2 中文字符在 suffix 前，无法匹配 "某公司"（仅 1 字符）  
**修复**: ① 添加 "公司" 到后缀列表；② 正则改为 `{1,}`

## Bug 6: pipeline.py — lazy import 缺少 `core.` 前缀

**文件**: `core/pipeline.py`  
**位置**: `run_pipeline()` 函数，约 L728, L760  
**现象**: 未配置 preset 或数据缺失较多时，`from auto_detect_preset import ...` / `from data_collection_guide import ...` 失败  
**根因**: `sys.path` 添加的是 skill 根目录（`SCRIPT_DIR`），文件在 `core/` 子目录下  
**修复**: 改为 `from core.auto_detect_preset import ...` / `from core.data_collection_guide import ...`

## Bug 7: SKILL.md 文件结构过时

**文件**: `SKILL.md`  
**位置**: 第 8 节文件结构说明  
**现象**: 列出不存在的 `_real_data.json` 文件（数据已重组为 `data/mappings/` + `data/presets/`）  
**修复**: 更新为实际文件结构，补充 `industry-benchmark-database.yaml`、`stock-to-industry-mapping.json` 等新增文件

## Bug 8: references/V4.5-框架结构.md 被误标记 HISTORICAL

**文件**: `references/V4.5-框架结构-HISTORICAL.md`  
**现象**: SKILL.md 引用的文件被重命名添加 HISTORICAL 后缀  
**修复**: 还原为 `references/V4.5-框架结构.md`
