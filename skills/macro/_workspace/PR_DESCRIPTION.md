# PR: Macro数据管道收尾 — Token安全化 + 语法修复 + 多时点验证

## 类型
- [x] 安全改进
- [x] Bug修复
- [x] 功能完善

## 做了什么

### 1. FRED API Token 安全化
- 移除 `data_sources/macro_data.py` 中硬编码的FRED API key
- 集成 `python-dotenv`，通过 `.env` 文件 + 环境变量 `FRED_API_KEY` 读取
- 创建 `.env.example` 模板文件
- `.env` 已在 `.gitignore` 中排除，确保不进入仓库

### 2. 修复 macro_data.py 语法错误
- 修复14处方法签名中 docstring 错位导致的语法错误（缺少 `):`）
- 修复多处函数调用缺失闭合括号（`stock_margin_sse`, `bond_local_government_issue_cninfo`, `forex_hist_em`, `bond_china_close_return` 等）
- 修复 lambda 表达式和 `round()` 调用括号问题
- 修复 global_pmi 计算 `round()` 和 computation 字段括号问题
- 修复 `logger.info()` 缺失闭合括号
- 修复孤立的冗余括号

### 3. akshare API 兼容性检查
- 检测到6个 akshare 函数在当前版本中已移除：
  - `macro_china_market_equilibrator` → 降级到各专用API（均可用）
  - `macro_china_caixin_manufacturing_pmi` → 无替代，fallback
  - `futures_index_hist`, `index_nh_hist` → 无替代
  - `index_value_hist_funddb` → 无替代
  - `macro_china_mlf_rate` → 已有LPR降级方案
- 已验证32个核心 akshare 函数可用

### 4. 多时点框架验证
运行4个历史时点的完整pipeline（数据采集→Agent分析）：
| 日期 | 倾向 | 置信度 | 字段数 | 实时覆盖率 |
|------|------|--------|--------|-----------|
| 2026-06-01 | bearish | 85% | 59 | ~65% |
| 2026-03-01 | bearish | 85% | 37 | ~14% |
| 2025-06-01 | neutral | 85% | 62 | ~68% |
| 2021-06-01 | bearish | 85% | 92 | ~77% |

## 如何测试
1. 复制 `.env.example` 为 `.env`，填入 FRED API key
2. `python tests/run_macro_batch.py T0 2026-06-01`
3. 验证输出 JSON 中 direction/confidence/reasoning 字段完整

## 影响范围
- `data_sources/macro_data.py` — 语法修复 + Token安全化
- `.env.example` — 新增模板文件
- `tests/run_macro_5dates.py` — 新增5时点批跑脚本
- `tests/_batch_results/macro_progress_final.html` — 进度同步报告

## Checklist
- [x] FRED key不再硬编码
- [x] .env不进入仓库
- [x] 语法错误全部修复
- [x] 多时点框架运行通过
- [x] 进度HTML报告生成
- [x] 推理链完整可追溯
