#!/usr/bin/env python3
"""
Industrial Sentinel V4.5 — AI数据采集任务生成器

核心功能：
1. 输入产业链类型（preset）或股票代码
2. 读取对应preset YAML
3. 生成结构化AI数据采集任务清单
4. 清单包含：搜索词、来源优先级、必填级别、时效要求、校验规则、回填路径

对方AI拿到任务清单后：
- 按任务逐个搜索数据
- 校验来源和时效
- 按field_path回填到JSON模板
- 缺失字段标注"数据缺失"，不编造
- 完成后运行pipeline自动生成报告

用法：
    python3 core/data_collection_guide.py optical-module
    python3 core/data_collection_guide.py 002916.SZ --output tasks.json
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("collection_guide")

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
REF_DIR = SCRIPT_DIR / "references"
PRESET_DIR = REF_DIR / "preset-chains"
DATA_DIR = SCRIPT_DIR / "data"

# ── 必填/推荐/可选标记 ──
REQUIRED = "★必填"
RECOMMENDED = "☆推荐"
OPTIONAL = "○可选"


def load_preset(preset_name: str) -> Optional[Dict[str, Any]]:
    """加载preset YAML文件（支持子目录层级结构）"""
    path = PRESET_DIR / f"{preset_name}.yaml"
    if not path.exists():
        # 递归搜索子目录（layer1-5结构）
        for subdir in PRESET_DIR.iterdir():
            if subdir.is_dir():
                candidate = subdir / f"{preset_name}.yaml"
                if candidate.exists():
                    path = candidate
                    break
        # 兜底 generic
        if not path.exists():
            path = PRESET_DIR / "generic.yaml"
    if not path.exists():
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error("加载preset失败: %s — %s", path, e)
        return None


def build_search_queries(indicator_name: str, industry_name: str) -> Dict[str, List[str]]:
    """
    基于指标名和行业名，生成多语言搜索词。
    覆盖：财报数据、研报数据、行业新闻、公司公告
    """
    # 中文搜索词
    chinese = [
        f"{industry_name} {indicator_name} 2026",
        f"{industry_name} {indicator_name} 最新数据",
        f"{industry_name} {indicator_name} 同比 环比",
        f"{industry_name} {indicator_name} 财报",
        f"{industry_name} {indicator_name} 研报",
    ]
    # 英文搜索词（标准化）
    english_ind = indicator_name.replace("价格", "price").replace("毛利率", "gross margin") \
        .replace("营收", "revenue").replace("订单", "order").replace("库存", "inventory") \
        .replace("产能", "capacity").replace("交货", "delivery").replace("周期", "cycle")
    english = [
        f"{industry_name} {english_ind} 2026 data",
        f"{industry_name} {english_ind} latest",
        f"{industry_name} {english_ind} report",
    ]
    return {"chinese": chinese, "english": english}


def infer_field_path(indicator_name: str, category: str) -> str:
    """
    推断该指标应该回填到JSON的哪个路径。
    category: barometric / mid_axis / ebb_warning / upstream / midstream / downstream / system_b
    """
    name = indicator_name.strip()
    
    # System A 五态信号
    signal_map = {
        "营收": "real_signals.revenue_growth",
        "收入": "real_signals.revenue_growth",
        "毛利率": "real_signals.gross_margin",
        "毛利": "real_signals.gross_margin",
        "订单": "real_signals.order_backlog",
        "backlog": "real_signals.order_backlog",
        "产能": "real_signals.capacity_utilization",
        "利用率": "real_signals.capacity_utilization",
        "价格": "real_signals.price_yoy",
        "库存": "real_signals.inventory_days",
        "库存天数": "real_signals.inventory_days",
        "资本开支": "real_signals.capex_plan",
        "capex": "real_signals.capex_plan",
        "政策": "real_signals.policy_count",
        "亏损": "real_signals.net_loss_yoy_improvement",
    }
    
    for key, path in signal_map.items():
        if key in name:
            return path
    
    # 行业数据表格
    if category in ("barometric", "upstream"):
        return f"industry_data.{clean_field_name(name)}"
    if category in ("mid_axis", "midstream"):
        return f"industry_data.{clean_field_name(name)}"
    if category in ("ebb_warning", "downstream"):
        return f"industry_data.{clean_field_name(name)}"
    
    # System B
    if category == "system_b":
        sb_map = {
            "研发": "system_b_input.rd_ratio",
            "rd": "system_b_input.rd_ratio",
            "资产": "system_b_input.asset_lightness",
            "盈利": "system_b_input.profit_stability",
            "利润": "system_b_input.profit_stability",
        }
        for key, path in sb_map.items():
            if key in name:
                return path
        return f"system_b_input.{clean_field_name(name)}"
    
    return f"industry_data.{clean_field_name(name)}"


def clean_field_name(name: str) -> str:
    """清理字段名用于JSON路径"""
    cleaned = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned.strip('_')


def infer_source_priority(indicator_name: str, category: str) -> List[str]:
    """推断数据来源优先级"""
    name = indicator_name.lower()
    
    # 财报优先
    if any(k in name for k in ["毛利率", "营收", "收入", "利润", "净利润", "roe", "roic", "资产", "负债", "现金流", "应收", "库存", "存货", "周转"]):
        return ["财报/季报", "研报", "公司公告"]
    
    # 业绩会/订单优先
    if any(k in name for k in ["订单", "backlog", "pipeline", "合同", "预收款", "合同负债"]):
        return ["业绩说明会/投资者关系活动", "公司公告", "研报"]
    
    # 行业数据/价格优先
    if any(k in name for k in ["价格", "涨价", "跌幅", "交货", "周期", "产能利用率", "稼动率", "供需", "缺口", "渗透率"]):
        return ["行业研报/券商调研", "行业协会/咨询机构", "公司公告", "行业新闻"]
    
    # 宏观/政策优先
    if any(k in name for k in ["政策", "补贴", "capex", "资本开支", "投资"]):
        return ["部委文件/政策", "券商研报", "行业新闻"]
    
    # 技术/产品
    if any(k in name for k in ["技术", "产品", "良率", "认证", "渗透率"]):
        return ["公司公告", "行业研报", "技术会议/OFC等"]
    
    return ["财报数据", "研报", "公司公告", "行业新闻"]


def infer_freshness(indicator_name: str) -> str:
    """推断数据时效要求"""
    name = indicator_name.lower()
    if any(k in name for k in ["毛利率", "营收", "收入", "利润", "净利率", "roe", "roic", "资产", "负债", "现金流"]):
        return "最近季度财报（90天内）"
    if any(k in name for k in ["订单", "backlog", "pipeline", "合同", "预收款"]):
        return "最新业绩会/公告（60天内）"
    if any(k in name for k in ["价格", "涨价", "交货", "周期", "产能", "稼动率", "缺口"]):
        return "最近30天行业数据"
    if any(k in name for k in ["政策", "capex", "资本开支", "投资", "补贴"]):
        return "最近6个月政策/公告"
    return "最近90天内有效数据"


def infer_required_level(category: str, indicator_name: str) -> str:
    """推断必填级别"""
    # 五态信号核心字段
    core_signals = ["营收", "收入", "毛利率", "毛利", "订单", "产能", "利用率", "价格", "库存", "资本", "capex", "政策"]
    if category == "barometric" and any(k in indicator_name for k in core_signals[:4]):
        return REQUIRED
    if category == "mid_axis" and any(k in indicator_name for k in ["毛利率", "产能", "订单", "交付"]):
        return REQUIRED
    if category == "ebb_warning" and any(k in indicator_name for k in ["库存", "价格", "应收", "取消"]):
        return REQUIRED
    # 产业链关键指标
    if any(k in indicator_name for k in ["价格", "缺口", "交货", "产能利用率", "毛利率", "营收", "订单"]):
        return REQUIRED
    if any(k in indicator_name for k in ["政策", "技术", "认证", "良率", "渗透率", "替代"]):
        return RECOMMENDED
    return OPTIONAL


def build_validation_rule(indicator: Dict[str, Any]) -> str:
    """构建数据校验/判定规则，告诉AI搜到数据后怎么标注趋势"""
    trigger = indicator.get("trigger", "")
    unit = indicator.get("unit", "")
    
    rules = []
    if trigger:
        rules.append(f"触发条件: {trigger}")
    if unit:
        rules.append(f"单位: {unit}")
    
    # 自动添加趋势标注规则
    name = indicator.get("indicator", "").lower()
    if "毛利率" in name:
        rules.append("趋势标注: >30%为高毛利，20-30%中等，<20%偏低；环比改善↑，恶化↓")
    elif "营收" in name or "收入" in name:
        rules.append("趋势标注: >30%为高增长，10-30%稳健，<10%放缓，负增长↓")
    elif "价格" in name:
        rules.append("趋势标注: 连续上涨↑，连续下跌↓，波动→")
    elif "库存" in name:
        rules.append("趋势标注: 天数下降↓为需求好转，上升↑为积压")
    elif "订单" in name or "backlog" in name:
        rules.append("趋势标注: 同比增长↑为景气，下降↓为收缩")
    elif "产能" in name or "利用率" in name:
        rules.append("趋势标注: >90%为紧张，70-90%正常，<70%过剩")
    elif "交货" in name:
        rules.append("趋势标注: 周期延长↑为紧缺，缩短↓为缓解")
    
    return " | ".join(rules) if rules else "按实际数值记录，附来源和时间戳"


def build_fallback_strategy(indicator_name: str) -> str:
    """构建搜不到数据时的降级策略"""
    name = indicator_name.lower()
    if "毛利率" in name:
        return "用往期财报毛利率推算趋势；或标注'数据缺失'"
    if "营收" in name or "收入" in name:
        return "用环比替代同比；或标注'数据缺失'"
    if "订单" in name:
        return "用pipeline或客户合作替代；或标注'数据缺失'"
    if "产能" in name or "利用率" in name:
        return "用扩产状态推断（扩产中→产能爬坡）"
    if "价格" in name:
        return "用相近材料/产品价格类比；或标注'数据缺失'"
    if "库存" in name:
        return "用存货周转天数替代；或标注'数据缺失'"
    return "标注'数据缺失'，不编造数字"


def _build_format_example(task: Dict[str, Any]) -> str:
    """为每个task生成填值格式示例，让AI无需文档就理解怎么填"""
    field_path = task.get("field_path", "")
    indicator = task.get("indicator_name", "")
    
    # 根据field_path推断是数值还是文本
    numeric_fields = ["revenue_growth", "gross_margin", "capacity_utilization", 
                      "price_yoy", "inventory_days", "rd_ratio", "roe", "penetration"]
    is_numeric = any(f in field_path for f in numeric_fields)
    
    if is_numeric:
        return f"数值: 如 35.2 | source: 公司2026Q1财报 | date: 2026-04-28"
    else:
        return f"文本: 如 '扩产中，预计Q3投产' | source: 公司公告 | date: 2026-03-15"


def extract_chain_node_tasks(preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从产业链各层级（上游/中游/下游）提取关键指标任务"""
    tasks = []
    industry = preset.get("industry_name", "")
    
    for tier in ["upstream", "midstream", "downstream"]:
        tier_data = preset.get(tier, {})
        nodes = tier_data.get("nodes", []) if isinstance(tier_data, dict) else []
        tier_label = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}.get(tier, tier)
        
        for node in nodes:
            node_name = node.get("name", "未命名")
            key_metrics = node.get("key_metrics", [])
            
            for metric in key_metrics:
                if isinstance(metric, str):
                    metric_name = metric
                else:
                    metric_name = str(metric)
                
                queries = build_search_queries(metric_name, industry)
                field_path = infer_field_path(metric_name, tier)
                
                tasks.append({
                    "task_id": f"chain_{tier}_{clean_field_name(node_name)}_{clean_field_name(metric_name)}",
                    "layer": "产业链结构",
                    "category": tier,
                    "category_label": tier_label,
                    "node_name": node_name,
                    "indicator_name": metric_name,
                    "field_name": clean_field_name(metric_name),
                    "field_path": field_path,
                    "chinese_queries": queries["chinese"],
                    "english_queries": queries["english"],
                    "source_priority": infer_source_priority(metric_name, tier),
                    "required_level": infer_required_level(tier, metric_name),
                    "freshness": infer_freshness(metric_name),
                    "validation_rule": f"产业链指标: {node_name} | 记录当前数值+趋势+来源",
                    "fallback_strategy": build_fallback_strategy(metric_name),
                    "notes": f"该指标用于交叉验证产业链{node_name}环节的景气度",
                })
    
    return tasks


def extract_signal_tasks(preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从preset_indicators提取五态信号任务"""
    tasks = []
    industry = preset.get("industry_name", "")
    indicators = preset.get("preset_indicators", {})
    
    signal_categories = {
        "barometric": "景气度信号",
        "mid_axis": "拐点信号",
        "ebb_warning": "退潮预警",
    }
    
    for category, label in signal_categories.items():
        items = indicators.get(category, [])
        for idx, ind in enumerate(items):
            if not isinstance(ind, dict):
                continue
            
            ind_name = ind.get("indicator", f"指标_{idx}")
            queries = build_search_queries(ind_name, industry)
            field_path = infer_field_path(ind_name, category)
            
            tasks.append({
                "task_id": f"signal_{category}_{clean_field_name(ind_name)}_{idx}",
                "layer": "System A 五态拐点",
                "category": category,
                "category_label": label,
                "indicator_name": ind_name,
                "unit": ind.get("unit", ""),
                "trigger": ind.get("trigger", ""),
                "current_hint": ind.get("current", "待搜索"),
                "field_name": clean_field_name(ind_name),
                "field_path": field_path,
                "chinese_queries": queries["chinese"],
                "english_queries": queries["english"],
                "source_priority": infer_source_priority(ind_name, category),
                "required_level": infer_required_level(category, ind_name),
                "freshness": infer_freshness(ind_name),
                "validation_rule": build_validation_rule(ind),
                "fallback_strategy": build_fallback_strategy(ind_name),
                "notes": f"五态模型{label}: 搜到数据后按trigger条件判定是否触发",
            })
    
    return tasks


def extract_lifecycle_tasks(preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """提取生命周期判定所需数据任务"""
    tasks = []
    industry = preset.get("industry_name", "")
    
    lifecycle_metrics = [
        {"name": "行业营收增速", "field": "lifecycle_indicators.revenue_growth", "rule": ">50%导入期, 20-50%成长期, <20%成熟期"},
        {"name": "毛利率修复趋势", "field": "lifecycle_indicators.gross_margin", "rule": "低/亏损→修复→稳定"},
        {"name": "产能扩张状态", "field": "lifecycle_indicators.capacity_expansion", "rule": "爬坡中→扩产→饱和"},
        {"name": "渗透率水平", "field": "lifecycle_indicators.penetration", "rule": "<15%导入期, 15-40%成长期, >60%成熟期"},
        {"name": "行业竞争格局", "field": "lifecycle_indicators.competition", "rule": "分散→集中→稳定"},
    ]
    
    for metric in lifecycle_metrics:
        queries = build_search_queries(metric["name"], industry)
        tasks.append({
            "task_id": f"lifecycle_{clean_field_name(metric['name'])}",
            "layer": "产业链生命周期",
            "category": "lifecycle",
            "category_label": "生命周期",
            "indicator_name": metric["name"],
            "field_name": clean_field_name(metric["name"]),
            "field_path": metric["field"],
            "chinese_queries": queries["chinese"],
            "english_queries": queries["english"],
            "source_priority": ["行业研报", "券商报告", "行业协会"],
            "required_level": RECOMMENDED,
            "freshness": "最近90天行业数据",
            "validation_rule": metric["rule"],
            "fallback_strategy": "用相近行业数据类比，标注'参考行业'",
            "notes": "生命周期判定需要行业级数据，非个股数据",
        })
    
    return tasks


def extract_system_b_tasks(stock_code: str, stock_name: str) -> List[Dict[str, Any]]:
    """提取System B个股类型判定任务"""
    tasks = []
    
    sb_metrics = [
        {"name": "营收增速", "field": "system_b_input.revenue_growth", "rule": ">30%成长型, <20%价值型"},
        {"name": "研发投入占比", "field": "system_b_input.rd_ratio", "rule": ">5%技术壁垒, <3%常规"},
        {"name": "资产轻重", "field": "system_b_input.asset_lightness", "rule": "轻资产扩张弹性大"},
        {"name": "盈利稳定性", "field": "system_b_input.profit_stability", "rule": "连续盈利→价值型, 波动大→周期型"},
        {"name": "ROE/ROIC", "field": "system_b_input.roe", "rule": ">15%优质, 8-15%中等, <8%偏弱"},
    ]
    
    for metric in sb_metrics:
        queries = {
            "chinese": [
                f"{stock_name} {stock_code} {metric['name']} 2026",
                f"{stock_name} {metric['name']} 财报",
            ],
            "english": [
                f"{stock_name} {metric['name']} 2026 financial report",
            ],
        }
        tasks.append({
            "task_id": f"systemb_{clean_field_name(metric['name'])}",
            "layer": "System B 个股类型",
            "category": "system_b",
            "category_label": "个股判定",
            "indicator_name": metric["name"],
            "field_name": clean_field_name(metric["name"]),
            "field_path": metric["field"],
            "chinese_queries": queries["chinese"],
            "english_queries": queries["english"],
            "source_priority": ["最新季报/年报", "券商研报", "公司公告"],
            "required_level": RECOMMENDED,
            "freshness": "最近季度财报（90天内）",
            "validation_rule": metric["rule"],
            "fallback_strategy": "用往期数据推算趋势，标注'基于历史推断'",
            "notes": "个股级数据，用于判定成长/周期/价值/主题/混合型",
        })
    
    return tasks


def generate_collection_guide(preset_name: str, stock_code: str = "", stock_name: str = "") -> Dict[str, Any]:
    """
    生成完整的数据采集任务清单。
    
    对方AI拿到后按以下流程执行：
    1. 读取本清单
    2. 按required_level排序（★必填优先）
    3. 逐个执行chinese_queries搜索
    4. 校验来源优先级（优先用高可信度来源）
    5. 记录数值+来源+日期
    6. 按field_path回填JSON
    7. 缺失字段标注"数据缺失"
    8. 完成后运行pipeline生成报告
    """
    preset = load_preset(preset_name)
    if not preset:
        logger.error("无法加载preset: %s", preset_name)
        return {}
    
    industry = preset.get("industry_name", preset_name)
    
    all_tasks = []
    all_tasks.extend(extract_signal_tasks(preset))        # System A 五态信号
    all_tasks.extend(extract_chain_node_tasks(preset))     # 产业链上下游
    all_tasks.extend(extract_lifecycle_tasks(preset))      # 生命周期
    
    if stock_code:
        all_tasks.extend(extract_system_b_tasks(stock_code, stock_name or stock_code))
    
    # 排序：必填在前，推荐其次，可选最后
    level_order = {REQUIRED: 0, RECOMMENDED: 1, OPTIONAL: 2}
    all_tasks.sort(key=lambda t: level_order.get(t.get("required_level", OPTIONAL), 2))
    
    # 给每个task补 target_file 和 format_example（让AI零文档理解）
    target_file = f"data/{stock_code}_real_data.json" if stock_code else "data/<stock_code>_real_data.json"
    for task in all_tasks:
        task["target_file"] = target_file
        task["format_example"] = _build_format_example(task)
    
    guide = {
        "meta": {
            "version": "V4.5",
            "preset": preset_name,
            "industry": industry,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "generated_at": str(datetime.now())[:19],
            "total_tasks": len(all_tasks),
            "required_count": sum(1 for t in all_tasks if t.get("required_level") == REQUIRED),
            "recommended_count": sum(1 for t in all_tasks if t.get("required_level") == RECOMMENDED),
            "optional_count": sum(1 for t in all_tasks if t.get("required_level") == OPTIONAL),
        },
        "instructions": {
            "role": "你是一个数据采集AI。请按本清单逐项搜索数据，回填到JSON文件。",
            "target_file": f"data/{stock_code}_real_data.json" if stock_code else "data/<stock_code>_real_data.json",
            "execution_order": [
                "1. 按 required_level 排序：★必填 → ☆推荐 → ○可选，必填项优先搜",
                "2. 对每个 task: 用 chinese_queries 搜索 → 选 source_priority 最高的结果",
                "3. 把搜到的值按 format_example 格式，写入 target_file 中 field_path 指定的位置",
                "4. field_path 用点号表示 JSON 嵌套路径，如 real_signals.revenue_growth 表示 {\"real_signals\": {\"revenue_growth\": ...}}",
                "5. 搜索失败时用 fallback_strategy 降级，绝不编造数字",
                "6. 非数值字段（来源、备注）也必须填写 source 和 date",
                "7. 完成后运行: python3 scripts/validate_data.py <代码> 再跑 ./run.sh <代码>",
            ],
            "critical_rules": [
                "每个数字必须带 source（来源名称）和 date（YYYY-MM-DD）",
                "搜不到就写 'data_missing'，不要编",
                "行业数据用行业研报，个股数据用财报/季报",
            ],
        },
        "workflow": {
            "step_1": "按task_id顺序执行搜索（★必填优先）",
            "step_2": "每个任务：执行chinese_queries → 筛选source_priority最高的来源 → 记录数值+来源URL+日期",
            "step_3": "按field_path回填到 data/<stock_code>_real_data.json",
            "step_4": "缺失字段标注'数据缺失'，不编造",
            "step_5": "运行 python3 scripts/validate_data.py <stock_code> 校验完整性",
            "step_6": "运行 python3 core/pipeline.py <stock_code> 生成最终报告",
        },
        "data_quality_rules": {
            "rule_1": "每个数字必须有来源（财报/研报/新闻/公告）和时间戳",
            "rule_2": "优先用source_priority排第一的来源",
            "rule_3": "数据时效超过90天标注'数据老化'",
            "rule_4": "搜不到时用fallback_strategy降级，绝不编造",
            "rule_5": "行业数据用行业研报，个股数据用财报",
        },
        "tasks": all_tasks,
    }
    
    return guide


def save_guide(guide: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
    """保存任务清单到文件"""
    stock_code = guide.get("meta", {}).get("stock_code", "unknown")
    preset = guide.get("meta", {}).get("preset", "generic")
    
    if output_path is None:
        output_path = DATA_DIR / f"{stock_code}_{preset}_collection_tasks.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(guide, f, ensure_ascii=False, indent=2)
    
    logger.info("采集任务清单已保存: %s (%d项任务)", output_path, guide["meta"]["total_tasks"])
    return output_path


def main():
    import argparse
    from datetime import datetime
    
    parser = argparse.ArgumentParser(description="V4.5 AI数据采集任务生成器")
    parser.add_argument("preset_or_code", help="产业链preset名称或股票代码")
    parser.add_argument("--stock-code", "-c", help="股票代码（如002916.SZ）")
    parser.add_argument("--stock-name", "-n", help="股票名称（如深南电路）")
    parser.add_argument("--preset", "-p", help="强制指定preset名称")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--auto-detect", action="store_true", help="尝试自动检测preset")
    
    args = parser.parse_args()
    
    # 解析输入
    preset_name = args.preset or args.preset_or_code
    stock_code = args.stock_code or ""
    stock_name = args.stock_name or ""
    
    # 如果输入像股票代码（含数字），尝试从映射表找preset
    if re.search(r'\d', args.preset_or_code) and not args.preset:
        # 尝试加载映射表
        mapping_path = SCRIPT_DIR / "data" / "mappings" / "stock-to-industry-optical.json"
        if mapping_path.exists():
            try:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
                matched = mapping.get(args.preset_or_code)
                if matched:
                    preset_name = matched.get("preset", "generic")
                    stock_code = args.preset_or_code
                    stock_name = matched.get("name", stock_code)
                    logger.info("[自动映射] %s → preset=%s", stock_code, preset_name)
            except Exception:
                pass
    
    guide = generate_collection_guide(preset_name, stock_code, stock_name)
    
    if not guide:
        print("错误: 无法生成采集任务清单")
        sys.exit(1)
    
    # 输出摘要
    meta = guide["meta"]
    print(f"\n{'='*60}")
    print(f"V4.5 AI数据采集任务清单")
    print(f"{'='*60}")
    print(f"产业链: {meta['industry']}")
    print(f"Preset: {meta['preset']}")
    if meta['stock_code']:
        print(f"标的: {meta['stock_name']} ({meta['stock_code']})")
    print(f"总任务: {meta['total_tasks']}项")
    print(f"  ★必填: {meta['required_count']}项")
    print(f"  ☆推荐: {meta['recommended_count']}项")
    print(f"  ○可选: {meta['optional_count']}项")
    print(f"{'='*60}\n")
    
    # 输出前5个必填任务预览
    required_tasks = [t for t in guide["tasks"] if t.get("required_level") == REQUIRED][:5]
    if required_tasks:
        print("【必填任务预览】")
        for t in required_tasks:
            print(f"  {t['task_id']}: {t['indicator_name']} → {t['field_path']}")
            print(f"    搜索: {t['chinese_queries'][0]}")
            print(f"    来源: {' > '.join(t['source_priority'][:3])}")
            print()
    
    # 保存
    output = save_guide(guide, Path(args.output) if args.output else None)
    print(f"任务清单已保存: {output}")
    print(f"\n对方AI执行流程:")
    for k, v in guide["workflow"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
