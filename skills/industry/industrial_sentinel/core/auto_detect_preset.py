"""
自动检测股票所属产业链 preset
支持多轮查询，失败后降级
"""

import json
import logging
import sys
import importlib.util
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# A 股代码格式补全：纯数字 → 带后缀
# ═══════════════════════════════════════════════════════════════

def _normalize_a_stock_code(code: str) -> str:
    """将纯数字 A 股代码补全为 'CODE.EXCHANGE' 格式。

    规则：
      - 已有 .SH/.SZ/.BJ/.HK 后缀 → 原样返回
      - 688xxx       → .SH (科创板)
      - 600/601/603/605xxx → .SH (上海主板)
      - 000-003xxx   → .SZ (深圳主板/中小板)
      - 300/301xxx   → .SZ (创业板)
      - 430-439/830-839/870-879/920-929xxx → .BJ (北交所)
      - 其他         → 原样返回（不做猜测）
    """
    code = code.strip().upper()
    if not code:
        return code
    if any(code.endswith(sfx) for sfx in (".SH", ".SZ", ".BJ", ".HK")):
        return code

    # 尝试按前缀规则补全
    digits = "".join(c for c in code if c.isdigit())
    if len(digits) < 6:
        return code  # 不是标准 A 股代码，原样返回

    prefix = digits[:3]
    if prefix.startswith("688"):
        return f"{digits}.SH"
    if prefix.startswith(("600", "601", "603", "605")):
        return f"{digits}.SH"
    if prefix.startswith(("000", "001", "002", "003")):
        return f"{digits}.SZ"
    if prefix.startswith(("300", "301")):
        return f"{digits}.SZ"
    if prefix.startswith(("430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839")):
        return f"{digits}.BJ"
    if prefix.startswith(("870", "871", "872", "873", "874", "875", "876", "877", "878", "879")):
        return f"{digits}.BJ"
    if prefix.startswith(("920", "921", "922", "923", "924", "925", "926", "927", "928", "929")):
        return f"{digits}.BJ"
    return code


def _lookup_code(code: str, mapping: dict) -> Optional[str]:
    """在映射表中查找代码，支持带后缀和纯数字两种格式。"""
    normalized = _normalize_a_stock_code(code)
    digits = "".join(c for c in normalized if c.isdigit())
    # 优先级：标准格式 → 纯数字
    for candidate in (normalized, digits):
        if candidate in mapping:
            return mapping[candidate]
    return None

# ═══════════════════════════════════════════════════════════════
# 股票名称 → 代码映射（用于本地 preset 路由）
# ═══════════════════════════════════════════════════════════════

def _is_stock_code(s: str) -> bool:
    """判断输入是否为股票代码（而非名称）。"""
    s = s.strip()
    if any(s.endswith(sfx) for sfx in (".SH", ".SZ", ".BJ", ".HK")):
        return True
    digits = "".join(c for c in s if c.isdigit())
    return len(digits) >= 6


STOCK_NAME_TO_CODE = {
    "中芯国际": "688981.SH", "中微公司": "688012.SH", "北方华创": "002371.SZ",
    "澜起科技": "688008.SH", "寒武纪": "688256.SH", "海光信息": "688041.SH",
    "芯原股份": "688521.SH", "通富微电": "002156.SZ", "长电科技": "600584.SH",
    "华虹半导体": "688347.SH", "沪硅产业": "688126.SH", "江丰电子": "300666.SZ",
    "深南电路": "002916.SZ", "生益科技": "600183.SH", "东山精密": "002384.SZ",
    "工业富联": "601138.SH", "沪电股份": "002463.SZ", "胜宏科技": "300476.SZ",
    "立讯精密": "002475.SZ", "浪潮信息": "000977.SZ", "中航光电": "002179.SZ",
    "中石科技": "300684.SZ", "华勤技术": "603296.SH", "锐捷网络": "301165.SZ",
    "德明利": "301309.SZ", "瑞芯微": "603893.SH",
    "中际旭创": "300308.SZ", "新易盛": "300502.SZ", "天孚通信": "300394.SZ",
    "光迅科技": "002281.SZ", "德科立": "688205.SH", "仕佳光子": "688313.SH",
    "源杰科技": "688498.SH", "长光华芯": "688048.SH", "光库科技": "300620.SZ",
    "太辰光": "300570.SZ", "博创科技": "300548.SZ", "联特科技": "301205.SZ",
    "剑桥科技": "603083.SH", "华工科技": "000988.SZ", "腾景科技": "688195.SH",
    "炬光科技": "688167.SH", "亨通光电": "600487.SH", "长飞光纤": "601869.SH",
    "烽火通信": "600498.SH", "中兴通讯": "000063.SZ",
    "阳光电源": "300274.SZ", "汇川技术": "300124.SZ", "思源电气": "002028.SZ",
    "国电南瑞": "600406.SH", "平高电气": "600312.SH", "许继电气": "000400.SZ",
    "中国西电": "601179.SH", "英维克": "002837.SZ", "高澜股份": "300499.SZ",
    "同飞股份": "300990.SZ", "科华数据": "002335.SZ", "科士达": "002518.SZ",
    "光环新网": "300383.SZ", "润泽科技": "300442.SZ", "伊戈尔": "002922.SZ",
    "绿的谐波": "688017.SH", "拓普集团": "601689.SH", "三花智控": "002050.SZ",
    "双环传动": "002472.SZ", "鸣志电器": "603728.SH", "柯力传感": "603662.SH",
    "奥比中光": "688322.SH", "石头科技": "688169.SH",
    "云南锗业": "002428.SZ", "罗博特科": "300757.SZ", "菲利华": "300395.SZ",
    "东田微": "301116.SZ", "永鼎股份": "600105.SH", "模塑科技": "000700.SZ",
    "埃斯顿": "002747.SZ", "步科股份": "688160.SH", "中大力德": "002896.SZ",
    "佰维存储": "688525.SH", "东芯股份": "688110.SH",
}


def _resolve_input(stock_code: str) -> str:
    """将输入解析为标准化的股票代码（名称→代码 或 代码标准化）。"""
    s = stock_code.strip()
    if _is_stock_code(s):
        return _normalize_a_stock_code(s.upper())
    # 精确名称匹配
    code = STOCK_NAME_TO_CODE.get(s)
    if code:
        return code
    # 模糊匹配
    s_clean = s.replace(" ", "").replace("(", "\uff08").replace(")", "\uff09")
    for name, code in STOCK_NAME_TO_CODE.items():
        if s_clean in name or name in s_clean:
            return code
    return _normalize_a_stock_code(s.upper())


# 导入名称关键词 → preset 路由映射
_spec = importlib.util.spec_from_file_location("name_preset_mapping", Path(__file__).parent / "name_preset_mapping.py")
_name_preset_module = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(Path(__file__).parent))
_spec.loader.exec_module(_name_preset_module)
NAME_TO_PRESET = _name_preset_module.NAME_TO_PRESET


# ═══════════════════════════════════════════════════════════════
# 第一层：本地 preset 路由表（覆盖常见标的）
# ═══════════════════════════════════════════════════════════════

LOCAL_PRESET_ROUTING_MAP = {
    # ── L2 芯片 (13) ──
    "688981.SH": "ai-chip",            # 中芯国际
    "688012.SH": "ai-chip",            # 中微公司
    "002371.SZ": "ai-chip",            # 北方华创
    "688008.SH": "ai-chip",            # 澜起科技
    "688256.SH": "ai-chip",            # 寒武纪
    "688041.SH": "ai-chip",            # 海光信息
    "688521.SH": "ai-chip",            # 芯原股份
    "002156.SZ": "ai-chip",            # 通富微电
    "600584.SH": "ai-chip",            # 长电科技
    "688347.SH": "ai-chip",            # 华虹半导体
    "688126.SH": "ai-chip",            # 沪硅产业
    "300666.SZ": "ai-chip",            # 江丰电子
    "603019.SH": "ai-chip",            # 中科曙光

    # ── L2 存储 (2) ──
    "688525.SH": "storage",            # 佰维存储
    "688110.SH": "storage",            # 东芯股份

    # ── L3 光通信 (30) ──
    "300308.SZ": "optical-module",     # 中际旭创
    "300502.SZ": "optical-module",     # 新易盛
    "300394.SZ": "optical-module",     # 天孚通信
    "002281.SZ": "optical-module",     # 光迅科技
    "688313.SH": "optical-module",     # 仕佳光子
    "002428.SZ": "optical-module",     # 云南锗业
    "688205.SH": "optical-module",     # 德科立
    "688498.SH": "optical-module",     # 源杰科技
    "688048.SH": "optical-module",     # 长光华芯
    "300620.SZ": "optical-module",     # 光库科技
    "688195.SH": "optical-module",     # 腾景科技
    "688167.SH": "optical-module",     # 炬光科技
    "300570.SZ": "optical-module",     # 太辰光
    "300548.SZ": "optical-module",     # 博创科技
    "301205.SZ": "optical-module",     # 联特科技
    "603083.SH": "optical-module",     # 剑桥科技
    "000988.SZ": "optical-module",     # 华工科技
    "600487.SH": "optical-module",     # 亨通光电
    "601869.SH": "optical-module",     # 长飞光纤
    "600498.SH": "optical-module",     # 烽火通信
    "000063.SZ": "optical-module",     # 中兴通讯
    "300739.SZ": "optical-module",     # 明阳电路
    "688010.SH": "optical-module",     # 福光股份
    "688127.SH": "optical-module",     # 蓝特光学
    "688183.SH": "optical-module",     # 生益电子
    "300731.SZ": "optical-module",     # 科创新源
    "688260.SH": "optical-module",     # 昀冢科技
    "688061.SH": "optical-module",     # 灿瑞科技
    "300691.SZ": "optical-module",     # 联合光电
    "688496.SH": "optical-module",     # 清越科技

    # ── L3 基础设施 (14) ──
    "002916.SZ": "ai-infrastructure",  # 深南电路
    "600183.SH": "ai-infrastructure",  # 生益科技
    "002384.SZ": "ai-infrastructure",  # 东山精密
    "601138.SH": "ai-infrastructure",  # 工业富联
    "002463.SZ": "ai-infrastructure",  # 沪电股份
    "300476.SZ": "ai-infrastructure",  # 胜宏科技
    "002475.SZ": "ai-infrastructure",  # 立讯精密
    "000977.SZ": "ai-infrastructure",  # 浪潮信息
    "002179.SZ": "ai-infrastructure",  # 中航光电
    "300684.SZ": "ai-infrastructure",  # 中石科技
    "603296.SH": "ai-infrastructure",  # 华勤技术
    "301165.SZ": "ai-infrastructure",  # 锐捷网络
    "301309.SZ": "ai-infrastructure",  # 德明利
    "603893.SH": "ai-infrastructure",  # 瑞芯微

    # ── L1 能源 (16) ──
    "300274.SZ": "ai-energy",          # 阳光电源
    "300124.SZ": "ai-energy",          # 汇川技术
    "002028.SZ": "ai-energy",          # 思源电气
    "600406.SH": "ai-energy",          # 国电南瑞
    "600312.SH": "ai-energy",          # 平高电气
    "000400.SZ": "ai-energy",          # 许继电气
    "601179.SH": "ai-energy",          # 中国西电
    "002837.SZ": "ai-energy",          # 英维克
    "300499.SZ": "ai-energy",          # 高澜股份
    "300990.SZ": "ai-energy",          # 同飞股份
    "002335.SZ": "ai-energy",          # 科华数据
    "002518.SZ": "ai-energy",          # 科士达
    "300383.SZ": "ai-energy",          # 光环新网
    "300442.SZ": "ai-energy",          # 润泽科技
    "600885.SH": "ai-energy",          # 宏发股份
    "002922.SZ": "ai-energy",          # 伊戈尔

    # ── L5 机器人 (13) ──
    "688017.SH": "robotics",           # 绿的谐波
    "601689.SH": "robotics",           # 拓普集团
    "002050.SZ": "robotics",           # 三花智控
    "002472.SZ": "robotics",           # 双环传动
    "603728.SH": "robotics",           # 鸣志电器
    "603662.SH": "robotics",           # 柯力传感
    "688322.SH": "robotics",           # 奥比中光
    "688169.SH": "robotics",           # 石头科技
    "002747.SZ": "robotics",           # 埃斯顿
    "688160.SH": "robotics",           # 步科股份
    "002896.SZ": "robotics",           # 中大力德
    "300607.SZ": "robotics",           # 拓斯达
    "002031.SZ": "robotics",           # 巨轮智能

    # ── 用户持仓补充 ──
    "300757.SZ": "ai-infrastructure",  # 罗博特科
    "000700.SZ": "robotics",           # 模塑科技
}

SUPPORTED_PRESETS = set(LOCAL_PRESET_ROUTING_MAP.values()) | {
    "ai-energy",
    "ai-chip",
    "semiconductor-equipment",
    "storage",
    "optical-module",
    "ai-infrastructure",
    "pcb",
    "ai-model",
    "robotics",
    "generic",
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
        except Exception as e:
            logger.debug("用户映射文件加载失败: %s", e)
    return {}


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

def auto_detect_preset(
    stock_code: str,
    data_dir: Path,
    allow_provider_lookup: bool = False,
) -> Optional[str]:
    """
    自动检测股票所属 preset。支持代码和名称。

    查询顺序：preset直传 → 名称/行业关键词 → 名称转代码 → 本地 preset 路由 → 用户映射。
    allow_provider_lookup 保留为兼容参数；外部 provider 识别统一由 data_sources/ 负责。
    """
    data_dir = Path(data_dir) if not isinstance(data_dir, Path) else data_dir
    direct_preset = stock_code.strip().lower()
    if direct_preset in SUPPORTED_PRESETS:
        logger.info("[自动检测] 输入为 preset: %s", direct_preset)
        return direct_preset

    # 轮0：名称识别（名称→preset 直接映射 + 名称→代码转换）
    if not _is_stock_code(stock_code):
        for name_key, preset in NAME_TO_PRESET.items():
            if name_key in stock_code:
                logger.info("[自动检测] 名称'%s' 匹配'%s' → %s", stock_code, name_key, preset)
                return preset
        preset = match_preset_by_industry(stock_code)
        if preset:
            logger.info("[自动检测] 行业关键词'%s' → %s", stock_code, preset)
            return preset
        resolved = _resolve_input(stock_code)
        if resolved != _normalize_a_stock_code(stock_code.upper()):
            logger.info("[自动检测] 名称'%s' → %s", stock_code, resolved)
            stock_code = resolved
        else:
            for name, code in STOCK_NAME_TO_CODE.items():
                if stock_code in name or name in stock_code:
                    logger.info("[自动检测] 模糊'%s' → %s", stock_code, code)
                    stock_code = code
                    break
    else:
        stock_code = _normalize_a_stock_code(stock_code.upper())

    # 轮1：本地 preset 路由表（支持带后缀和纯数字两种格式）
    preset = _lookup_code(stock_code, LOCAL_PRESET_ROUTING_MAP)
    if preset:
        logger.info("[自动检测] %s → %s (本地 preset 路由)", stock_code, preset)
        return preset

    # 轮1.5：用户自定义映射
    user_map = load_user_map(data_dir)
    preset = _lookup_code(stock_code, user_map)
    if preset:
        logger.info("[自动检测] %s → %s (用户映射)", stock_code, preset)
        return preset

    logger.warning("[自动检测] %s 未命中本地映射；外部 provider 识别请通过 data_sources 注入", stock_code)
    return None


def auto_detect_preset_with_log(
    stock_code: str,
    data_dir: Path,
    allow_provider_lookup: bool = False,
) -> tuple[Optional[str], list[str]]:
    """
    自动检测，同时返回查询日志。支持名称输入。
    """
    data_dir = Path(data_dir) if not isinstance(data_dir, Path) else data_dir
    logs = []
    direct_preset = stock_code.strip().lower()
    if direct_preset in SUPPORTED_PRESETS:
        logs.append(f"输入为 preset: {direct_preset}")
        return direct_preset, logs

    # 轮0：名称识别
    if not _is_stock_code(stock_code):
        logs.append(f"轮0: 检测到名称输入'{stock_code}'...")
        for name_key, preset in NAME_TO_PRESET.items():
            if name_key in stock_code:
                logs.append(f"  ✅ 名称关键字'{name_key}'匹配 → {preset}")
                return preset, logs
        preset = match_preset_by_industry(stock_code)
        if preset:
            logs.append(f"  ✅ 行业关键词匹配 → {preset}")
            return preset, logs
        resolved = _resolve_input(stock_code)
        if resolved != _normalize_a_stock_code(stock_code.upper()):
            logs.append(f"  ✅ 名称→代码: {resolved}")
            stock_code = resolved
        else:
            for name, code in STOCK_NAME_TO_CODE.items():
                if stock_code in name or name in stock_code:
                    logs.append(f"  ✅ 模糊名称→代码: {code}")
                    stock_code = code
                    break
    else:
        stock_code = _normalize_a_stock_code(stock_code.upper())

    # 轮1：本地 preset 路由表
    logs.append("轮1: 查本地 preset 路由表...")
    preset = _lookup_code(stock_code, LOCAL_PRESET_ROUTING_MAP)
    if preset:
        logs.append(f"  ✅ 命中: {stock_code} → {preset}")
        return preset, logs
    logs.append("  ❌ 未命中")

    logs.append("未命中本地映射；外部 provider 识别请通过 data_sources 注入，或补充本地映射。")
    logs.append("\n请手动指定 --preset <preset名称>，或在项目数据层补充行业识别结果。")
    logs.append("   可用preset (黄仁勋AI五层蛋糕): ")
    logs.append("     L1能源: ai-energy | L2芯片: ai-chip, semiconductor-equipment, storage")
    logs.append("     L3基础设施: optical-module, ai-infrastructure, pcb | L4模型: ai-model")
    logs.append("     L5应用: robotics")
    return None, logs


if __name__ == "__main__":
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
