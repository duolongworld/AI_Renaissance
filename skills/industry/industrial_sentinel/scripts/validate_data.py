#!/usr/bin/env python3
"""
Industrial Sentinel — 数据验证器

用法:
    python scripts/validate_data.py <stock_code>

功能:
    验证 real_data.json 是否符合标准格式，检查必填字段和数据质量。
    输出验证报告：通过/警告/错误。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DATA_DIR = Path(__file__).parent.parent / "data"


def _safe_num(value):
    """安全地将输入值转换为数字。兼容显式字符串占位（如「数据缺失」）。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        if v in ("数据缺失", "待补充", "待填写", "N/A", "—", "", "null", "None"):
            return None
        cleaned = v.replace("%", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


class DataValidator:
    """数据验证器"""
    
    # 必填字段定义
    REQUIRED_TOP_KEYS = [
        "stock_code", "stock_name", "industry", "preset",
        "chain_position", "data_source",
        "industry_signals", "industry_data", "lifecycle_indicators",
    ]
    
    REQUIRED_INDUSTRY_SIGNAL_KEYS = [
        "industry_market_growth", "industry_order_growth",
        "industry_capacity_utilization", "industry_price_yoy",
        "industry_inventory_days", "industry_capex_plan",
        "industry_policy_count"
    ]
    
    REQUIRED_INDUSTRY_DATA_FIELDS = ["metric", "value", "source", "source_type"]
    
    def __init__(self, data: Dict):
        self.data = data
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def validate(self) -> Tuple[bool, List[str], List[str], List[str]]:
        """执行完整验证，返回 (是否通过, 错误, 警告, 信息)"""
        self._validate_structure()
        self._validate_signals()
        self._validate_industry_data()
        self._validate_system_b()
        self._validate_data_quality()
        return len(self.errors) == 0, self.errors, self.warnings, self.info
    
    def _validate_structure(self):
        """验证顶层结构 — 缺数据不阻塞，降级为警告"""
        for key in self.REQUIRED_TOP_KEYS:
            if key not in self.data:
                self.warnings.append(f"缺少字段: {key}（可降级输出）")
        
        if "industry_signals" in self.data:
            signals = self.data["industry_signals"]
            for key in self.REQUIRED_INDUSTRY_SIGNAL_KEYS:
                if key not in signals:
                    self.warnings.append(f"industry_signals 缺少字段: {key}（五态判定可能不完整）")
        elif "real_signals" in self.data:
            self.warnings.append("使用旧 real_signals 结构；建议迁移到 industry_signals / peer_basket_signals / company_signals")
    
    def _validate_signals(self):
        """验证信号数据质量"""
        signals = self.data.get("industry_signals", {})
        
        # 检查数值字段 — 允许字符串"数据缺失"作为显式占位
        numeric_keys = [
            "industry_market_growth", "industry_order_growth",
            "industry_capacity_utilization", "industry_price_yoy",
            "industry_inventory_days",
        ]
        for key in numeric_keys:
            val = signals.get(key)
            if val is None:
                self.warnings.append(f"{key} = null（数据缺失，报告将显示「数据缺失」）")
            elif isinstance(val, str) and val.strip() == "数据缺失":
                # 显式占位，合法
                pass
            elif not isinstance(val, (int, float)):
                self.warnings.append(f"{key} 类型错误: {type(val).__name__}（应为数字或「数据缺失」）")
        
        # 检查来源标注
        for key in self.REQUIRED_INDUSTRY_SIGNAL_KEYS:
            source_key = f"{key}_source"
            if source_key not in signals:
                self.warnings.append(f"缺少来源标注: {source_key}")
            else:
                source = signals[source_key]
                if "待" in str(source) or "null" in str(source).lower():
                    self.warnings.append(f"{source_key} 未填写真实来源")
    
    def _validate_industry_data(self):
        """验证行业数据表格"""
        industry_data = self.data.get("industry_data", [])
        
        if len(industry_data) == 0:
            self.warnings.append("industry_data 为空（报告将缺少行业数据表格）")
        elif len(industry_data) < 3:
            self.warnings.append(f"industry_data 只有 {len(industry_data)} 项（建议至少5-8项）")
        
        for i, row in enumerate(industry_data):
            for field in self.REQUIRED_INDUSTRY_DATA_FIELDS:
                if field not in row:
                    self.errors.append(f"industry_data[{i}] 缺少字段: {field}")
            
            # 检查待补充标记
            val = row.get("value", "")
            if "待" in str(val) or str(val) == "":
                self.warnings.append(f"industry_data[{i}] ({row.get('metric', '?')}) 值未填写")
    
    def _validate_system_b(self):
        """验证System B输出"""
        system_b_type = self.data.get("system_b_type", "")
        if system_b_type in ["待判定", "", None]:
            self.warnings.append("system_b_type 未判定（报告将显示「数据缺失」）")
        
        core_contradiction = self.data.get("system_b_core_contradiction", "")
        if "待" in str(core_contradiction) or not core_contradiction:
            self.warnings.append("system_b_core_contradiction 未填写")
    
    def _validate_data_quality(self):
        """数据质量评估"""
        signals = self.data.get("industry_signals", {})
        filled_count = sum(1 for k in self.REQUIRED_INDUSTRY_SIGNAL_KEYS if signals.get(k) is not None)
        total_count = len(self.REQUIRED_INDUSTRY_SIGNAL_KEYS)
        
        self.info.append(f"信号填充率: {filled_count}/{total_count} ({filled_count/total_count*100:.0f}%)")
        
        if filled_count >= 6:
            self.info.append("信号数据充足，五态判定可信度高")
        elif filled_count >= 4:
            self.info.append("信号数据基本充足，五态判定可信度中等")
        elif filled_count >= 2:
            self.warnings.append("信号数据较少，五态判定可信度偏低")
        else:
            self.errors.append("信号数据严重不足，无法进行五态判定")
        
        # 检查是否有明显的数据矛盾
        industry_growth = _safe_num(signals.get("industry_market_growth"))
        peer_margin = _safe_num(self.data.get("peer_basket_signals", {}).get("gross_margin_median"))
        if industry_growth is not None and peer_margin is not None:
            if industry_growth > 30 and peer_margin < 10:
                self.warnings.append("行业需求高增(+30%+)但同业毛利率极低(<10%)，供需质量需核实")


def print_report(code: str, passed: bool, errors: List[str], warnings: List[str], info: List[str]):
    """打印验证报告"""
    print(f"\n{'='*60}")
    print(f"📋 数据验证报告 — {code}")
    print(f"{'='*60}")
    
    if passed and len(warnings) == 0:
        print(f"\n✅ 验证通过 — 数据完整，可直接生成报告")
    elif passed:
        print(f"\n⚠️ 验证通过（有警告）— 可生成报告，但建议补充以下数据：")
    else:
        print(f"\n❌ 验证失败 — 必须先修复以下错误：")
    
    if errors:
        print(f"\n【错误】({len(errors)}项)")
        for e in errors:
            print(f"  ❌ {e}")
    
    if warnings:
        print(f"\n【警告】({len(warnings)}项)")
        for w in warnings:
            print(f"  ⚠️ {w}")
    
    if info:
        print(f"\n【信息】")
        for i in info:
            print(f"  ℹ️ {i}")
    
    print(f"\n{'='*60}")
    if passed:
        print("💡 下一步: 运行 pipeline 生成报告")
        print(f"   python -c \"from core.pipeline import run_pipeline; run_pipeline('{code}')\"")
    else:
        print("💡 下一步: 补充缺失数据后再次验证")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="验证 数据文件")
    parser.add_argument("stock_code", help="股票代码")
    args = parser.parse_args()
    
    code = args.stock_code
    filepath = DATA_DIR / f"{code}_real_data.json"
    
    if not filepath.exists():
        print(f"❌ 文件不存在: {filepath}")
        print(f"💡 先生成模板: python scripts/generate_data_template.py {code}")
        sys.exit(1)
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ JSON解析失败: {e}")
        sys.exit(1)
    
    validator = DataValidator(data)
    passed, errors, warnings, info = validator.validate()
    print_report(code, passed, errors, warnings, info)
    
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
