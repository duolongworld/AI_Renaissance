# 样例

这个目录存放本地开发和联调用的手动样例。

新成员可以先从这里运行示例，观察 Agent 当前能否加载、执行并返回标准信号。

## 和 `main.py` 的区别

项目根目录的 `main.py` 是主流程入口：注册专家 Agent、收集 `Signal`、进入仲裁，并输出最终分析结果。

`samples/agent_run_check_sample.py` 是本地运行检查样例：逐个运行 Agent，只展示每个 Agent 的运行状态和 `Signal` 摘要，不做仲裁，也不输出最终决策。

简单说：

- 看系统最终结果，运行 `main.py`
- 看每个 Agent 当前接入状态，运行这个样例

## Agent 运行检查样例

`agent_run_check_sample.py` 会逐个运行指定专家 Agent，并打印简洁的 `Signal` 摘要。

`Signal` 是 Agent 返回给系统的标准信号对象。

首次运行前，先在项目根目录安装依赖：

```powershell
pip install -r requirements.txt
```

运行全部专家 Agent：

```powershell
python samples\agent_run_check_sample.py --stock 600519
```

一次运行输出示例：

```text
Agent 运行检查样例
股票代码: 600519
检查对象: 财务(financial), 技术(technical), 资金(fundflow), 宏观(macro), 行业(industry), 舆情(news), 风险(risk)
说明: 只检查 Agent 运行状态和 Signal 摘要，不做仲裁或最终决策

Agent            运行状态     实现状态          耗时 信号类型            方向                  置信度  推理摘要
------------------------------------------------------------------------------------------------------------------------
财务(financial)    成功       待实现        0.00s 财务(financial)   -                     -  财务分析 Agent 待实现
技术(technical)    成功       待实现        0.00s 技术(technical)   -                     -  技术指标 Agent 待实现
资金(fundflow)     成功       待实现        0.00s 资金(fundflow)    -                     -  资金流向 Agent 待实现
宏观(macro)        成功       待实现        0.00s 宏观(macro)       -                     -  宏观周期 Agent 待实现
行业(industry)     成功       待实现        0.00s 行业(industry)    -                     -  行业景气 Agent 待实现
舆情(news)         成功       已实现        6.72s 舆情(news)        中性(neutral)         38%  基于帖子标题和列表指标，分析 142 条帖子，看多 19 条，看空 15 条，中性 108 条
风险(risk)         成功       待实现        0.00s 风险(risk)        -                     -  风险预警 Agent 待实现

汇总: 成功=7, 失败=0, 无效=0
```

运行指定 Agent：

```powershell
python samples\agent_run_check_sample.py --stock 600519 --agents financial,news,risk
```

可用的 Agent key 包括：`financial`、`technical`、`fundflow`、`macro`、`industry`、`news`、`risk`。

这个样例会直接运行当前 Agent 实现。为避免本地联调卡住，脚本内部会使用本地联调配置。

运行后重点看三件事：

- `运行状态`：Agent 是否能被加载、执行，并返回 `Signal`
- `实现状态`：Agent 是已有实现，还是仍然待实现
- `方向` 和 `置信度`：只看 `已实现` 的行；`待实现` 的行会显示为 `-`

`运行状态=成功` 不代表这个 Agent 已经完成业务分析，只代表它能跑起来并返回标准信号。

显示 Agent 日志：

```powershell
python samples\agent_run_check_sample.py --stock 600519 --verbose
```

这个脚本只用于本地观察和联调，不承担仲裁、决策或正式运行入口职责。
