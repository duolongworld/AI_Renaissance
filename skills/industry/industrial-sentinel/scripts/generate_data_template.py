#!/usr/bin/env python3
"""
Industrial Sentinel V4.5 — 数据模板生成器

用法:
    python scripts/generate_data_template.py <stock_code> [options]

示例:
    python scripts/generate_data_template.py 002916.SZ --industry PCB --position "中游 — PCB+IC载板"
    python scripts/generate_data_template.py AXTI.US --industry "Compound Semiconductor" --position "上游 — 衬底"

功能:
    为新标的生成标准化的 real_data.json 模板，包含所有必要字段。
    生成的模板中，数值字段留空或标记为「数据缺失」，来源字段标注待补充。
    对方AI使用任意搜索工具（web_search/kimi_search/serpapi等）搜索数据，填入模板即可。
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / "data"


def generate_template(stock_code: str, stock_name: str, industry: str,
                    sub_sector: str, chain_position: str) -> dict:
    """生成标准化数据模板（V4.5 方法论框架版）
    
    重要说明：
    本框架是方法论，不是黑箱工具。你需要用自己的AI/Agent搜索数据填入此模板，
    框架根据填入的数据自动推理产业链景气度、拐点状态和个股类型。
    
    必填 vs 可选字段标注：
    [必填★] — 核心字段，缺失将导致关键分析降级为"数据缺失"
    [推荐☆] — 增强分析精度，缺失时框架用降级策略处理
    [可选]  — 锦上添花，不影响核心分析
    
    推理规则详见：references/methodology-mapping.md
    数据要求详见：references/data-requirements.md
    """
    
    now = datetime.now().strftime("%Y-%m-%d")
    
    template = {
        "_meta": {
            "framework": "Industrial Sentinel V4.5",
            "type": "methodology_framework — 填入数据后自动推理",
            "docs": {
                "data_requirements": "references/data-requirements.md",
                "methodology_mapping": "references/methodology-mapping.md"
            },
            "note": "用你自己的AI/Agent搜索数据填入。每个数字必须标注来源和时间戳。"
        },
        
        # [必填★] 基础信息 — 股票身份、行业归属
        "stock_code": stock_code,
        "stock_name": stock_name,
        "industry": industry,
        "sub_sector": sub_sector,
        "chain_position": chain_position,
        "preset": "",  # [推荐☆] 产业链模板名，空则自动检测
        "data_source": "待补充 — 请通过搜索工具（web_search/kimi_search等）搜索财报和行业研报",
        "generated_at": now,
        
        # [必填★] System A 五态判定信号 — 至少填3项
        "real_signals": {
            "revenue_growth": None,           # [必填★] 营收同比% — 财报
            "revenue_growth_source": "待搜索 — Q1 2026 vs Q1 2025 营收同比（财报）",
            "gross_margin": None,             # [必填★] 毛利率% — 财报
            "gross_margin_source": "待搜索 — 最新季度毛利率（财报）",
            "order_backlog": None,            # [推荐☆] 订单backlog或pipeline — 业绩会/公告
            "order_backlog_source": "待搜索 — 订单backlog或pipeline（财报/业绩会）",
            "capacity_utilization": None,     # [推荐☆] 产能利用率 — 调研/新闻
            "capacity_utilization_source": "待搜索 — 产能利用率或扩产状态（财报/调研）",
            "price_yoy": None,                # [推荐☆] 产品价格同比变化 — 行业新闻/研报
            "price_yoy_source": "待搜索 — 产品价格同比变化（行业新闻/研报）",
            "inventory_days": None,           # [可选] 库存天数 — 财报
            "inventory_days_source": "待搜索 — 库存天数（财报）",
            "capex_plan": None,               # [推荐☆] 扩产计划 — 财报/新闻
            "capex_plan_source": "待搜索 — 扩产计划/资本开支（财报/新闻）",
            "policy_count": 0,                # [可选] 政策数量 — 部委文件/新闻
            "policy_count_source": "待搜索 — 相关政策数量（部委文件/新闻）",
            "net_loss_yoy_improvement": None,  # [可选] 亏损收窄幅度 — 财报
            "net_loss_yoy_improvement_source": "待搜索 — 亏损收窄幅度（财报）"
        },
        
        # [必填★] 行业数据表格 — 至少5项（推荐8项）
        "industry_data": [
            {
                "metric": "Q1 2026 Revenue",    # [必填★]
                "value": "待补充",
                "yoy_change": "待补充",
                "source": "公司财报",
                "source_url": "",
                "source_type": "财报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "Gross Margin",       # [必填★]
                "value": "待补充",
                "yoy_change": "待补充",
                "source": "公司财报",
                "source_url": "",
                "source_type": "财报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "Order Backlog",      # [推荐☆]
                "value": "待补充",
                "yoy_change": "",
                "source": "业绩会/公告",
                "source_url": "",
                "source_type": "财报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "行业需求增速",        # [必填★]
                "value": "待补充",
                "yoy_change": "",
                "source": "行业研报",
                "source_url": "",
                "source_type": "研报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "关键材料价格",        # [推荐☆]
                "value": "待补充",
                "yoy_change": "",
                "source": "行业新闻",
                "source_url": "",
                "source_type": "新闻",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "产能利用率",          # [可选]
                "value": "待补充",
                "yoy_change": "",
                "source": "调研/研报",
                "source_url": "",
                "source_type": "研报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "供需缺口",            # [可选]
                "value": "待补充",
                "yoy_change": "",
                "source": "行业研报",
                "source_url": "",
                "source_type": "研报",
                "date": "",
                "analysis": ""
            },
            {
                "metric": "政策催化剂",          # [可选]
                "value": "待补充",
                "yoy_change": "",
                "source": "部委文件/新闻",
                "source_url": "",
                "source_type": "新闻",
                "date": "",
                "analysis": ""
            }
        ],
        
        # [必填★] 生命周期判定指标 — 至少填3项
        "lifecycle_indicators": [
            {"label": "营收增速", "value": "待补充", "trend": "—", "source": "财报"},
            {"label": "毛利率修复", "value": "待补充", "trend": "—", "source": "财报"},
            {"label": "订单backlog", "value": "待补充", "trend": "—", "source": "财报"},
            {"label": "产能扩张", "value": "待补充", "trend": "—", "source": "新闻"},
            {"label": "行业周期", "value": "待补充", "trend": "—", "source": "研报"}
        ],
        
        # [推荐☆] System B 个股类型判定指标
        "system_b_input": {
            "revenue_growth": None,    # [推荐☆] 营收增速% — 判定成长/周期/价值
            "rd_ratio": None,          # [推荐☆] 研发投入占比% — 判定技术壁垒
            "asset_lightness": None,   # [可选] "轻资产"/"重资产" — 扩张弹性
            "profit_stability": None   # [可选] "稳定盈利"/"波动大" — 盈利质量
        },
        
        # 以下字段在数据搜索后由框架自动推理填充，无需手动填写
        "system_b_type": "待判定 — 框架自动推理",
        "system_b_type_reason": "待搜索营收增速、研发投入、资产模式后，框架自动判定",
        "system_b_core_contradiction": "待搜索后，框架自动分析核心矛盾",
        "system_b_tracking_metrics": ["待补充 — 框架自动提出跟踪指标"],
        "system_b_risks": ["待补充 — 框架自动识别风险"],
        "inflection_logic": "待搜索真实数据后，框架基于信号匹配自动填写"
    }
    
    return template


def save_template(data: dict, force: bool = False) -> Path:
    """保存模板到data目录"""
    code = data["stock_code"]
    filepath = DATA_DIR / f"{code}_real_data.json"
    
    if filepath.exists() and not force:
        print(f"⚠️ 文件已存在: {filepath}")
        print(f"   使用 --force 覆盖，或手动备份")
        return filepath
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 模板已生成: {filepath}")
    return filepath


def print_search_guide(stock_code: str, stock_name: str):
    """打印数据搜索指南"""
    print("\n" + "="*60)
    print(f"📋 数据搜索指南 — {stock_name} ({stock_code})")
    print("="*60)
    print("""
请使用任意搜索工具（web_search/kimi_search/serpapi等）搜索以下数据，填入生成的JSON模板：

【财报数据】
1. "{stock_code} Q1 2026 财报 营收 毛利率"
2. "{stock_code} 2026年 一季度 业绩" 
3. "{stock_name} earnings Q1 2026 revenue gross margin"

【行业数据】
4. "{industry} 行业 2026 市场规模 增长率"
5. "{industry} 产业链 供需缺口 产能利用率"
6. "{industry} 价格趋势 订单 backlog"

【政策/新闻】
7. "{industry} 政策 2026 补贴 准入"
8. "{stock_name} 扩产 产能规划 资本开支"

【System B分析】
9. "{stock_name} 研发投入占比 资产模式"
10. "{stock_name} 竞争格局 客户结构 风险"

填入完成后，再次运行 pipeline 即可生成报告。
""".format(stock_code=stock_code, stock_name=stock_name, industry="该行业"))


def main():
    parser = argparse.ArgumentParser(
        description="生成 Industrial Sentinel V4.5 数据模板"
    )
    parser.add_argument("stock_code", help="股票代码，如 002916.SZ 或 AXTI.US")
    parser.add_argument("--name", "-n", default="", help="股票名称")
    parser.add_argument("--industry", "-i", default="待补充", help="所属行业")
    parser.add_argument("--sub-sector", "-s", default="待补充", help="细分赛道")
    parser.add_argument("--position", "-p", default="待补充", help="产业链位置")
    parser.add_argument("--force", "-f", action="store_true", help="覆盖已存在文件")
    
    args = parser.parse_args()
    
    stock_name = args.name or args.stock_code
    
    # 生成模板
    template = generate_template(
        stock_code=args.stock_code,
        stock_name=stock_name,
        industry=args.industry,
        sub_sector=args.sub_sector,
        chain_position=args.position,
    )
    
    # 保存
    filepath = save_template(template, force=args.force)
    
    # 打印搜索指南
    print_search_guide(args.stock_code, stock_name)
    
    print(f"\n💡 下一步:")
    print(f"   1. 使用搜索工具（web_search/kimi_search等）搜索上述数据")
    print(f"   2. 编辑 {filepath}")
    print(f"   3. 运行: python -c \"from core.pipeline import run_pipeline; run_pipeline('{args.stock_code}')\"")


if __name__ == "__main__":
    main()
