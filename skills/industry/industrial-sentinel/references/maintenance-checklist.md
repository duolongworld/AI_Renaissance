# Industrial Sentinel 维护检查清单

> 每次发布新版本或接收外部 PR 时必查。基于 V4.5 上线审查实践总结。

---

## 一、代码级检查

### 1.1 变量初始化
```python
# ❌ 常见错误：变量未初始化就做运算
if dispersion > 30:
    confidence -= 15   # UnboundLocalError!

# ✅ 必须先赋值
confidence = 80
if dispersion > 30:
    confidence -= 15
```
**检查方法**：`grep -n " -= \| += " core/*.py | grep -v "= "` 查找所有自减/自增操作，确认变量已在前文初始化。

### 1.2 import 路径
```python
# ❌ pipeline.py 内的懒加载 import 容易缺 core. 前缀
from auto_detect_preset import ...      # 炸
from data_collection_guide import ...   # 炸

# ✅ 完整路径
from core.auto_detect_preset import ...
from core.data_collection_guide import ...
```
**检查方法**：`grep -n "from [a-z].*import" core/pipeline.py`，排除 stdlib 和 core. 前缀的，其余全可疑。

### 1.3 dict key 一致性
```python
# ❌ get_stock_type_description 返回 {"key_metric": ...}
# 但 demo 代码用 desc['key_features'] → KeyError
```
**检查方法**：运行全部测试，grep 所有 `['xxx']` 访问确认 key 存在。

### 1.4 正则模式覆盖
```python
# ❌ COMPANY_SUFFIX_PATTERN 用 {2,} 匹配不到"某公司"（只有1个中文字符）
# ✅ 改为 {1,}
```
**检查方法**：运行 system_a 的数据防火墙测试（7 个用例必须全过）。

---

## 二、文档级检查

### 2.1 SKILL.md 与实际文件一致性
```bash
# SKILL.md 列出的文件必须全部存在
for f in $(从SKILL.md提取); do [ -f "$f" ] || echo "MISSING: $f"; done
```

### 2.2 README.md 完整性
- [ ] 安装命令可一键执行（clone + run）
- [ ] 核心设计理念在前 3 屏可见（不要埋太深）
- [ ] 支持的产业链列表与 `references/preset-chains/` 一致
- [ ] git clone URL 不是 `yourname`

### 2.3 .gitignore 覆盖
必须排除：
- `data/*_real_data.json`（用户个人数据）
- `data/*_collection_tasks.json`（自动生成）
- `reports/*.html`（运行产物）
- `.bak*/`（备份目录）

---

## 三、测试级检查

```bash
# 必须全部通过
python3 tests/test_system_b.py    # 个股类型判定 6 用例
python3 tests/test_system_a.py    # 数据防火墙 7 用例 + 降级链
python3 tests/test_pipeline.py    # 端到端 8 用例

# 确保 run.sh 可执行
./run.sh 002916.SZ                # 应生成 HTML 报告
```

---

## 四、依赖检查

```bash
# 框架宣称零外部依赖，确认无遗漏
grep -r "^import \|^from " core/ scripts/ --include="*.py" \
  | grep -v "from core\|from scripts\|import json\|import re\|import os\|import sys\|import logging\|import math\|import copy\|import yaml\|import csv\|import io\|import time\|import enum\|import subprocess\|import argparse\|import pathlib\|from pathlib\|import datetime\|from datetime\|from typing\|import runpy\|import shutil\|from collections\|import textwrap\|import warnings\|import base64\|import hashlib\|import itertools\|import functools\|from dataclasses\|from enum"
```

---

## 五、设计原则（不可违背）

1. **框架不绑数据源**：代码中不得出现硬编码的外部 API URL 或固定数据抓取逻辑。数据获取由 AI Agent 完成。
2. **结论可审计**：所有判定条件必须透明可查（阈值、规则、决策树）。
3. **零外部 pip 依赖**：核心框架仅用 Python 标准库。
4. **数据必溯源**：所有数据点必须带 source + date。
