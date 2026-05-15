# 宏观分析 Skill（7层流水线）

基于五大底层公理，通过**7层流水线**（Layer 0 → Layer 5，新增Layer 4.5反身性与元认知层）的标准化分析体系，聚焦AI科技主线，从双经济体追踪、状态识别、周期定位、枢纽变量分析、市场定价提取、预期差信号引擎、反身性与元认知修正，到最终的 **Beta+Alpha 资产配置**，构建从宏观状态识别到资产配置的完整信号生产线。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                      agents/macro/ Agent                        │
│  (负责数据获取、按顺序调用各层、汇总输出Signal)                   │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  Layer 0-2    │   │  Layer 2.5-4  │   │  Layer 4.5-5  │
│  (数值计算)   │   │  (智能分析)   │   │  (配置输出)   │
└───────────────┘   └───────────────┘   └───────────────┘
```

## 目录结构

```
skills/macro/
├── README.md                      # 本文件
├── utils/                        # 共享工具模块
│   ├── __init__.py
│   ├── constants.py              # 权重表、阈值常量
│   └── signal_utils.py           # Signal构建工具
├── layer0_tracking/              # Layer 0：双经济体追踪
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer1_cai_fci/              # Layer 1：CAI/FCI计算（纯数值）
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer2_cycle_positioning/      # Layer 2：周期定位
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer2_5_hub_variable/        # Layer 2.5：枢纽变量分析
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer3_market_pricing/         # Layer 3：市场定价提取
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer4_expected_diff/          # Layer 4：预期差信号引擎
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
├── layer4_5_reflexivity/          # Layer 4.5：反身性与元认知
│   ├── SKILL.md
│   └── scripts/
│       ├── __init__.py
│       └── analyzer.py
└── layer5_asset_allocation/       # Layer 5：资产配置
    ├── SKILL.md
    └── scripts/
        ├── __init__.py
        └── analyzer.py
```

## 各层职责

| 层 | 名称 | 执行方式 | 核心功能 |
|----|------|----------|----------|
| Layer 0 | 双经济体追踪 | 智能分析 | 追踪中美五大维度、6条传导通道 |
| Layer 1 | CAI/FCI计算 | 纯数值 | 计算中美活动指数、金融条件指数 |
| Layer 2 | 周期定位 | 混合 | 4象限定位、政策维度调节 |
| Layer 2.5 | 枢纽变量 | 智能分析 | 汇率/大宗商品传导分析 |
| Layer 3 | 市场定价 | 混合 | 从价格反推隐含预期 |
| Layer 4 | 预期差引擎 | 智能分析 | 计算"实际vs定价"偏差 |
| Layer 4.5 | 反身性 | 混合 | 信号拥挤度、范式稳定性 |
| Layer 5 | 资产配置 | 混合 | Beta+Alpha权重输出 |

## 数据获取

数据获取由 `agents/macro/agent.py` 负责，当前使用**伪代码+模拟数据**预留。

详细输入规范见：[skills/macro/_workspace/spec/input_data_spec.md](../_workspace/spec/input_data_spec.md)

## 使用方式

### 1. Agent调用流程

```python
# agents/macro/agent.py

from skills.macro.layer0_tracking.scripts.analyzer import analyze_bilateral_tracking
from skills.macro.layer1_cai_fci.scripts.analyzer import analyze_cai_fci
# ...

class MacroAgent(BaseAgent):
    
    def analyze(self, query: str) -> Signal:
        # 1. 获取数据（伪代码）
        data = self.fetch_macro_data()
        
        # 2. 按顺序调用各层
        layer0 = analyze_bilateral_tracking(...)
        layer1 = analyze_cai_fci(...)
        layer2 = analyze_cycle_positioning(...)
        # ...
        
        # 3. 返回最终Signal
        return final_signal
```

### 2. 单独使用某层

```python
from skills.macro.layer1_cai_fci.scripts.analyzer import analyze_cai_fci

result = analyze_cai_fci(
    china_indicators={"nbs_manufacturing_pmi": 50.2},
    us_indicators={"ism_manufacturing_pmi": 52.0},
)
```

## 开发进度

- [x] 第一阶段：工具模块（utils/constants.py, utils/signal_utils.py）
- [x] 第二阶段：Layer 0-2
- [x] 第三阶段：Layer 2.5-4
- [x] 第四阶段：Layer 4.5-5
- [ ] 第五阶段：测试与集成

## 相关文档

- [需求文档](./_workspace/spec/requirement.md)
- [输入数据规范](./_workspace/spec/input_data_spec.md)
- [框架手册](./_workspace/spec/framework_full.md)（如已转换为Markdown）
- [待解决问题清单](./_workspace/spec/框架待解决问题清单.md)

## 维护人

专家4组（宏观方向）

## 版本历史

- V0.1 (2026-05-16): 初始版本，实现7层流水线骨架
