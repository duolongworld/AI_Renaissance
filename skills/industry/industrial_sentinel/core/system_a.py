#!/usr/bin/env python3
"""
System A - 中观层产业拐点分析引擎
合并模块:数据获取、数据防火墙、五态拐点模型

包含:
- 四层行业数据获取(L1→L4 降级)
- System A 数据防火墙(白名单/黑名单校验)
- 五态拐点定量判定(Pre/Early/Confirmed/Late/Post)
- 产业链生命周期判定(初创/成长/成熟/衰退)

V4.5 变更:
- 删除所有评分数字与评分公式
- 删除产业拐点指数(0-100)合成
- 五态判定改为基于真实信号匹配
- 生命周期判定改为基于数据推断
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union, Set

# ───────────────────────────────────────────────────────────────
# 日志配置(统一一次)
# ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("system_a")

# ───────────────────────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class IndustryDataPoint:
    """
    行业数据点 -- System A 的唯一合法输入单元 (V4.5 无评分版)

    属性:
        value: 数据值(float/int/str,视metric而定)
        source_level: 数据来源层级 L1/L2/L3/L4
        source_detail: 详细来源说明(用于溯源表)
        data_date: 数据原始日期(YYYY-MM-DD)
        timestamp: 数据采集时间
    """
    value: Union[float, int, str]
    source_level: str  # "L1" / "L2" / "L3" / "L4"
    source_detail: str = ""
    data_date: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source_level": self.source_level,
            "source_detail": self.source_detail,
            "data_date": self.data_date,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════
# 异常类
# ═══════════════════════════════════════════════════════════════

class DataSourceFallback(Exception):
    """
    数据源降级异常。
    当某一层级数据获取失败时抛出,携带失败原因和已尝试层级,
    由 acquire_industry_data() 捕获并自动触发下一层级。
    """
    def __init__(self, message: str, failed_level: str, attempted_source: str, next_level: str):
        self.failed_level = failed_level
        self.attempted_source = attempted_source
        self.next_level = next_level
        super().__init__(message)


class AllLevelsFailed(Exception):
    """L1→L4 全部降级后仍无法获取数据,终极失败异常。"""
    def __init__(self, industry_name: str, metric: str, attempts: List[str]):
        self.industry_name = industry_name
        self.metric = metric
        self.attempts = attempts
        super().__init__(f"[{industry_name}.{metric}] L1→L4 全部失败,已尝试: {attempts}")


# ═══════════════════════════════════════════════════════════════
# 行业预设:龙头股权重配置(L3推断用)
# ═══════════════════════════════════════════════════════════════

INDUSTRY_LEADERS: Dict[str, Dict[str, Any]] = {
    "光模块": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "中际旭创", "code": "300308.SZ", "weight": 0.40},
            {"name": "新易盛", "code": "300502.SZ", "weight": 0.30},
            {"name": "光迅科技", "code": "002281.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "光通信": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "中际旭创", "code": "300308.SZ", "weight": 0.40},
            {"name": "新易盛", "code": "300502.SZ", "weight": 0.30},
            {"name": "光迅科技", "code": "002281.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "ABF载板": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.50},
            {"name": "兴森科技", "code": "002436.SZ", "weight": 0.30},
            {"name": "其他", "code": "OTHER", "weight": 0.20},
        ],
    },
    "PCB": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.35},
            {"name": "深南电路", "code": "002916.SZ", "weight": 0.30},
            {"name": "鹏鼎控股", "code": "002938.SZ", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.15},
        ],
    },
    "半导体设备": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "北方华创", "code": "002371.SZ", "weight": 0.40},
            {"name": "中微公司", "code": "688012.SH", "weight": 0.30},
            {"name": "拓荆科技", "code": "688072.SH", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.10},
        ],
    },
    "存储": {
        "metric_map": {
            "订单增速": "order_growth",
            "产能利用率": "capacity_util",
            "库存天数": "inventory_days",
            "价格趋势": "price_trend",
            "毛利率": "gross_margin",
        },
        "leaders": [
            {"name": "兆易创新", "code": "603986.SH", "weight": 0.35},
            {"name": "江波龙", "code": "301308.SZ", "weight": 0.30},
            {"name": "佰维存储", "code": "688525.SH", "weight": 0.20},
            {"name": "其他", "code": "OTHER", "weight": 0.15},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# 预取数据提取(V4.4 真实数据层)
# ───────────────────────────────────────────────────────────────

# Part 2 - 数据防火墙 (v44-data-firewall)
# ═══════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────
# 日志配置
# ───────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════
# 异常类
# ═══════════════════════════════════════════════════════════════
class DataFirewallViolation(Exception):
    """
    数据防火墙违规异常。
    当 System A 输入数据包含公司特定字段时抛出。
    """
    def __init__(self, message: str, violations: List[str] = None):
        self.violations = violations or []
        super().__init__(message)


# ═══════════════════════════════════════════════════════════════
# 白名单:System A 允许使用的行业级字段
# ═══════════════════════════════════════════════════════════════
SYSTEM_A_ALLOWED_FIELDS: Set[str] = {
    "industry_order_growth",
    "industry_capacity_util",
    "industry_inventory_days",
    "industry_price_trend",
    "industry_policy_score",
    "industry_lifecycle_stage",
    "industry_penetration_rate",
    "industry_competition_score",
}

# 允许的前缀模式(用于动态匹配 industry_ 开头的字段)
ALLOWED_PREFIX = "industry_"


# ═══════════════════════════════════════════════════════════════
# 黑名单:System A 严禁使用的公司特定字段
# ═══════════════════════════════════════════════════════════════
SYSTEM_A_BLOCKED_FIELDS: Set[str] = {
    # 订单与营收
    "company_order_growth",
    "company_revenue_growth",
    "company_revenue",
    "company_backlog",
    # 现金流
    "company_cash_flow",
    "company_operating_cash_flow",
    "company_free_cash_flow",
    "company_cash_flow_ratio",
    # 市场份额
    "company_market_share",
    "company_share_change",
    "company_market_position",
    # 管理层
    "company_mgmt_score",
    "company_mgmt_change",
    "company_ceo_tenure",
    # 估值
    "company_valuation_pe",
    "company_valuation_pb",
    "company_valuation_ps",
    "company_valuation_peg",
    "company_dividend_yield",
    # 技术面
    "company_technical_ma",
    "company_technical_rsi",
    "company_technical_macd",
    "company_technical_volume",
    "company_support_level",
    "company_resistance_level",
    # 基本面
    "company_roe",
    "company_roic",
    "company_gross_margin",
    "company_net_margin",
    "company_debt_ratio",
    "company_patent_count",
    "company_rd_ratio",
    # 财务排雷
    "company_receivable_growth",
    "company_contract_liability",
    "company_capital_expenditure",
    "company_goodwill",
    "company_inventory_turnover",
    # 情绪/消息
    "company_news_sentiment",
    "company_analyst_coverage",
    "company_institutional_holding",
    "company_short_interest",
}

# 黑名单前缀模式
BLOCKED_PREFIXES: tuple = (
    "company_",
    "stock_",
    "firm_",
    "corp_",
    "enterprise_",
)


# ═══════════════════════════════════════════════════════════════
# 启发式检测模式
# ═══════════════════════════════════════════════════════════════

# A股股票代码正则:6位数字 + .SH/.SZ/.BJ
STOCK_CODE_PATTERN = re.compile(
    r"\b\d{6}\.(?:SH|SZ|BJ)\b",
    re.IGNORECASE
)

# 公司名称后缀启发式(常见A股公司名称后缀)
COMPANY_NAME_SUFFIXES: tuple = (
    # 通用公司后缀
    "公司",  # 捕获 "某公司"、"XX公司"、"行业公司" 等
    "股份", "科技", "电子", "通信", "光学", "半导体",
    "精密", "智能", "微", "新材", "生态", "集团",
    "控股", "实业", "制造", "软件", "网络", "仪器",
    "设备", "材料", "化学", "生物", "医药", "医疗",
    "能源", "环保", "传媒", "文化", "旅游", "航空",
    "航天", "汽车", "机械", "电气", "电力", "建设",
    "工程", "交通", "物流", "农业", "食品", "饮料",
    "纺织", "服装", "商业", "贸易", "金融", "保险",
    "银行", "证券", "地产", "置业", "矿业", "冶炼",
    "化工", "化肥", "农药", "橡胶", "塑料", "造纸",
    "印刷", "包装", "家具", "建材", "水泥", "钢铁",
    "有色", "金属", "煤炭", "石油", "燃气", "水务",
    # 行业特定后缀(覆盖用户关注标的)
    "锗业", "硅业", "光子", "芯", "创", "立",
    "光迅", "华芯", "景科技", "特光学", "光科技",
    "孚通信", "晶科技", "田微", "润光学", "绿生态",
    "通股份", "鼎股份", "天股份",
)

# 公司名称后缀正则(用于检测字段值中嵌入的公司名)
COMPANY_SUFFIX_PATTERN = re.compile(
    r"[\u4e00-\u9fff]{1,}(?:" + "|".join(COMPANY_NAME_SUFFIXES) + r")",
    re.IGNORECASE
)


def _contains_stock_code(value: Any) -> bool:
    """
    检查值中是否包含股票代码(如 000001.SZ、300308.SZ)。
    支持字符串、列表、字典递归检测。
    """
    if isinstance(value, str):
        return bool(STOCK_CODE_PATTERN.search(value))
    if isinstance(value, (list, tuple)):
        return any(_contains_stock_code(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_stock_code(v) for v in value.values())
    return False


def _contains_company_name(value: Any) -> bool:
    """
    检查值中是否包含公司名称后缀(如 "贵州茅台"、"宁德时代")。
    仅对字符串值检测,避免误报数字型字段。
    """
    if isinstance(value, str):
        return bool(COMPANY_SUFFIX_PATTERN.search(value))
    if isinstance(value, (list, tuple)):
        return any(_contains_company_name(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_company_name(v) for v in value.values())
    return False


def _is_blocked_field(field_name: str) -> bool:
    """
    判断字段名是否属于 System A 黑名单。
    精确匹配 + 前缀匹配双重检测。
    """
    # 精确匹配黑名单
    if field_name in SYSTEM_A_BLOCKED_FIELDS:
        return True
    # 前缀匹配
    if field_name.startswith(BLOCKED_PREFIXES):
        return True
    return False


def _is_allowed_field(field_name: str) -> bool:
    """
    判断字段名是否属于 System A 白名单。
    精确匹配 + 前缀匹配双重检测。
    """
    if field_name in SYSTEM_A_ALLOWED_FIELDS:
        return True
    if field_name.startswith(ALLOWED_PREFIX):
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# 核心函数:validate_system_a_input
# ═══════════════════════════════════════════════════════════════

def validate_system_a_input(data_dict: Dict[str, Any]) -> bool:
    """
    校验输入数据字典是否符合 System A 数据防火墙规则。

    检查项:
    1. 所有字段名必须在白名单内(industry_ 前缀或精确匹配)
    2. 任何字段名不得命中黑名单(company_ / stock_ / firm_ / corp_ / enterprise_ 前缀)
    3. 字段值中不得嵌入股票代码(如 000001.SZ)
    4. 字段值中不得嵌入公司名称(如 "贵州茅台"、"宁德时代")

    Args:
        data_dict: 待校验的数据字典

    Returns:
        True - 数据干净,可通过防火墙

    Raises:
        DataFirewallViolation: 发现违规字段或嵌入公司特定信息
    """
    if not isinstance(data_dict, dict):
        raise DataFirewallViolation(
            f"输入必须是字典类型,收到 {type(data_dict).__name__}",
            violations=["类型错误"]
        )

    violations: List[str] = []

    for field_name, value in data_dict.items():
        # ── 检查 1:黑名单命中 ──
        if _is_blocked_field(field_name):
            violations.append(
                f"字段名违规:'{field_name}' 命中黑名单(公司特定字段禁止进入 System A)"
            )
            continue

        # ── 检查 2:白名单外字段 ──
        if not _is_allowed_field(field_name):
            violations.append(
                f"字段名未授权:'{field_name}' 不在 System A 白名单中(必须以 'industry_' 开头)"
            )

        # ── 检查 3:字段值嵌入股票代码 ──
        if _contains_stock_code(value):
            violations.append(
                f"值违规:字段 '{field_name}' 的值中检测到股票代码(如 000001.SZ),"
                f"System A 禁止混入公司标识"
            )

        # ── 检查 4:字段值嵌入公司名称 ──
        if _contains_company_name(value):
            violations.append(
                f"值违规:字段 '{field_name}' 的值中检测到公司名称(如 '贵州茅台'),"
                f"System A 禁止混入公司标识"
            )

    if violations:
        error_msg = (
            f"🚫 System A 数据防火墙拦截:发现 {len(violations)} 处违规\n"
            + "\n".join(f"  • {v}" for v in violations)
            + "\n\nSystem A 仅允许行业级数据(industry_ 前缀字段)。"
            "公司特定数据请通过 System B 通道输入。"
        )
        raise DataFirewallViolation(error_msg, violations=violations)

    logger.info("✅ System A 数据防火墙校验通过:%d 个字段,全部符合行业级数据规范", len(data_dict))
    return True


# ═══════════════════════════════════════════════════════════════
# 核心函数:sanitize_for_system_a
# ═══════════════════════════════════════════════════════════════

def sanitize_for_system_a(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    对混合数据(可能同时包含行业级和公司级字段)进行清洗,
    仅保留 System A 允许的行业级字段。

    处理逻辑:
    1. 遍历所有字段,仅保留白名单内字段
    2. 对保留的字段值进行启发式检测(股票代码、公司名称)
    3. 若值中嵌入公司标识,移除该字段
    4. 记录清洗日志,确保透明可追溯

    Args:
        raw_data: 原始混合数据字典

    Returns:
        清洗后的纯行业级数据字典
    """
    if not isinstance(raw_data, dict):
        logger.warning("清洗输入不是字典,返回空字典")
        return {}

    clean_data: Dict[str, Any] = {}
    removed_fields: List[str] = []

    for field_name, value in raw_data.items():
        # ── 步骤 1:白名单过滤 ──
        if not _is_allowed_field(field_name):
            removed_fields.append(
                f"'{field_name}'(不在白名单,属于公司级或未知字段)"
            )
            continue

        # ── 步骤 2:黑名单二次过滤 ──
        if _is_blocked_field(field_name):
            removed_fields.append(
                f"'{field_name}'(命中黑名单,公司特定字段)"
            )
            continue

        # ── 步骤 3:值级启发式检测 ──
        if _contains_stock_code(value):
            removed_fields.append(
                f"'{field_name}'(值中嵌入股票代码,如 000001.SZ)"
            )
            continue

        if _contains_company_name(value):
            removed_fields.append(
                f"'{field_name}'(值中嵌入公司名称,如 '贵州茅台')"
            )
            continue

        # 通过所有检查,保留
        clean_data[field_name] = value

    # ── 日志记录 ──
    if removed_fields:
        logger.info(
            "🧹 System A 数据清洗完成:保留 %d 个字段,移除 %d 个字段\n"
            "  移除详情:%s",
            len(clean_data),
            len(removed_fields),
            "; ".join(removed_fields)
        )
    else:
        logger.info(
            "✅ System A 数据清洗完成:全部 %d 个字段通过,无需移除",
            len(clean_data)
        )

    return clean_data


# ═══════════════════════════════════════════════════════════════
# 演示 / 测试用例
# ═══════════════════════════════════════════════════════════════

def _run_demo():
    """运行全部测试用例,验证数据防火墙功能。"""
    print("=" * 60)
    print("V4.4 数据防火墙代码层 - 测试套件")
    print("=" * 60)

    passed = 0
    failed = 0

    # ── 测试 1:干净的行业数据应通过 ──
    print("\n【测试 1】干净的行业数据 - 应通过")
    clean_data = {
        "industry_order_growth": 25.0,
        "industry_capacity_util": 85.0,
        "industry_inventory_days": 45,
        "industry_price_trend": 10.0,
        "industry_policy_score": 75,
        "industry_lifecycle_stage": "成长期加速段",
        "industry_penetration_rate": 35.0,
        "industry_competition_score": 60,
    }
    try:
        validate_system_a_input(clean_data)
        print("  ✅ 通过:干净行业数据顺利通过防火墙")
        passed += 1
    except DataFirewallViolation as e:
        print(f"  ❌ 失败:{e}")
        failed += 1

    # ── 测试 2:公司特定数据应被拦截 ──
    print("\n【测试 2】公司特定数据 - 应被拦截")
    company_data = {
        "industry_order_growth": 25.0,
        "company_order_growth": 8.0,      # ❌ 黑名单
        "company_cash_flow": -12.0,       # ❌ 黑名单
        "company_market_share": 15.0,    # ❌ 黑名单
        "company_valuation_pe": 85.0,    # ❌ 黑名单
    }
    try:
        validate_system_a_input(company_data)
        print("  ❌ 失败:公司数据未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确拦截公司特定数据")
        print(f"     发现 {len(e.violations)} 处违规")
        for v in e.violations[:3]:
            print(f"     • {v[:80]}...")
        passed += 1

    # ── 测试 3:混合数据应被清洗 ──
    print("\n【测试 3】混合数据 - 应被清洗为纯行业数据")
    mixed_data = {
        "industry_order_growth": 25.0,
        "industry_capacity_util": 85.0,
        "industry_price_trend": 10.0,
        "company_revenue_growth": 30.0,   # 应被移除
        "company_mgmt_score": 70,        # 应被移除
        "stock_technical_rsi": 65,        # 应被移除
    }
    sanitized = sanitize_for_system_a(mixed_data)
    removed_count = len(mixed_data) - len(sanitized)
    if removed_count == 3 and len(sanitized) == 3:
        print(f"  ✅ 通过:正确移除 {removed_count} 个公司级字段,保留 {len(sanitized)} 个行业级字段")
        passed += 1
    else:
        print(f"  ❌ 失败:应移除 3 个,实际移除 {removed_count} 个;应保留 3 个,实际保留 {len(sanitized)} 个")
        failed += 1

    # ── 测试 4:字段值嵌入股票代码应被拦截 ──
    print("\n【测试 4】字段值嵌入股票代码 - 应被拦截")
    embedded_stock = {
        "industry_order_growth": "光模块行业订单增速 25%(参考 300308.SZ)",  # ❌ 嵌入股票代码
        "industry_capacity_util": 85.0,
    }
    try:
        validate_system_a_input(embedded_stock)
        print("  ❌ 失败:嵌入股票代码未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确检测字段值中的股票代码")
        passed += 1

    # ── 测试 5:字段值嵌入公司名称应被拦截 ──
    print("\n【测试 5】字段值嵌入公司名称 - 应被拦截")
    embedded_company = {
        "industry_order_growth": "某公司订单增速仅 8%,低于行业平均",  # ❌ 嵌入公司名
        "industry_capacity_util": 85.0,
    }
    try:
        validate_system_a_input(embedded_company)
        print("  ❌ 失败:嵌入公司名称未被发现")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确检测字段值中的公司名称")
        passed += 1

    # ── 测试 6:清洗函数应能处理值级嵌入 ──
    print("\n【测试 6】清洗函数处理值级嵌入 - 应移除含嵌入的字段")
    mixed_embedded = {
        "industry_order_growth": 25.0,
        "industry_price_trend": "参考 000001.SZ 涨幅 10%",  # 应被移除
        "industry_policy_score": "某光模块公司受益政策",        # 应被移除
        "industry_capacity_util": 85.0,
    }
    sanitized_embedded = sanitize_for_system_a(mixed_embedded)
    if "industry_price_trend" not in sanitized_embedded and "industry_policy_score" not in sanitized_embedded:
        print(f"  ✅ 通过:正确移除含嵌入标识的字段,保留 {len(sanitized_embedded)} 个干净字段")
        passed += 1
    else:
        print(f"  ❌ 失败:含嵌入标识的字段未被移除")
        failed += 1

    # ── 测试 7:未知前缀字段应被拒绝 ──
    print("\n【测试 7】未知前缀字段 - 应被拒绝")
    unknown_prefix = {
        "industry_order_growth": 25.0,
        "sector_revenue": 100.0,  # ❌ 既非 industry_ 也非 company_,但不在白名单
    }
    try:
        validate_system_a_input(unknown_prefix)
        print("  ❌ 失败:未知前缀字段未被拦截")
        failed += 1
    except DataFirewallViolation as e:
        print(f"  ✅ 通过:正确拦截非白名单字段")
        passed += 1

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print(f"测试完成:通过 {passed} / 失败 {failed} / 总计 {passed + failed}")
    print("=" * 60)
    return failed == 0

# ═══════════════════════════════════════════════════════════════
# Part 3 - 五态拐点模型 (v44-inflection-states)
# ═══════════════════════════════════════════════════════════════

class InflectionState(Enum):
    """五态拐点枚举"""
    PRE = "Pre-inflection"           # 拐点前/潜伏
    EARLY = "Early-inflection"         # 拐点初期
    CONFIRMED = "Confirmed"          # 拐点确认
    LATE = "Late"                    # 拐点晚期
    POST = "Post"                    # 拐点后/衰退


@dataclass
class StateResult:
    """状态判定结果"""
    state_name: str
    state_code: str
    color_code: str          # HTML/CSS color
    color_hex: str           # Hex color for charts
    confidence: float        # 0.0 - 1.0
    investment_advice: str
    key_monitoring_metrics: List[str]
    matched_signals: List[str]
    all_signals: Dict[str, any]


@dataclass
class Threshold:
    """单维度阈值定义"""
    name: str
    description: str
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    exact_match: Optional[str] = None  # 用于布尔型或离散值


# =============================================================================
# 五态阈值定义
# =============================================================================

STATE_THRESHOLDS = {
    InflectionState.PRE: {
        "cycle_score": Threshold("行业周期评分", "0-100", max_val=45),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", max_val=45),
        "policy_score": Threshold("政策催化剂评分", "0-100", max_val=50),
        "utilization": Threshold("产能利用率", "%", min_val=70, max_val=80),
        "price_yoy": Threshold("价格同比", "%", min_val=-5, max_val=0),
        "policy": Threshold("政策强度", "0-100", max_val=50),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="none"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", max_val=10),
    },
    InflectionState.EARLY: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=40, max_val=60),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=35, max_val=60),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=45, max_val=70),
        "utilization": Threshold("产能利用率", "%", min_val=80, max_val=85),
        "price_yoy": Threshold("价格同比", "%", min_val=0, max_val=5),
        "policy": Threshold("政策强度", "0-100", min_val=50, max_val=65),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="planned"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=5, max_val=20),
    },
    InflectionState.CONFIRMED: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=55, max_val=80),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=55, max_val=80),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=60, max_val=85),
        "utilization": Threshold("产能利用率", "%", min_val=85, max_val=95),
        "price_yoy": Threshold("价格同比", "%", min_val=5, max_val=15),
        "policy": Threshold("政策强度", "0-100", min_val=65, max_val=80),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="underway"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=15, max_val=40),
    },
    InflectionState.LATE: {
        "cycle_score": Threshold("行业周期评分", "0-100", min_val=75),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", min_val=70),
        "policy_score": Threshold("政策催化剂评分", "0-100", min_val=75),
        "utilization": Threshold("产能利用率", "%", min_val=95),
        "price_yoy": Threshold("价格同比", "%", min_val=15, max_val=25),
        "price_mom_trend": Threshold("价格环比趋势", "放缓信号", exact_match="slowing"),
        "policy": Threshold("政策强度", "0-100", min_val=80),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="aggressive"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", min_val=20, max_val=50),
    },
    InflectionState.POST: {
        "cycle_score": Threshold("行业周期评分", "0-100", max_val=50),
        "supply_demand_score": Threshold("供需拐点评分", "0-100", max_val=45),
        "policy_score": Threshold("政策催化剂评分", "0-100", max_val=55),
        "utilization": Threshold("产能利用率", "%", max_val=60),
        "price_yoy": Threshold("价格同比", "%", min_val=25),
        "price_mom_trend": Threshold("价格环比趋势", "转负或见顶", exact_match="declining"),
        "policy": Threshold("政策强度", "0-100", max_val=60),
        "capacity_expansion": Threshold("扩产计划", "布尔", exact_match="oversupply_risk"),
        "order_backlog_growth": Threshold("订单 backlog 增速", "%", max_val=10),
    },
}


STATE_META = {
    InflectionState.PRE: {
        "name": "拐点前/潜伏",
        "color_code": "#9CA3AF",    # gray-400
        "color_hex": "#9CA3AF",
        "investment_advice": (
            "行业处于底部区域,产能利用率偏低,价格同比仍在负区间。"
            "政策尚未密集释放。此时适合深度研究、建立观察池,"
            "跟踪左侧信号,等待更明确的拐点确认。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否突破80%",
            "价格同比是否由负转正",
            "政策文件密度是否增加",
            "行业龙头订单是否回暖",
        ],
    },
    InflectionState.EARLY: {
        "name": "拐点初期",
        "color_code": "#60A5FA",    # blue-400
        "color_hex": "#60A5FA",
        "investment_advice": (
            "行业景气度开始回升,产能利用率站上80%,价格同比由负转正。"
            "政策进入预热期。此时是左侧信号窗口,"
            "选择行业内护城河最深的龙头,关注基本面验证。"
        ),
        "key_monitoring_metrics": [
            "产能利用率能否持续突破85%",
            "价格环比是否连续2月为正",
            "订单 backlog 增速是否>15%",
            "扩产计划是否实质性启动",
        ],
    },
    InflectionState.CONFIRMED: {
        "name": "拐点确认",
        "color_code": "#4ADE80",    # green-400
        "color_hex": "#4ADE80",
        "investment_advice": (
            "行业进入高景气通道,产能利用率85-95%,价格同比+5~15%,"
            "政策密集释放期。右侧信号窗口,"
            "优先布局产能紧缺的结构性龙头,关注扩产良率。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否逼近95%瓶颈",
            "价格环比是否出现加速信号",
            "扩产良率爬坡进度",
            "新增产能释放节奏 vs 需求增速",
        ],
    },
    InflectionState.LATE: {
        "name": "拐点晚期",
        "color_code": "#FBBF24",    # amber-400
        "color_hex": "#FBBF24",
        "investment_advice": (
            "行业高度景气但边际动能减弱,产能利用率>95%且扩产激进,"
            "价格同比仍高但环比放缓。进入观察阶段,"
            "警惕过热信号,关注新增产能释放后的供需平衡。"
        ),
        "key_monitoring_metrics": [
            "价格环比增速是否连续3月放缓",
            "扩产产能释放后利用率是否回落",
            "行业估值是否进入历史前20%分位",
            "新进入者数量是否激增",
        ],
    },
    InflectionState.POST: {
        "name": "拐点后/衰退",
        "color_code": "#F87171",    # red-400
        "color_hex": "#F87171",
        "investment_advice": (
            "行业景气见顶回落,产能利用率下降,价格同比虽仍高但环比转负,"
            "政策退坡。景气下行信号,"
            "关注基本面恶化条件,转向休眠观察。"
        ),
        "key_monitoring_metrics": [
            "产能利用率是否跌破85%",
            "价格环比是否连续2月为负",
            "库存天数是否快速攀升",
            "龙头订单增速是否转负",
        ],
    },
}


# =============================================================================
# 核心判定函数
# =============================================================================

def check_threshold(value: any, threshold: Threshold) -> bool:
    """检查单值是否满足阈值"""
    if threshold.exact_match is not None:
        return str(value).lower() == threshold.exact_match.lower()

    if value is None:
        return False

    try:
        val = float(value)
    except (ValueError, TypeError):
        return False

    if threshold.min_val is not None and val < threshold.min_val:
        return False
    if threshold.max_val is not None and val > threshold.max_val:
        return False
    return True


def count_matching_signals(signals: Dict[str, any], state: InflectionState) -> Tuple[int, List[str]]:
    """
    计算给定信号集满足某状态阈值的信号数量
    返回: (匹配数, 匹配信号名列表)
    """
    thresholds = STATE_THRESHOLDS[state]
    matched = []

    for key, threshold in thresholds.items():
        if key in signals and check_threshold(signals[key], threshold):
            matched.append(f"{key}={signals[key]} (满足 {threshold.name} 阈值)")

    return len(matched), matched


def determine_inflection_state(
    cycle_score: float = 0,
    supply_demand_score: float = 0,
    policy_score: float = 0,
    supply_signals: Dict[str, any] = None,
    policy_signals: Dict[str, any] = None,
    cycle_signals: Dict[str, any] = None,
    min_signals_required: int = 2,
    real_signals: Dict[str, Any] = None,
) -> StateResult:
    """
    判定产业拐点状态 - V4.5 多信号匹配, 优先 real_signals 路径,不依赖单一合成指数

    参数:
        cycle_score: 行业周期评分 0-100
        supply_demand_score: 供需拐点评分 0-100
        policy_score: 政策催化剂评分 0-100
        supply_signals: 供需信号 dict
        policy_signals: 政策信号 dict
        cycle_signals: 周期信号 dict
        min_signals_required: 状态切换所需最少同时满足信号数

    返回:
        StateResult: 包含状态名、颜色、投资建议、监测指标、匹配信号详情
    """
    # V4.5 优先：如果提供了 real_signals，走真实数据路径
    if real_signals is not None and isinstance(real_signals, dict) and len(real_signals) > 0:
        result, _ = determine_inflection_state_v45(real_signals, min_signals_required)
        return result

    supply_signals = supply_signals or {}
    policy_signals = policy_signals or {}
    cycle_signals = cycle_signals or {}
    # 合并所有信号(含三维评分作为独立信号)
    all_signals = {
        "cycle_score": cycle_score,
        "supply_demand_score": supply_demand_score,
        "policy_score": policy_score,
        **supply_signals,
        **policy_signals,
        **cycle_signals,
    }

    # 按优先级从高到低评估各状态(POST > LATE > CONFIRMED > EARLY > PRE)
    state_priority = [
        InflectionState.POST,
        InflectionState.LATE,
        InflectionState.CONFIRMED,
        InflectionState.EARLY,
        InflectionState.PRE,
    ]

    best_state = InflectionState.PRE
    best_confidence = 0.0
    best_matched = []

    for state in state_priority:
        matched_count, matched_details = count_matching_signals(all_signals, state)
        total_signals = len(STATE_THRESHOLDS[state])

        # V4.5: 不再要求单一合成指数区间,仅要求匹配信号数>=阈值
        if matched_count >= min_signals_required:
            confidence = matched_count / total_signals if total_signals > 0 else 0.0
            if confidence > best_confidence:
                best_state = state
                best_confidence = confidence
                best_matched = matched_details

    meta = STATE_META[best_state]

    return StateResult(
        state_name=meta["name"],
        state_code=best_state.value,
        color_code=meta["color_code"],
        color_hex=meta["color_hex"],
        confidence=round(best_confidence, 2),
        investment_advice=meta["investment_advice"],
        key_monitoring_metrics=meta["key_monitoring_metrics"],
        matched_signals=best_matched,
        all_signals=all_signals,
    )


# =============================================================================
# 真实产业数据 Demo Cases
# =============================================================================

# ═══════════════════════════════════════════════════════════════
# Part 4 - 评分公式 (v43-scoring-formula)
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# V4.5 重写：五态拐点判定 — 基于真实信号匹配，无算法评分
# ═══════════════════════════════════════════════════════════════

def _parse_string_list(val):
    """将多种格式的定性信号解析为字符串列表"""
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []

def _safe_float(val):
    if val is None: return None
    try: return float(val)
    except (ValueError, TypeError): return None

def determine_inflection_state_v45(real_signals, min_signals_required=2):
    rev_growth = _safe_float(real_signals.get("revenue_growth"))
    gm = _safe_float(real_signals.get("gross_margin"))
    backlog = _safe_float(real_signals.get("order_backlog"))
    util = _safe_float(real_signals.get("capacity_utilization"))
    price_yoy = _safe_float(real_signals.get("price_yoy"))
    inv_days = _safe_float(real_signals.get("inventory_days"))
    capex = str(real_signals.get("capex_plan", "")).lower()

    # P1-1: 读取用户回填的定性信号作为bonus
    inflection_bonus = _parse_string_list(real_signals.get("inflection_signals", []))
    lifecycle_bonus = _parse_string_list(real_signals.get("lifecycle_signals", []))
    # 关键词→拐点阶段映射
    BONUS_KEYWORD_MAP = {
        "confirmed": ["加速", "突破", "放量", "提价", "涨价", "缺货", "爆单", "产能紧张", "催化剂"],
        "early": ["复苏", "回暖", "政策", "试点", "导入", "验证", "送样", "通过"],
        "pre": ["低迷", "探底", "观望", "去库存", "低谷"],
        "late": ["过热", "泡沫", "疯狂", "抢装", "囤货", "高位"],
        "post": ["过剩", "降价", "暴跌", "砍单", "收缩", "去产能"],
    }
    bonus_matches = {tag: [] for tag in BONUS_KEYWORD_MAP}
    for signal_text in inflection_bonus + lifecycle_bonus:
        text_lower = signal_text.lower()
        for tag, keywords in BONUS_KEYWORD_MAP.items():
            if any(kw in text_lower for kw in keywords):
                bonus_matches[tag].append(signal_text)

    def _match(tag):
        m = []
        if tag == "pre":
            if rev_growth is not None and rev_growth < 10: m.append(f"营收增速 {rev_growth:.1f}% < 10%")
            if util is not None and util < 80: m.append(f"产能利用率 {util:.1f}% < 80%")
            if price_yoy is not None and price_yoy < 0: m.append(f"价格同比 {price_yoy:.1f}% < 0")
            if capex in ("none", ""): m.append("扩产计划：无")
            if backlog is not None and backlog < 20: m.append(f"订单backlog {backlog:.1f} 低位")
        elif tag == "early":
            if rev_growth is not None and 5 <= rev_growth < 20: m.append(f"营收增速 {rev_growth:.1f}% 温和复苏")
            if util is not None and 80 <= util < 85: m.append(f"产能利用率 {util:.1f}% 回升中")
            if price_yoy is not None and 0 <= price_yoy < 5: m.append(f"价格同比 {price_yoy:.1f}% 止跌")
            if capex in ("planned", "规划中"): m.append("扩产：已规划")
            if backlog is not None and 20 <= backlog < 50: m.append(f"订单backlog {backlog:.1f} 改善")
            if gm is not None and gm < 0: m.append(f"毛利率 {gm:.1f}% 仍为负")
        elif tag == "confirmed":
            if rev_growth is not None and rev_growth >= 20: m.append(f"营收增速 {rev_growth:.1f}% >= 20% 加速")
            if util is not None and util >= 85: m.append(f"产能利用率 {util:.1f}% >= 85% 紧张")
            if price_yoy is not None and price_yoy >= 5: m.append(f"价格同比 {price_yoy:.1f}% >= 5% 涨价")
            if capex in ("underway", "进行中", "aggressive", "激进"): m.append("扩产：已启动")
            if backlog is not None and backlog >= 50: m.append(f"订单backlog {backlog:.1f} 高位")
            if gm is not None and gm >= 0: m.append(f"毛利率 {gm:.1f}% 修复至非负")
        elif tag == "late":
            if util is not None and util >= 95: m.append(f"产能利用率 {util:.1f}% >= 95% 瓶颈")
            if price_yoy is not None and price_yoy >= 15: m.append(f"价格同比 {price_yoy:.1f}% >= 15% 高位")
            if inv_days is not None and inv_days > 60: m.append(f"库存天数 {inv_days:.1f} > 60 补库过激")
            if capex in ("aggressive", "激进"): m.append("扩产：激进")
            mom = str(real_signals.get("price_mom_trend", "")).lower()
            if mom in ("slowing", "declining", "放缓", "下滑"): m.append("价格环比：放缓")
        elif tag == "post":
            if rev_growth is not None and rev_growth < 0: m.append(f"营收增速 {rev_growth:.1f}% < 0 收缩")
            if util is not None and util < 75: m.append(f"产能利用率 {util:.1f}% < 75% 回落")
            if price_yoy is not None and price_yoy < -5: m.append(f"价格同比 {price_yoy:.1f}% < -5% 暴跌")
            if backlog is not None and backlog < 10: m.append(f"订单backlog {backlog:.1f} 枯竭")
            if inv_days is not None and inv_days > 80: m.append(f"库存天数 {inv_days:.1f} > 80 积压")
        return len(m) >= min_signals_required, m

    checks = [("post", InflectionState.POST), ("late", InflectionState.LATE),
              ("confirmed", InflectionState.CONFIRMED), ("early", InflectionState.EARLY),
              ("pre", InflectionState.PRE)]
    best_state, best_matched, best_conf = InflectionState.PRE, [], 0.0
    for tag, state in checks:
        ok, matched = _match(tag)
        # 合并定性bonus信号
        bonus_list = bonus_matches.get(tag, [])
        total_matched = matched + [f"[定性] {b}" for b in bonus_list]
        if ok or len(total_matched) >= min_signals_required:
            conf = min(1.0, len(total_matched)/8)  # 分母用8（6定量+bonus空间）
            if conf >= best_conf:
                best_state, best_conf, best_matched = state, conf, total_matched
    meta = STATE_META[best_state]
    logic = "\\n".join([f"基于 {len(best_matched)} 个真实数据信号匹配："] + [f"  • {x}" for x in best_matched] if best_matched else ["信号不足，回退至「拐点前」。建议补充真实指标。"])
    return StateResult(
        state_name=meta["name"], state_code=best_state.value,
        color_code=meta["color_code"], color_hex=meta["color_hex"],
        confidence=round(best_conf, 2),
        investment_advice=meta["investment_advice"],
        key_monitoring_metrics=meta["key_monitoring_metrics"],
        matched_signals=best_matched, all_signals=real_signals,
    ), logic


# ============================================================================
# System B: Micro 层 - 个股层面调整(V4.3 新增)
# ============================================================================


class LifecyclePhase(Enum):
    """产业链生命周期四阶段"""
    GROWTH = "成长期"
    MATURE = "成熟期"
    DECLINE = "衰退期"
    EBB = "退潮期"


def determine_lifecycle_phase(
    penetration_rate: float,
    revenue_growth: float,
    industry_concentration_hhi: float = None,
    price_trend: str = "stable",
) -> Dict[str, any]:
    """
    判定产业链生命周期阶段 — 基于渗透率阈值（V4.0 标准）

    渗透率阈值标准：
    - 成长期: 渗透率 < 15% 或 15-30%且增速>25%
    - 成熟期: 渗透率 30-60% 且增速稳定
    - 衰退期: 渗透率 > 60% 但仍在增长
    - 退潮期: 渗透率 > 60% 且增速<5%或下滑

    辅助信号：
    - 营收增速: growth >20%, mature 5-20%, decline 0-5%, ebb <0%
    - 价格趋势: 成长期涨价/稳价, 退潮期持续跌价
    - 行业集中度(HHI): 成熟期集中度上升, 退潮期集中度下降(洗牌)

    Args:
        penetration_rate: 渗透率 % (0-100)
        revenue_growth: 行业营收增速 %
        industry_concentration_hhi: HHI指数 (可选, 0-10000)
        price_trend: "rising" | "stable" | "slowing" | "declining"

    Returns:
        Dict: {phase, phase_name, confidence, description, key_signals}
    """
    phase = None
    signals = []
    confidence = 0.80  # 初始置信度

    # 渗透率主判定
    if penetration_rate < 15.0:
        phase = LifecyclePhase.GROWTH
        signals.append(f"渗透率 {penetration_rate:.1f}% < 15% → 成长期")
    elif penetration_rate < 30.0 and revenue_growth > 25.0:
        phase = LifecyclePhase.GROWTH
        signals.append(f"渗透率 {penetration_rate:.1f}% 处于15-30%但增速 {revenue_growth:.1f}% > 25% → 成长期")
    elif penetration_rate < 60.0 and revenue_growth >= 5.0:
        phase = LifecyclePhase.MATURE
        signals.append(f"渗透率 {penetration_rate:.1f}% 处于30-60%且增速 {revenue_growth:.1f}% >= 5% → 成熟期")
    elif penetration_rate >= 60.0 and revenue_growth >= 0.0:
        phase = LifecyclePhase.DECLINE
        signals.append(f"渗透率 {penetration_rate:.1f}% >= 60% 且增速 {revenue_growth:.1f}% >= 0% → 衰退期")
    else:
        phase = LifecyclePhase.EBB
        signals.append(f"渗透率 {penetration_rate:.1f}% >= 60% 且增速 {revenue_growth:.1f}% < 0% → 退潮期")

    # 营收增速交叉验证
    if revenue_growth > 20.0 and phase != LifecyclePhase.GROWTH:
        confidence -= 0.10
        signals.append(f"营收增速 {revenue_growth:.1f}% > 20% 但主判定非成长期 → 置信度-0.10")
    elif revenue_growth < 0.0 and phase != LifecyclePhase.EBB:
        confidence -= 0.15
        signals.append(f"营收增速 {revenue_growth:.1f}% < 0% 但主判定非退潮期 → 置信度-0.15")

    # 价格趋势交叉验证
    if price_trend == "declining" and phase in [LifecyclePhase.GROWTH, LifecyclePhase.MATURE]:
        confidence -= 0.10
        signals.append("价格趋势持续下跌，与成长期/成熟期判定矛盾 → 置信度-0.10")
    elif price_trend == "rising" and phase == LifecyclePhase.EBB:
        confidence -= 0.15
        signals.append("价格趋势上涨，与退潮期判定矛盾 → 置信度-0.15")

    # HHI集中度验证（可选）
    if industry_concentration_hhi is not None:
        if industry_concentration_hhi > 2500 and phase == LifecyclePhase.MATURE:
            confidence += 0.05
            signals.append(f"HHI {industry_concentration_hhi} > 2500 高集中度 → 成熟期置信度+0.05")
        elif industry_concentration_hhi < 1500 and phase == LifecyclePhase.EBB:
            confidence += 0.05
            signals.append(f"HHI {industry_concentration_hhi} < 1500 低集中度(洗牌中) → 退潮期置信度+0.05")


    phase_meta = {
        LifecyclePhase.GROWTH: {
            "description": "渗透率快速提升阶段，技术迭代快，产能扩张激进。投资侧重成长型标的，关注技术路线和产能落地节奏。",
            "color": "#10b981",
            "investment_focus": "技术领先型成长标的",
        },
        LifecyclePhase.MATURE: {
            "description": "渗透率进入平台期，竞争格局稳定，龙头集中。投资侧重价值型龙头，关注成本控制和份额提升。",
            "color": "#3b82f6",
            "investment_focus": "成本领先型价值龙头",
        },
        LifecyclePhase.DECLINE: {
            "description": "渗透率见顶，增长放缓，结构性机会减少。谨慎参与，关注细分领域的差异化机会。",
            "color": "#f59e0b",
            "investment_focus": "细分差异化或转型标的",
        },
        LifecyclePhase.EBB: {
            "description": "渗透率过顶，行业收缩，价格战加剧。回避为主，仅关注供给侧出清后的反转机会。",
            "color": "#ef4444",
            "investment_focus": "供给侧出清后的反转机会",
        },
    }

    meta = phase_meta[phase]

    return {
        "phase": phase.value,
        "phase_name": phase.value,
        "confidence": round(confidence, 2),
        "description": meta["description"],
        "investment_focus": meta["investment_focus"],
        "color": meta["color"],
        "key_signals": signals,
        "penetration_rate": penetration_rate,
        "revenue_growth": revenue_growth,
    }


# ═══════════════════════════════════════════════════════════════
# 七、维度矛盾信号检测（V4.5 新增）
# ═══════════════════════════════════════════════════════════════

def detect_dimension_contradictions(
    cycle_score: float,
    supply_demand_score: float,
    policy_score: float,
    state_result: StateResult = None,
) -> List[Dict[str, any]]:
    """
    检测三维评分之间的逻辑矛盾信号

    矛盾规则（基于 V4.0 方法论 + 实盘验证）：
    1. 周期评分高(>75) + 供需评分低(<40): "周期上行但供需未跟" → 假繁荣风险
    2. 供需评分高(>75) + 政策评分低(<40): "供需紧但政策不支持" → 可持续性存疑
    3. 政策评分高(>75) + 周期评分低(<40): "政策强推但周期未起" → 政策驱动型/人造景气
    4. 三维度极差(>40分): "内部信号严重分化" → 产业链处于剧烈结构转换期
    5. 与五态判定矛盾: 三维均高但五态为Post → 数据异常或滞后期

    Args:
        cycle_score: 周期评分 0-100
        supply_demand_score: 供需评分 0-100
        policy_score: 政策评分 0-100
        state_result: 五态判定结果 (可选, 用于交叉验证)

    Returns:
        List[Dict]: 矛盾信号列表, 每个包含 {type, severity, description, suggestion}
    """
    contradictions = []

    # 矛盾1: 周期高 + 供需低
    if cycle_score > 75 and supply_demand_score < 40:
        contradictions.append({
            "type": "周期-供需背离",
            "severity": "high",
            "description": f"周期评分高({cycle_score:.0f})但供需评分低({supply_demand_score:.0f}) — 周期上行但供需基本面未跟上，可能存在假繁荣或资金推动型行情",
            "suggestion": "优先验证供需数据真实性，关注订单/产能利用率是否实质改善，警惕主题炒作",
        })

    # 矛盾2: 供需高 + 政策低
    if supply_demand_score > 75 and policy_score < 40:
        contradictions.append({
            "type": "供需-政策背离",
            "severity": "medium",
            "description": f"供需评分高({supply_demand_score:.0f})但政策评分低({policy_score:.0f}) — 供需紧平衡缺乏政策催化剂支撑，景气度可持续性存疑",
            "suggestion": "关注是否有政策催化剂蓄势待发，若无则缩短观察周期，等待信号收敛",
        })

    # 矛盾3: 政策高 + 周期低
    if policy_score > 75 and cycle_score < 40:
        contradictions.append({
            "type": "政策-周期背离",
            "severity": "medium",
            "description": f"政策评分高({policy_score:.0f})但周期评分低({cycle_score:.0f}) — 政策强推但行业周期未起，属于政策驱动型/人造景气",
            "suggestion": "判断政策力度能否扭转周期，强政策(如国家级战略)可博弈，弱政策(补贴退坡)则回避",
        })

    # 矛盾4: 三维度极差过大
    all_scores = [cycle_score, supply_demand_score, policy_score]
    score_range = max(all_scores) - min(all_scores)
    if score_range > 40:
        contradictions.append({
            "type": "三维度严重分化",
            "severity": "high",
            "description": f"三维度极差 {score_range:.0f} 分(>40) — 产业链处于剧烈结构转换期，各维度信号严重不一致",
            "suggestion": "产业链大概率处于范式切换期(如技术路线变更/政策转向)，建议增加观察期，等待信号收敛",
        })

    # 矛盾5: 与五态判定交叉验证
    if state_result is not None:
        avg_score = sum(all_scores) / 3
        if avg_score > 70 and state_result.state_code == "post":
            contradictions.append({
                "type": "评分-五态矛盾",
                "severity": "high",
                "description": f"三维均分 {avg_score:.0f} 较高但五态判定为「拐点后/衰退」— 数据可能存在滞后或异常，或行业处于结构性分化(部分环节衰退、部分繁荣)",
                "suggestion": "核查数据源时效性，细分产业链各环节分别评估，避免用平均数掩盖结构差异",
            })
        elif avg_score < 40 and state_result.state_code in ["confirmed", "late"]:
            contradictions.append({
                "type": "评分-五态矛盾",
                "severity": "high",
                "description": f"三维均分 {avg_score:.0f} 较低但五态判定为「拐点确认/晚期」— 信号严重矛盾，可能存在数据异常",
                "suggestion": "暂停基于该数据的决策，重新校验数据源，优先相信原始高频数据(价格/订单/产能)而非综合评分",
            })

    return contradictions


# ============================================================================
# 自测
# ============================================================================
# ═══════════════════════════════════════════════════════════════
# 统一测试入口
# ═══════════════════════════════════════════════════════════════

