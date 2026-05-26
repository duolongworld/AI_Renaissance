"""
自动检测股票所属产业链 preset
支持多轮查询，失败后降级
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 第一层：内置映射表（覆盖常见标的）
# ═══════════════════════════════════════════════════════════════

BUILT_IN_MAP = {
    # 光通信
    "300308.SZ": "optical-module",
    # "688313.SH": "optical-module",  # 已注释（保留历史映射记录）
    # "002428.SZ": "optical-module",  # 已注释（保留历史映射记录）
    # "688205.SH": "optical-module",  # 已注释（保留历史映射记录）
    "002281.SZ": "optical-module", "300502.SZ": "optical-module",
    "300620.SZ": "optical-module", "688498.SH": "optical-module",
    "688260.SH": "optical-module", "300548.SZ": "optical-module",
    "688195.SH": "optical-module", "688489.SH": "optical-module",
    "688167.SH": "optical-module", "688496.SH": "optical-module",
    "300946.SZ": "optical-module", "301221.SZ": "optical-module",
    "688061.SH": "optical-module", "688010.SH": "optical-module",
    "300691.SZ": "optical-module", "300657.SZ": "optical-module",
    "300709.SZ": "optical-module", "300936.SZ": "optical-module",
    "300739.SZ": "optical-module", "688195.SH": "optical-module",
    "300570.SZ": "optical-module", "688228.SH": "optical-module",
    "688498.SH": "optical-module", "688127.SH": "optical-module",
    "688165.SH": "optical-module", "300958.SZ": "optical-module",
    "688183.SH": "optical-module", "688609.SH": "optical-module",
    "300902.SZ": "optical-module", "300731.SZ": "optical-module",
    "300902.SZ": "optical-module", "300731.SZ": "optical-module",
    "300308.SZ": "optical-module", "002281.SZ": "optical-module",
    "300548.SZ": "optical-module", "688489.SH": "optical-module",
    "688260.SH": "optical-module", "300620.SZ": "optical-module",
    "300502.SZ": "optical-module",
    # "688205.SH": "optical-module",  # 已注释（保留历史映射记录）
    # "688313.SH": "optical-module",  # 已注释（保留历史映射记录）
    # "002428.SZ": "optical-module",  # 已注释（保留历史映射记录）
    # "300476.SZ": "ai-infrastructure",  # 示例PCB标的 → PCB/基础设施
    "002916.SZ": "ai-infrastructure",  # 深南电路
    "600183.SH": "ai-infrastructure",  # 生益科技
    "002384.SZ": "ai-infrastructure",  # 东山精密
    "601138.SH": "ai-infrastructure",  # 工业富联
    "603019.SH": "ai-chip",            # 中科曙光
    "688981.SH": "ai-chip",            # 中芯国际
    "688012.SH": "ai-chip",            # 中微公司
    "002371.SZ": "ai-chip",            # 北方华创
    "688008.SH": "ai-chip",            # 澜起科技
    "688256.SH": "ai-chip",            # 寒武纪
    "688041.SH": "ai-chip",            # 海光信息
    # "688521.SH": "ai-chip",            # 示例半导体标的（已注释）
    "300124.SZ": "ai-energy",          # 汇川技术
    "600885.SH": "ai-energy",          # 宏发股份
    "002028.SZ": "ai-energy",          # 思源电气
    "300274.SZ": "ai-energy",          # 阳光电源
    "002270.SZ": "robotics",           # 绿的谐波
    "603583.SH": "robotics",           # 拓普集团
    "002050.SZ": "robotics",           # 三花智控
    "002747.SZ": "robotics",           # 埃斯顿
    "688160.SH": "robotics",           # 步科股份
    "002979.SZ": "robotics",           # 科沃斯
    "603486.SH": "robotics",           # 石头科技
    "300222.SZ": "robotics",           # 科大智能
    "002896.SZ": "robotics",           # 中大力德
    "603666.SH": "robotics",           # 亿嘉和
    "300607.SZ": "robotics",           # 拓斯达
    "688017.SH": "robotics",           # 绿的谐波
    "002031.SZ": "robotics",           # 巨轮智能
    "002527.SZ": "robotics",           # 新时达
    "300278.SZ": "robotics",           # 华昌达
    "603895.SH": "robotics",           # 天准科技
    "688322.SH": "robotics",           # 奥比中光
}

# 行业关键词 → preset 映射
INDUSTRY_KEYWORDS = {
    "optical-module": ["光通信", "光模块", "光器件", "光纤", "光缆", "光芯片", "磷化铟", "硅光", "CW光源", "EML", "DSP", "AWG", "光互联"],
    "ai-chip": ["半导体", "集成电路", "芯片", "GPU", "ASIC", "HBM", "存储", "晶圆", "刻蚀", "光刻", "封测", "先进封装", "EDA"],
    "ai-infrastructure": ["PCB", "电路板", "服务器", "数据中心", "交换机", "网络设备", "液冷", "温控", "电源", "UPS", "连接器", "线缆"],
    "pcb": ["覆铜板", "CCL", "电子布", "铜箔", "载板", "HDI", "高多层"],
    "semiconductor-equipment": ["半导体设备", "光刻机", "刻蚀机", "薄膜沉积", "量测", "清洗设备", "CVD", "PVD", "ALD"],
    "storage": ["存储", "内存", "NAND", "DRAM", "HBM", "SSD", "闪存", "存储器"],
    "ai-energy": ["电力", "电网", "能源", "发电", "核电", "风电", "光伏", "储能", "变压器", "配电", "液冷", "温控", "散热"],
    "ai-model": ["大模型", "LLM", "AI模型", "训练", "推理", "开源模型", "语言模型", "多模态", "Agent"],
    "robotics": ["机器人", "减速器", "伺服", "电机", "执行器", "自动化", "工控", "智能制造", "人形机器人", "谐波", "RV减速器"],
}


def load_user_map(data_dir: Path) -> Dict[str, str]:
    """加载用户自定义映射表"""
    user_map_path = data_dir / "mappings" / "stock-to-preset.json"
    if user_map_path.exists():
        try:
            with open(user_map_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


# ═══════════════════════════════════════════════════════════════
# 第二层：通过 akshare 获取申万行业（如果环境有）
# ═══════════════════════════════════════════════════════════════

def query_akshare(stock_code: str) -> Optional[str]:
    """尝试用 akshare 查询行业分类"""
    try:
        import akshare as ak
        # 尝试获取股票基本信息
        df = ak.stock_individual_info_em(symbol=stock_code.replace(".SH", "").replace(".SZ", "").replace(".HK", ""))
        if df is not None and not df.empty:
            # 查找行业相关字段
            for col in df["item"]:
                val = df[df["item"] == col]["value"].values[0] if col in df["item"].values else ""
                if col in ["行业", "所属行业", "申万行业", "证监会行业", "所属概念"]:
                    return str(val)
    except Exception as e:
        logger.debug("akshare 查询失败: %s", e)
    return None


# ═══════════════════════════════════════════════════════════════
# 第三层：通过东方财富网页API获取行业
# ═══════════════════════════════════════════════════════════════

def query_eastmoney(stock_code: str) -> Optional[str]:
    """尝试通过东方财富API获取行业"""
    import urllib.request
    import urllib.error
    
    # 确定 secid
    if stock_code.endswith(".SH"):
        secid = f"1.{stock_code.replace('.SH', '')}"
    elif stock_code.endswith(".SZ"):
        secid = f"0.{stock_code.replace('.SZ', '')}"
    else:
        return None
    
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f100,f102"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("data"):
                # f100 通常是行业
                industry = data["data"].get("f100", "")
                if industry:
                    return industry
    except Exception as e:
        logger.debug("东方财富API查询失败: %s", e)
    return None


# ═══════════════════════════════════════════════════════════════
# 第四层：通过腾讯API获取名称，然后搜索行业
# ═══════════════════════════════════════════════════════════════

def query_tencent_name(stock_code: str) -> Optional[str]:
    """通过腾讯API获取股票名称"""
    import urllib.request
    
    prefix = "sh" if stock_code.endswith(".SH") else "sz"
    code = stock_code.replace(".SH", "").replace(".SZ", "")
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            # 尝试多种编码
            for enc in ["gb2312", "gbk", "utf-8"]:
                try:
                    text = content.decode(enc)
                    # 解析格式: v_sh600519="1~贵州茅台~600519~...
                    if "~" in text:
                        parts = text.split("~")
                        if len(parts) >= 3:
                            return parts[1]  # 股票名称
                    break
                except UnicodeDecodeError:
                    continue
    except Exception as e:
        logger.debug("腾讯API查询失败: %s", e)
    return None


# ═══════════════════════════════════════════════════════════════
# 行业名称 → preset 匹配
# ═══════════════════════════════════════════════════════════════

def match_preset_by_industry(industry_name: str) -> Optional[str]:
    """根据行业名称匹配 preset"""
    if not industry_name:
        return None
    
    industry_lower = industry_name.lower()
    
    for preset, keywords in INDUSTRY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in industry_lower:
                return preset
    
    return None


# ═══════════════════════════════════════════════════════════════
# 主入口：多轮查询
# ═══════════════════════════════════════════════════════════════

def auto_detect_preset(stock_code: str, data_dir: Path) -> Optional[str]:
    """
    自动检测股票所属 preset
    多轮查询：内置映射 → akshare → 东方财富 → 腾讯名称 → None
    """
    stock_code = stock_code.upper()
    
    # 轮1：内置映射表
    preset = BUILT_IN_MAP.get(stock_code)
    if preset:
        logger.info("[自动检测] %s → %s (内置映射)", stock_code, preset)
        return preset
    
    # 轮1.5：用户自定义映射
    user_map = load_user_map(data_dir)
    preset = user_map.get(stock_code)
    if preset:
        logger.info("[自动检测] %s → %s (用户映射)", stock_code, preset)
        return preset
    
    # 轮2：akshare
    industry = query_akshare(stock_code)
    if industry:
        preset = match_preset_by_industry(industry)
        if preset:
            logger.info("[自动检测] %s → %s (akshare: %s)", stock_code, preset, industry)
            return preset
    
    # 轮3：东方财富API
    industry = query_eastmoney(stock_code)
    if industry:
        preset = match_preset_by_industry(industry)
        if preset:
            logger.info("[自动检测] %s → %s (东方财富: %s)", stock_code, preset, industry)
            return preset
    
    # 轮4：腾讯API获取名称 + 名称关键词匹配
    name = query_tencent_name(stock_code)
    if name:
        preset = match_preset_by_industry(name)
        if preset:
            logger.info("[自动检测] %s → %s (名称匹配: %s)", stock_code, preset, name)
            return preset
    
    logger.warning("[自动检测] %s 无法自动识别行业，请手动指定 --preset", stock_code)
    return None


def auto_detect_preset_with_log(stock_code: str, data_dir: Path) -> tuple[Optional[str], list[str]]:
    """
    自动检测，同时返回查询日志
    用于 run.sh 展示给用户看查询过程
    """
    stock_code = stock_code.upper()
    logs = []
    
    # 轮1：内置映射
    logs.append(f"轮1: 查内置映射表...")
    preset = BUILT_IN_MAP.get(stock_code)
    if preset:
        logs.append(f"  ✅ 命中: {stock_code} → {preset}")
        return preset, logs
    logs.append(f"  ❌ 未命中")
    
    # 轮2：akshare
    logs.append(f"轮2: 查 akshare 申万行业...")
    industry = query_akshare(stock_code)
    if industry:
        logs.append(f"  ✅ 查到行业: {industry}")
        preset = match_preset_by_industry(industry)
        if preset:
            logs.append(f"  ✅ 匹配 preset: {preset}")
            return preset, logs
        logs.append(f"  ⚠️ 行业'{industry}'未匹配到已知preset")
    else:
        logs.append(f"  ❌ akshare 不可用或查询失败")
    
    # 轮3：东方财富
    logs.append(f"轮3: 查东方财富API...")
    industry = query_eastmoney(stock_code)
    if industry:
        logs.append(f"  ✅ 查到行业: {industry}")
        preset = match_preset_by_industry(industry)
        if preset:
            logs.append(f"  ✅ 匹配 preset: {preset}")
            return preset, logs
        logs.append(f"  ⚠️ 行业'{industry}'未匹配到已知preset")
    else:
        logs.append(f"  ❌ 东方财富API查询失败")
    
    # 轮4：腾讯API
    logs.append(f"轮4: 查腾讯API获取名称...")
    name = query_tencent_name(stock_code)
    if name:
        logs.append(f"  ✅ 查到名称: {name}")
        preset = match_preset_by_industry(name)
        if preset:
            logs.append(f"  ✅ 名称关键词匹配: {preset}")
            return preset, logs
        logs.append(f"  ⚠️ 名称'{name}'未匹配到已知preset")
    else:
        logs.append(f"  ❌ 腾讯API查询失败")
    
    logs.append(f"\n❌ 所有查询轮次均失败，请手动指定 --preset <preset名称>")
    logs.append(f"   可用preset (黄仁勋AI五层蛋糕): ")
    logs.append(f"     L1能源: ai-energy | L2芯片: ai-chip, semiconductor-equipment, storage")
    logs.append(f"     L3基础设施: optical-module, ai-infrastructure, pcb | L4模型: ai-model")
    logs.append(f"     L5应用: robotics")
    return None, logs


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        code = sys.argv[1]
        data_dir = Path(__file__).parent.parent / "data"
        preset, logs = auto_detect_preset_with_log(code, data_dir)
        for log in logs:
            print(log)
        if preset:
            print(f"\n结果: {preset}")
        else:
            print("\n结果: 未识别")
    else:
        print("用法: python3 auto_detect_preset.py <股票代码>")
        print("示例: python3 auto_detect_preset.py 002916.SZ")
