"""
股票名称关键词 → preset 路由映射

覆盖逻辑：
  - 按preset分类，收录该行业常见公司名称关键词
  - 匹配时做子串匹配（如"伊戈尔"含"戈尔"→ai-energy）
  - 优先级：精确匹配 > 长关键词 > 短关键词
"""

# AI芯片层（半导体设计/制造/封测/IP）
AI_CHIP_NAMES = {
    # 芯片设计
    "芯原": "ai-chip", "寒武纪": "ai-chip", "海光": "ai-chip", "龙芯": "ai-chip",
    "兆易创新": "ai-chip", "韦尔": "ai-chip", "圣邦": "ai-chip", "卓胜微": "ai-chip",
    "紫光国微": "ai-chip", "复旦微电": "ai-chip", "澜起": "ai-chip",
    "瑞芯微": "ai-chip", "全志": "ai-chip", "晶晨": "ai-chip", "恒玄": "ai-chip",
    "乐鑫": "ai-chip", "中颖电子": "ai-chip", "国民技术": "ai-chip",
    "富瀚微": "ai-chip", "国科微": "ai-chip", "博通集成": "ai-chip",
    "翱捷": "ai-chip", "希荻微": "ai-chip", "艾为电子": "ai-chip",
    "敏芯": "ai-chip", "晶丰明源": "ai-chip", "必易微": "ai-chip",
    "力芯微": "ai-chip", "芯朋微": "ai-chip", "明微电子": "ai-chip",
    # 晶圆制造
    "中芯": "ai-chip", "华虹": "ai-chip",
    # 封测
    "长电": "ai-chip", "通富": "ai-chip", "华天": "ai-chip", "甬矽": "ai-chip",
    "晶方": "ai-chip", "颀中": "ai-chip", "汇成": "ai-chip",
    # 设备
    "北方华创": "ai-chip", "中微": "ai-chip", "拓荆": "ai-chip", "盛美": "ai-chip",
    "华海清科": "ai-chip", "芯源微": "ai-chip", "微导纳米": "ai-chip",
    "至纯科技": "ai-chip", "精测": "ai-chip", "长川": "ai-chip",
    "华峰测控": "ai-chip", "联动科技": "ai-chip", "金海通": "ai-chip",
    # 材料
    "沪硅": "ai-chip", "安集": "ai-chip", "鼎龙": "ai-chip", "江丰": "ai-chip",
    "华特气体": "ai-chip", "南大光电": "ai-chip", "上海新阳": "ai-chip",
    "晶瑞电材": "ai-chip", "江化微": "ai-chip", "飞凯材料": "ai-chip",
    "雅克科技": "ai-chip", "清溢光电": "ai-chip", "路维光电": "ai-chip",
    "广信材料": "ai-chip", "容大感光": "ai-chip",
    # IP/EDA
    "概伦电子": "ai-chip", "华大九天": "ai-chip", "广立微": "ai-chip",
}

# 光模块/光通信
OPTICAL_NAMES = {
    "中际旭创": "optical-module", "新易盛": "optical-module", "天孚通信": "optical-module",
    "光迅": "optical-module", "仕佳": "optical-module", "德科立": "optical-module",
    "源杰": "optical-module", "长光华芯": "optical-module", "光库": "optical-module",
    "太辰光": "optical-module", "博创": "optical-module", "联特": "optical-module",
    "剑桥": "optical-module", "华工": "optical-module", "腾景": "optical-module",
    "炬光": "optical-module", "亨通光电": "optical-module", "长飞": "optical-module",
    "烽火": "optical-module", "中兴通讯": "optical-module",
    "新易盛": "optical-module", "中瓷电子": "optical-module",
    "永鼎": "optical-module", "通鼎": "optical-module", "中天": "optical-module",
    "特发": "optical-module",
    # 锗/磷化铟材料
    "锗业": "optical-module", "云南锗业": "optical-module",
    "罗博特科": "ai-infrastructure", "菲利华": "optical-module",
    "东田微": "optical-module",
}

# AI基础设施（PCB/服务器/交换机/连接器）
INFRA_NAMES = {
    # PCB
    "深南电路": "ai-infrastructure", "生益科技": "ai-infrastructure",
    "东山精密": "ai-infrastructure", "胜宏": "ai-infrastructure",
    "沪电": "ai-infrastructure", "鹏鼎": "ai-infrastructure",
    "景旺电子": "ai-infrastructure", "崇达技术": "ai-infrastructure",
    "兴森科技": "ai-infrastructure", "明阳电路": "ai-infrastructure",
    "世运电路": "ai-infrastructure", "奥士康": "ai-infrastructure",
    "博敏电子": "ai-infrastructure", "超声电子": "ai-infrastructure",
    "天津普林": "ai-infrastructure", "中京电子": "ai-infrastructure",
    "科翔股份": "ai-infrastructure", "本川智能": "ai-infrastructure",
    "金禄电子": "ai-infrastructure", "满坤科技": "ai-infrastructure",
    "威尔高": "ai-infrastructure", "广合科技": "ai-infrastructure",
    # 服务器/交换机
    "工业富联": "ai-infrastructure", "浪潮": "ai-infrastructure",
    "中科曙光": "ai-infrastructure", "紫光股份": "ai-infrastructure",
    "锐捷": "ai-infrastructure", "菲菱科思": "ai-infrastructure",
    "共进股份": "ai-infrastructure",
    # 连接器/线缆
    "立讯": "ai-infrastructure", "中航光电": "ai-infrastructure",
    "意华股份": "ai-infrastructure", "华丰科技": "ai-infrastructure",
    "鼎通科技": "ai-infrastructure", "珠城科技": "ai-infrastructure",
    "徕木股份": "ai-infrastructure", "创益通": "ai-infrastructure",
    "沃尔核材": "ai-infrastructure", "神宇股份": "ai-infrastructure",
    "新亚电子": "ai-infrastructure", "兆龙互连": "ai-infrastructure",
    "金信诺": "ai-infrastructure",
    # 散热/液冷
    "中石": "ai-infrastructure", "飞荣达": "ai-infrastructure",
    "精研科技": "ai-infrastructure",
}

# AI能源层（电力设备/电网/液冷/电源/IDC）
ENERGY_NAMES = {
    # 变压器/输变电
    "思源电气": "ai-energy", "中国西电": "ai-energy", "平高": "ai-energy",
    "许继": "ai-energy", "特变电工": "ai-energy", "保变电气": "ai-energy",
    "望变电气": "ai-energy", "扬电科技": "ai-energy",
    "金盘科技": "ai-energy", "明阳电气": "ai-energy",
    "伊戈尔": "ai-energy",  # ← 电力电子变压器
    "三变科技": "ai-energy", "新特电气": "ai-energy",
    "顺钠股份": "ai-energy", "科林电气": "ai-energy",
    # 电网自动化
    "国电南瑞": "ai-energy", "东方电子": "ai-energy", "四方股份": "ai-energy",
    "国网信通": "ai-energy", "理工能科": "ai-energy",
    # 液冷/温控
    "英维克": "ai-energy", "高澜": "ai-energy", "同飞": "ai-energy",
    "申菱环境": "ai-energy", "佳力图": "ai-energy", "依米康": "ai-energy",
    # 电源/UPS/PDU
    "科华数据": "ai-energy", "科士达": "ai-energy", "中恒电气": "ai-energy",
    "易事特": "ai-energy", "雄韬股份": "ai-energy", "南都电源": "ai-energy",
    "圣阳股份": "ai-energy",
    # 光伏
    "阳光电源": "ai-energy", "隆基": "ai-energy", "通威": "ai-energy",
    "TCL中环": "ai-energy", "晶科": "ai-energy", "天合光能": "ai-energy",
    "晶澳": "ai-energy", "正泰电器": "ai-energy", "晶盛机电": "ai-energy",
    "迈为股份": "ai-energy", "捷佳伟创": "ai-energy", "奥特维": "ai-energy",
    "爱旭": "ai-energy", "钧达": "ai-energy",
    # 风电
    "金风": "ai-energy", "明阳智能": "ai-energy", "运达": "ai-energy",
    "三一重能": "ai-energy", "东方电缆": "ai-energy", "中天科技": "ai-energy",
    "亨通光电": "ai-energy", "起帆电缆": "ai-energy",
    # 储能
    "宁德时代": "ai-energy", "亿纬锂能": "ai-energy", "比亚迪": "ai-energy",
    "鹏辉能源": "ai-energy", "派能科技": "ai-energy", "德方纳米": "ai-energy",
    "湖南裕能": "ai-energy", "天赐材料": "ai-energy", "恩捷股份": "ai-energy",
    "星源材质": "ai-energy", "当升科技": "ai-energy", "容百科技": "ai-energy",
    "璞泰来": "ai-energy", "杉杉股份": "ai-energy", "中科电气": "ai-energy",
    "尚太科技": "ai-energy", "永兴材料": "ai-energy",
    # 核电
    "中国广核": "ai-energy", "中国核电": "ai-energy",
    # 电机/工控
    "汇川": "ai-energy", "卧龙电驱": "ai-energy", "江特电机": "ai-energy",
    "宏发": "ai-energy", "麦格米特": "ai-energy", "英搏尔": "ai-energy",
    # IDC
    "润泽": "ai-energy", "光环新网": "ai-energy", "数据港": "ai-energy",
    "奥飞数据": "ai-energy", "宝信软件": "ai-energy",
    "中国西电": "ai-energy", "国电南自": "ai-energy",
    # ODM/EMS（算力基础设施配套）
    "华勤": "ai-infrastructure", "闻泰": "ai-infrastructure",
    "龙旗": "ai-infrastructure", "与德": "ai-infrastructure",
    # 服务器/整机
    "浪潮": "ai-infrastructure", "中科曙光": "ai-infrastructure",
    "紫光股份": "ai-infrastructure", "中国长城": "ai-infrastructure",
    "拓维信息": "ai-infrastructure", "高新发展": "ai-infrastructure",
    "神州数码": "ai-infrastructure", "广电运通": "ai-infrastructure",
    # 铜连接/高速互联
    "沃尔核材": "ai-infrastructure", "神宇股份": "ai-infrastructure",
    "兆龙互连": "ai-infrastructure", "新亚电子": "ai-infrastructure",
    # CPO/光电共封装
    "罗博特科": "ai-infrastructure", "通宇通讯": "optical-module",
    # 激光设备
    "大族激光": "optical-module", "锐科激光": "optical-module",
    "杰普特": "optical-module", "帝尔激光": "optical-module",
    # AI应用/软件
    "科大讯飞": "ai-model", "昆仑万维": "ai-model", "万兴科技": "ai-model",
    "金山办公": "ai-model", "三六零": "ai-model", "拓尔思": "ai-model",
    "汉王科技": "ai-model", "云从科技": "ai-model", "商汤": "ai-model",
    "寒武纪": "ai-chip",  # 已在上面，去重
}

# 机器人
ROBOTICS_NAMES = {
    "绿的谐波": "robotics", "拓普": "robotics", "三花智控": "robotics",
    "埃斯顿": "robotics", "机器人": "robotics", "鸣志": "robotics",
    "柯力传感": "robotics", "双环传动": "robotics",
    "中大力德": "robotics", "步科": "robotics", "奥比中光": "robotics",
    "禾川": "robotics", "江苏雷利": "robotics", "五洲新春": "robotics",
    "贝斯特": "robotics", "鼎智科技": "robotics", "伟创电气": "robotics",
    "信捷电气": "robotics", "正弦电气": "robotics", "汇川": "robotics",
    "雷赛智能": "robotics", "拓斯达": "robotics", "埃夫特": "robotics",
    "凯尔达": "robotics", "新时达": "robotics", "科大智能": "robotics",
    "亿嘉和": "robotics", "申昊科技": "robotics", "景业智能": "robotics",
    "博实": "robotics", "巨轮": "robotics", "天准": "robotics",
    "凌云光": "robotics", "奥普特": "robotics", "矩子科技": "robotics",
    "机器视觉": "robotics", "精工科技": "robotics",
}

# 存储
STORAGE_NAMES = {
    "兆易创新": "storage", "佰维": "storage", "江波龙": "storage",
    "德明利": "storage", "朗科": "storage", "东芯": "storage",
    "普冉": "storage", "恒烁": "storage", "聚辰": "storage",
    "澜起": "storage",  # 内存接口芯片
    "北京君正": "storage", "协创数据": "storage",
}

# 合并为统一映射。该表只用于 preset 路由，不参与景气度打分。
NAME_TO_PRESET = {}
for d in [AI_CHIP_NAMES, OPTICAL_NAMES, INFRA_NAMES, ENERGY_NAMES, ROBOTICS_NAMES, STORAGE_NAMES]:
    NAME_TO_PRESET.update(d)

# 去重统计
if __name__ == "__main__":
    from collections import Counter
    presets = Counter(NAME_TO_PRESET.values())
    print(f"名称关键词映射总计: {len(NAME_TO_PRESET)} 个")
    print("Preset 分布:")
    for p, c in presets.most_common():
        print(f"  {p}: {c} 个")
