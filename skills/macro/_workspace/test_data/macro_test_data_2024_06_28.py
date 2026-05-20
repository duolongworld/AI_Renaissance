"""
Macro Agent 测试数据集 - 2024年6月28日

数据来源：
- 中国数据：国家统计局(NBS)、中国人民银行(PBOC)、海关总署、中国外汇交易中心(CFETS)
- 美国数据：BLS、ISM、BEA、NY Fed、Fed、美联储官网
- 大宗商品：LME、COMEX、DCE、Mysteel、南华期货
- 市场价格：Bloomberg、Wind、英为财情

参考来源：
- 华西证券《财经早餐 2024年6月28日》- 美债/原油/黄金/LME铜数据
- 申万宏源《6月28日申万早评》- 中国债市数据
- 长江有色金属网《6月沪铜月报》- 铁矿石月度均价
- NBS 7月10日发布：6月CPI/PPI数据
- PBOC 7月12日发布：6月金融数据
- BLS 7月5日发布：6月非农就业报告
- ISM 7月1日发布：6月ISM制造业PMI
- Mysteel《6月铁矿石数据汇总》- 62%澳粉月均$106.05
"""

from dataclasses import dataclass
from typing import Dict, Any


# =============================================================================
# 锚定时间点：2024年6月28日
# =============================================================================

REPORT_DATE = "2024-06-28"
TIMESTAMP = "2024-06-28T00:00:00"


# =============================================================================
# Layer 0: 双经济体追踪
# =============================================================================

CHINA_INDICATORS = {
    # ===== 增长维度 =====
    "growth": {
        # 统计局制造业PMI：2024年6月=49.5，低于50荣枯线
        # 来源：NBS，2024年6月30日发布
        "nbs_manufacturing_pmi": 49.5,
        # 财新制造业PMI：2024年6月=51.8，连续8个月处于扩张区间
        # 来源：Caixin/S&P Global，2024年7月1日发布
        "caixin_manufacturing_pmi": 51.8,
        # 工业增加值同比：6月约6.5%（前值6.1%）
        # 来源：NBS
        "industrial_added_value_yoy": 6.5,
        # GDP同比：一季度5.3%，二季度预计5.1%
        # 来源：NBS，季度发布
        "gdp_yoy": 5.1,
        # 出口同比（美元）：2024年6月约+8.0%（前值+7.6%），强劲
        # 来源：海关总署
        "export_yoy_usd": 8.0,
        # 社会消费品零售总额同比：2024年6月约+2.0%（前值+3.7%），消费偏弱
        # 来源：NBS
        "retail_sales_yoy": 2.0,
        # 非制造业PMI：2024年6月=50.5（前值54.4）
        # 来源：NBS
        "non_manufacturing_pmi": 50.5,
        # 新订单-产成品库存剪刀差：约3.5（需求-库存扩张）
        # 来源：NBS PMI分项数据
        "new_order_inventory_spread": 3.5,
    },

    # ===== 通胀维度 =====
    "inflation": {
        # CPI同比：2024年6月=0.2%（前值0.3%），需求疲弱
        # 来源：NBS，2024年7月10日发布
        "cpi_yoy": 0.2,
        # PPI同比：2024年6月=-0.8%（前值-3.6%），降幅持续收窄
        # 来源：NBS，2024年7月10日发布
        "ppi_yoy": -0.8,
        # 核心CPI：约0.5%（前值0.6%）
        # 来源：NBS
        "core_cpi_yoy": 0.5,
        # 南华工业品指数同比：6月跌幅-2.74%（上月+0.95%）
        # 来源：南华期货研究院
        "nh_industrial_index_yoy": -2.74,
        # 南华工业品指数点位：约2,850（6月末水平）
        # 来源：南华期货研究院
        "nh_industrial_index": 2850.0,
    },

    # ===== 政策维度 =====
    "policy": {
        # 1Y LPR：3.45%，6月维持不变（央行2024年2月下调后持稳）
        # 来源：PBOC，每月20日发布
        "1y_lpr": 3.45,
        # 5Y LPR：3.95%，6月维持不变
        # 来源：PBOC
        "5y_lpr": 3.95,
        # MLF利率：2.5%，6月维持不变（6月17日续作）
        # 来源：PBOC
        "mlf_rate": 2.5,
        # 7天逆回购利率：1.8%，6月维持不变
        # 来源：PBOC
        "repo_7d_rate": 1.8,
        # 降准幅度：0（2024年6月无降准）
        # 来源：PBOC
        "reserve_cut_bp": 0,
        # ===== 政策打分卡输入（用于 calculate_policy_score_from_text）=====
        # 6月政策环境：无超预期宽松信号，政治局会议强调"持续用力"
        # 以下为规则匹配参数
        "media_keywords": ["积极", "有力"],  # 国常会/央行表述
        "state_council_freq_change": 0,       # 频次无明显变化
        "pboc_keywords": ["稳健"],            # 货政报告措辞中性
        "top_meeting_signal": "none",         # 6月政治局会议无超常规信号
        "implementation_count": 0,            # 当期无重大新政策落地
    },

    # ===== 信用/流动性维度 =====
    "liquidity": {
        # DR007：6月末约1.75%（央行公开市场净投放800亿后回落）
        # 来源：CFETS
        "dr007": 1.75,
        # SHIBOR 3M：约1.95%（资金面平稳）
        # 来源：SHIBOR
        "shibor_3m": 1.95,
        # 社融存量同比：2024年6月=8.1%（前值8.4%），增速放缓
        # 来源：PBOC，2024年7月12日发布
        "tsf_yoy": 8.1,
        # M1同比：6月=-5.0%（前值-4.2%），企业活力低迷
        # 来源：PBOC
        "m1_yoy": -5.0,
        # M2同比：6月=6.2%（前值7.0%），货币派生减弱
        # 来源：PBOC
        "m2_yoy": 6.2,
        # 企业中长期贷款同比：约15%（企业中长贷仍保持增长）
        # 来源：PBOC
        "corp_mid_long_loan_yoy": 15.0,
        # 融资融券余额：约1.48万亿（A股杠杆资金平稳）
        # 来源：Wind
        "margin_balance_cny_bn": 14800.0,
    },

    # ===== 市场定价维度 =====
    "market_pricing": {
        # 10Y国债收益率：6月28日约2.23%（国债期货上涨，收益率回落）
        # 来源：申万宏源，2024年6月28日早评
        "10y_bond_yield": 2.23,
        # 2Y国债收益率：约1.92%（期限利差约31bp，曲线略陡峭化）
        # 来源：CFETS
        "2y_bond_yield": 1.92,
        # 沪深300指数：约3,500（6月末水平）
        # 来源：Wind
        "csi300_index": 3500.0,
        # 沪深300 ERP：约5.2%（盈利收益率vs无风险利率）
        # 来源：Wind
        "csi300_erp": 5.2,
        # 3Y AA中票信用利差：约65bp（企业融资成本仍高）
        # 来源：Wind
        "aa_credit_spread_bp": 65.0,
        # 3Y国债：约2.05%（用于信用利差计算）
        # 来源：Wind
        "3y_gov_bond_yield": 2.05,
    },
}


US_INDICATORS = {
    # ===== 增长维度 =====
    "growth": {
        # ISM制造业PMI：2024年6月=48.5%（前值48.7%），连续收缩
        # 来源：ISM，2024年7月1日发布
        "ism_manufacturing_pmi": 48.5,
        # ISM服务业PMI：2024年6月=48.8%（前值53.8%），大幅收缩
        # 来源：ISM，2024年7月3日发布
        "ism_services_pmi": 48.8,
        # 非农就业：6月+20.6万（前值21.8万），略低于预期
        # 来源：BLS，2024年7月5日发布
        "nonfarm_payrolls": 206000,
        # 失业率：6月=4.1%（前值4.0%），略有上升
        # 来源：BLS
        "unemployment_rate": 4.1,
        # GDP环比折年：一季度1.4%，二季度预计2.1%
        # 来源：BEA
        "gdp_growth_qoq_annualized": 2.1,
        # 初申失业金人数：约23.5万（4周均值）
        # 来源：DOL
        "initial_jobless_claims_4w_avg": 235000,
    },

    # ===== 通胀维度 =====
    "inflation": {
        # PCE同比：6月约2.6%（前值2.7%），接近目标但仍偏高
        # 来源：BEA
        "pce_yoy": 2.6,
        # 核心PCE同比：6月约2.6%（前值2.8%），通胀粘性
        # 来源：BEA
        "core_pce_yoy": 2.6,
        # CPI同比：6月=3.0%（前值3.4%），明显回落
        # 来源：BLS
        "cpi_yoy": 3.0,
        # 核心CPI同比：6月约3.4%（前值3.6%）
        # 来源：BLS
        "core_cpi_yoy": 3.4,
        # ECI工资增速：6月约0.2%QoQ（劳动力市场紧张缓解中）
        # 来源：BLS
        "eci_wage_qoq": 0.2,
        # 5Y5Y通胀互换/Breakeven：约2.3%（长期通胀预期稳定锚定）
        # 来源：Bloomberg
        "breakeven_5y5y": 2.3,
    },

    # ===== 政策维度 =====
    "policy": {
        # FFR目标利率：5.25%，6月FOMC维持不变
        # 来源：Fed，2024年6月12日FOMC会议
        "ffr": 5.25,
        # 美联储总资产：约7.35万亿美元（6月末，周度数据）
        # 来源：Fed H.4.1
        "fed_total_assets_usd": 7.35e12,
    },

    # ===== 流动性维度 =====
    "liquidity": {
        # SOFR：6月末约5.32%（略高于FFR目标上界）
        # 来源：NY Fed
        "sofr": 5.32,
        # EFFR：约5.33%
        # 来源：NY Fed
        "effr": 5.33,
        # M2同比：6月约-0.3%（连续收缩，流动性收紧）
        # 来源：Fed
        "m2_yoy": -0.3,
    },

    # ===== 市场定价维度 =====
    "market_pricing": {
        # 10Y UST收益率：6月28日约4.29%（FOMC后小幅回落）
        # 来源：华西证券财经早餐，2024年6月28日
        "10y_ust_yield": 4.29,
        # 2Y UST收益率：6月28日约4.71%
        # 来源：华西证券财经早餐
        "2y_ust_yield": 4.71,
        # S&P 500指数：约5,460（6月末水平）
        # 来源：Bloomberg
        "sp500_index": 5460.0,
        # S&P 500 ERP：约2.1%（盈利收益率vs无风险利率）
        # 来源：Bloomberg
        "sp500_erp": 2.1,
        # US IG利差：约120bp（信用环境尚可）
        # 来源：ICE BofA
        "us_ig_spread_bp": 120.0,
        # US HY利差：约380bp（高收益债利差走阔）
        # 来源：ICE BofA
        "us_hy_spread_bp": 380.0,
    },
}


CROSS_BORDER_METRICS = {
    # ===== 汇率 =====
    "exchange_rate": {
        # USD/CNH即期：6月28日约7.27（6月从7.24小幅走贬）
        # 来源：HKMA/CNBC
        "usd_cnh": 7.27,
        # USD/CNY即期：约7.27（CNH与CNY基本持平）
        # 来源：CFETS
        "usd_cny": 7.27,
        # CNH-CNY价差：约5bp（离岸略弱于在岸，幅度正常）
        # 来源：HKMA
        "cnh_cny_spread_bp": 5.0,
        # USD/CNY中间价：约7.12（央行维稳信号）
        # 来源：PBOC
        "usd_cny_mid_rate": 7.12,
        # 央行中间价偏离度：(7.27-7.12)/7.12 ≈ +2.1%（显著强于中间价）
        # 来源：PBOC计算
        "pboc_mid_rate_deviation_pct": 2.1,
        # 人民币期权25Δ Risk Reversal：约0.5%（贬值预期轻微）
        # 来源：Bloomberg
        "cny_rr_25d": 0.5,
        # 外储月度变化：6月约-73亿美元（2024年上半年外储下降）
        # 来源：SAFE，2024年7月外储数据
        "forex_reserve_change_usd_bn": -73,
        # 外储余额：约3.15万亿美元（2024年6月末）
        # 来源：SAFE
        "forex_reserve_usd_bn": 3150,
        # 贸易顺差（海关口径）：6月约841亿美元（强劲出口）
        # 来源：海关总署
        "trade_surplus_usd_bn": 841,
    },

    # ===== 利率利差 =====
    "interest_rate": {
        # 中美10Y利差：2.23% - 4.29% = -206bp（倒挂加深）
        # 来源：CFETS/Bloomberg
        "cn_us_10y_spread_bp": -206,
        # 中美10Y利差（%）：约-2.06%
        "cn_us_10y_spread_pct": -2.06,
        # 中国10Y：2.23%，美国10Y：4.29%
        "cn_10y_yield": 2.23,
        "us_10y_yield": 4.29,
    },

    # ===== 资本流动 =====
    "capital_flow": {
        # 北向资金月净流入：6月约+200亿（接近有效流入阈值下限）
        # 来源：HKEX
        "northbound_flow_cny_bn": 200,
    },

    # ===== 风险偏好 =====
    "risk": {
        # VIX：6月28日约12.4（市场恐慌情绪较低）
        # 来源：CBOE/Bloomberg
        "vix": 12.4,
        # Sahm Rule衰退预警：0.1 < 0.5，未触发衰退预警
        # 来源：BLS/NY Fed计算
        "sahm_rule_value": 0.1,
        "sahm_rule_triggered": False,
    },

    # ===== 外部增长代理 =====
    "global_growth": {
        # 全球制造业PMI：2024年6月约50.3（勉强扩张）
        # 来源：JPMorgan/Bloomberg
        "global_manufacturing_pmi": 50.3,
        # 欧元区制造业PMI：2024年6月约45.8（深度收缩）
        # 来源：HCOB/S&P Global
        "euro_manufacturing_pmi": 45.8,
    },
}


# =============================================================================
# Layer 2.5: 大宗商品数据
# =============================================================================

COMMODITY_DATA = {
    # ===== 绝对价格 =====
    # LME铜3个月期货：6月28日收盘$9,514/吨（约$9,519开盘）
    # 来源：金投期货网，2024年6月28日
    "lme_copper_3m_usd_ton": 9514.0,
    # COMEX黄金8月期货：6月28日收盘$2,336.6/盎司
    # 来源：华西证券财经早餐，2024年6月28日
    "comex_gold_usd_oz": 2336.6,
    # 布伦特原油8月期货：6月28日收盘$86.39/桶
    # 来源：华西证券财经早餐
    "brent_oil_usd_bbl": 86.39,
    # WTI原油8月期货：6月28日收盘$81.74/桶
    # 来源：华西证券财经早餐
    "wti_oil_usd_bbl": 81.74,
    # 铁矿石62%普氏指数：6月月均$106.05/干吨（环比下跌$11.45）
    # 来源：Mysteel《6月铁矿石数据汇总》
    "iron_ore_62_fe_usd_dmt": 106.05,
    # DCE铁矿石期货：6月末约820-840元/吨（期货主力合约）
    # 来源：DCE
    "dce_iron_ore_cny_ton": 830.0,
    # CBOT大豆：6月末约1,100美分/蒲式耳
    # 来源：CBOT
    "cboy_soybean_usd_bu": 1100.0,
    # CBOT玉米：6月末约450美分/蒲式耳
    # 来源：CBOT
    "cboy_corn_usd_bu": 450.0,
    # 南华工业品指数：6月末约2,850（6月跌幅-2.74%）
    # 来源：南华期货研究院
    "nh_industrial_index": 2850.0,
    # 南华能化指数：6月跌幅-0.85%
    "nh_energy_chem_index": 2400.0,

    # ===== 商品比值信号（框架原文第655-668行定义）=====
    # 1. 铜金比 = LME铜($9,514/t) / COMEX黄金($2,336.6/oz)
    #    换算：铜$9,514/t ÷ 35.274 = $269.7/oz；269.7 ÷ 2336.6 ≈ 0.1154
    "copper_gold_ratio": round(9514.0 / (2336.6 / 35.274), 4),  # ≈ 0.1154
    # 2. 油金比 = 布伦特($86.39/bbl) / COMEX黄金($2,336.6/oz)
    #    换算：86.39 × 0.007493 = $0.647/oz；0.647 ÷ 2336.6 ≈ 0.000277
    "oil_gold_ratio": round(86.39 * 0.007493 / (2336.6 / 35.274), 6),  # ≈ 0.000277
    # 3. 铁矿石/铜比 = DCE铁矿石(¥830/t) / LME铜($9,514/t × 7.27)
    #    换算：¥830 ÷ ($9,514 × 7.27) = 830 ÷ 69,167 ≈ 0.012
    "iron_copper_ratio": round(830.0 / (9514.0 * 7.27), 4),  # ≈ 0.012
    # 4. 大豆/玉米比 = CBOT大豆($1,100/bu) / CBOT玉米($450/bu)
    "soybean_corn_ratio": round(1100.0 / 450.0, 4),  # ≈ 2.444
    # 5. 黄金vs实际利率 = COMEX黄金($2,336.6) / (10Y TIPS ≈ 2.0%)
    #    框架定义：黄金/10Y TIPS收益率(取负)背离=避险
    #    实际TIPS 6月末约2.0%，黄金/2.0 ≈ 1,168（z-score需计算）
    "gold_vs_real_rate": round(2336.6 / 2.0, 2),  # ≈ 1168
    # 6. 南华vs全球PMI = 南华指数同比 / 全球PMI = (-2.74%) / 50.3
    "nh_global_pmi_ratio": round(-2.74 / 50.3, 4),  # ≈ -0.0545
}


# =============================================================================
# Layer 2: 政策维度数据
# =============================================================================

CHINA_POLICY_INDICATORS = {
    # 货币政策宽松程度评分输入
    # 6月：DR007=1.75%处于政策利率1.8%下方，资金面偏松
    # MLF/LPR维持不变，无降息信号
    "monetary_policy": "easy",  # DR007低于政策利率，流动性偏松

    # 财政政策评分输入
    # 6月：专项债发行加速（上半年新增专项债2.3万亿）
    # 但整体财政扩张力度温和，未达"超常规"门槛
    "fiscal_policy": "neutral",  # 财政温和扩张，无强刺激

    # 地产政策评分输入
    # 6月：多地限购限贷优化，央行允许利率下浮
    # 但整体地产仍在深度调整，未见强力托底
    "real_estate_policy": "neutral",  # 边际优化，非全面宽松

    # 监管事件
    # 6月：资本市场监管平稳，无重大监管事件
    "regulation_event": "neutral",  # 无重大监管事件

    # ===== 专项数据（用于 Layer 2 单独分析）=====
    # 专项债发行进度：上半年2.3万亿（全年目标约3.9万亿），进度59%
    # 来源：MoF
    "special_bond_progress_pct": 59.0,
    # 财政赤字率：2024年目标3%（上半年约1.5%）
    # 来源：MoF
    "fiscal_deficit_rate_pct": 3.0,
    # 特别国债：6月无新增特别国债发行（特别国债于5月启动）
    "special_bond_count_jun": 0,
}


# =============================================================================
# Layer 3: 市场定价数据
# =============================================================================

MARKET_PRICING_DATA = {
    # ===== A股市场情绪 =====
    "csi300_index": 3500.0,
    "csi300_forward": 3495.0,  # 期货略贴水
    "csi300_put": 12.5,          # 6月末300ETF期权隐含波动率（近似）
    "csi300_call": 11.8,         # 300ETF看涨期权（略低于看跌）
    # P/C比率 = 12.5/11.8 ≈ 1.06（谨慎偏空，但未极端）
    "pc_ratio": round(12.5 / 11.8, 3),

    # ===== 国债市场情绪 =====
    # 国债期货10Y持仓量变化：6月末有所增加（机构降息预期升温）
    "gov_bond_10y_holding_change": 5000,  # 合约持仓量变化（手）
    "chinese_10y_fut": 102.5,  # 10Y国债期货价格（净价）

    # ===== 期限利差 =====
    # 中国：10Y-2Y = 2.23% - 1.92% = 31bp（曲线略陡峭）
    "cn_10y_2y_spread_bp": 31.0,
    # 美国：10Y-2Y = 4.29% - 4.71% = -42bp（倒挂中）
    "us_10y_2y_spread_bp": -42.0,

    # ===== 港A股估值差 =====
    # 恒生AH溢价指数：约135（A股相对H股溢价35%）
    # 来源：HKEX
    "hshare_ah_spread": 135.0,

    # ===== 大宗商品远月/近月（库存周期代理）=====
    "copper_near_usd_ton": 9514.0,
    "copper_far_usd_ton": 9475.0,  # 3M期货略低于现货（Backwardation）
    "oil_near_usd_bbl": 86.39,
    "oil_far_usd_bbl": 84.50,      # 12M期货低于现货
}


# =============================================================================
# Layer 4: 预期差数据
# =============================================================================

EXPECTED_DIFF_DATA = {
    # 中国数据意外指数（CESI）：6月约+10（数据持续好于预期）
    # 来源：Bloomberg/Wind
    "china_surprise_index": 10.0,
    # 美国Citi经济意外指数：6月约-15（数据持续不及预期）
    # 来源：Citi/Bloomberg
    "us_surprise_index": -15.0,
    # Fed Funds Futures隐含利率（12月）：约4.9%（市场定价1次降息25bp）
    # 来源：Bloomberg
    "ff_implied_rate_dec24": 4.90,
}


# =============================================================================
# Layer 4.5: 反身性数据
# =============================================================================

REFLEXIVITY_DATA = {
    # 信号拥挤度
    # CFTC非商业持仓（铜期货）：6月末净多头约30%（较高拥挤度）
    # 来源：CFTC
    "cftc_net_position_pct": 30.0,
    # ETF资金流：6月A股ETF净流入约+500亿（流入较多）
    # 来源：Bloomberg
    "etf_flow_cny_bn": 500.0,
    # 北向资金（与Layer 0共用）：+200亿
    "northbound_flow_cny_bn": 200.0,
    # 综合信号拥挤度评分（0-100）
    "signal_crowding_score": 45.0,
    # 仓位集中度（z-score）：约+0.8
    "position_concentration_z": 0.8,
    # 信号自我实现指数：约50
    "self_fulfilling_index": 50.0,
    # 跨框架一致性：约55（买方分歧较大）
    "cross_framework_consensus": 55.0,
    # 卖方策略报告：主要券商对A股观点约60%偏谨慎
    # 来源：各券商研报综合
    "sell_side_bearish_pct": 60.0,
    # 买方策略报告：约55%偏谨慎
    "buy_side_bearish_pct": 55.0,
}


# =============================================================================
# Layer 0 通道6专用：地缘政治评分
# =============================================================================

GEOPOLITICAL_DATA = {
    # 地缘政治综合评分（0-10）：2024年6月末约4.5分
    # 评估依据：
    # - US-China贸易/科技战（TikTok剥离令、关税上调）：+2.0
    # - 中东（以色列-哈马斯停火谈判进展缓慢）：+1.0
    # - 俄乌（持续冲突，但未升级）：+0.5
    # - 朝鲜半岛（朝俄走近）：+0.5
    # - 南海/台海（相对平静）：+0.0
    # - 其他（供应链重构风险）：+0.5
    "geopolitical_score": 4.5,
    "detail": {
        "us_china_tension": 2.0,
        "middle_east": 1.0,
        "russia_ukraine": 0.5,
        "korean_peninsula": 0.5,
        "south_china_sea": 0.0,
        "supply_chain_risk": 0.5,
    }
}


# =============================================================================
# 汇总：完整 Mock 数据（与 Agent._fetch_macro_data 格式一致）
# =============================================================================

def build_complete_mock_data() -> Dict[str, Any]:
    """
    构建与 Agent._fetch_macro_data 返回格式完全一致的完整 Mock 数据集。
    用于测试时直接替换 agent.py 中的 _fetch_macro_data 返回值。
    """
    # 中美10Y利差
    cn_10y = CHINA_INDICATORS["market_pricing"]["10y_bond_yield"]
    us_10y = US_INDICATORS["market_pricing"]["10y_ust_yield"]
    cn_us_10y_spread = round(cn_10y - us_10y, 2)

    # 铜金比
    copper_gold = COMMODITY_DATA["copper_gold_ratio"]
    # 油金比
    oil_gold = COMMODITY_DATA["oil_gold_ratio"]

    return {
        "_is_mock": True,
        "_report_date": REPORT_DATE,
        "_data_sources": "基于2024年6月28日真实宏观数据整理",

        # ===== 中国数据 =====
        "china": {
            # 增长
            "nbs_manufacturing_pmi": CHINA_INDICATORS["growth"]["nbs_manufacturing_pmi"],
            "caixin_manufacturing_pmi": CHINA_INDICATORS["growth"]["caixin_manufacturing_pmi"],
            "non_manufacturing_pmi": CHINA_INDICATORS["growth"]["non_manufacturing_pmi"],
            "industrial_added_value_yoy": CHINA_INDICATORS["growth"]["industrial_added_value_yoy"],
            "gdp_yoy": CHINA_INDICATORS["growth"]["gdp_yoy"],
            "retail_sales_yoy": CHINA_INDICATORS["growth"]["retail_sales_yoy"],
            "export_yoy_usd": CHINA_INDICATORS["growth"]["export_yoy_usd"],
            "new_order_inventory_spread": CHINA_INDICATORS["growth"]["new_order_inventory_spread"],
            # 通胀
            "cpi_yoy": CHINA_INDICATORS["inflation"]["cpi_yoy"],
            "ppi_yoy": CHINA_INDICATORS["inflation"]["ppi_yoy"],
            "core_cpi_yoy": CHINA_INDICATORS["inflation"]["core_cpi_yoy"],
            "nh_industrial_index_yoy": CHINA_INDICATORS["inflation"]["nh_industrial_index_yoy"],
            "nh_industrial_index": CHINA_INDICATORS["inflation"]["nh_industrial_index"],
            # 信用/流动性
            "tsf_yoy": CHINA_INDICATORS["liquidity"]["tsf_yoy"],
            "m1_yoy": CHINA_INDICATORS["liquidity"]["m1_yoy"],
            "m2_yoy": CHINA_INDICATORS["liquidity"]["m2_yoy"],
            "corp_mid_long_loan_yoy": CHINA_INDICATORS["liquidity"]["corp_mid_long_loan_yoy"],
            "dr007": CHINA_INDICATORS["liquidity"]["dr007"],
            "shibor_3m": CHINA_INDICATORS["liquidity"]["shibor_3m"],
            "margin_balance": CHINA_INDICATORS["liquidity"]["margin_balance_cny_bn"] * 1e8,
            # 政策
            "1y_lpr": CHINA_INDICATORS["policy"]["1y_lpr"],
            "5y_lpr": CHINA_INDICATORS["policy"]["5y_lpr"],
            "mlf_rate": CHINA_INDICATORS["policy"]["mlf_rate"],
            "repo_7d_rate": CHINA_INDICATORS["policy"]["repo_7d_rate"],
            "reserve_cut_bp": CHINA_INDICATORS["policy"]["reserve_cut_bp"],
            # 市场定价
            "cn_10y_yield": CHINA_INDICATORS["market_pricing"]["10y_bond_yield"],
            "cn_2y_yield": CHINA_INDICATORS["market_pricing"]["2y_bond_yield"],
            "csi300_erp": CHINA_INDICATORS["market_pricing"]["csi300_erp"],
            "aa_credit_spread": CHINA_INDICATORS["market_pricing"]["aa_credit_spread_bp"] / 100,
            # Layer 2 政策维度
            "monetary_policy_direction": CHINA_POLICY_INDICATORS["monetary_policy"],
            "fiscal_policy_direction": CHINA_POLICY_INDICATORS["fiscal_policy"],
            "real_estate_policy_direction": CHINA_POLICY_INDICATORS["real_estate_policy"],
            "regulation_event": CHINA_POLICY_INDICATORS["regulation_event"],
            "special_bond_progress": CHINA_POLICY_INDICATORS["special_bond_progress_pct"],
            "fiscal_deficit_rate": CHINA_POLICY_INDICATORS["fiscal_deficit_rate_pct"],
            # Layer 3
            "csi300_index": MARKET_PRICING_DATA["csi300_index"],
            "csi300_forward": MARKET_PRICING_DATA["csi300_forward"],
            "csi300_put": MARKET_PRICING_DATA["csi300_put"],
            "csi300_call": MARKET_PRICING_DATA["csi300_call"],
            "pc_ratio": MARKET_PRICING_DATA["pc_ratio"],
        },

        # ===== 美国数据 =====
        "us": {
            # 增长
            "ism_manufacturing_pmi": US_INDICATORS["growth"]["ism_manufacturing_pmi"],
            "ism_services_pmi": US_INDICATORS["growth"]["ism_services_pmi"],
            "nonfarm_payrolls": US_INDICATORS["growth"]["nonfarm_payrolls"],
            "us_unemployment_rate": US_INDICATORS["growth"]["unemployment_rate"],
            "gdp_growth": US_INDICATORS["growth"]["gdp_growth_qoq_annualized"],
            "initial_jobless_claims_4w_avg": US_INDICATORS["growth"]["initial_jobless_claims_4w_avg"],
            # 通胀
            "core_pce_yoy": US_INDICATORS["inflation"]["core_pce_yoy"],
            "cpi_yoy": US_INDICATORS["inflation"]["cpi_yoy"],
            "core_cpi_yoy": US_INDICATORS["inflation"]["core_cpi_yoy"],
            "eci_wage_qoq": US_INDICATORS["inflation"]["eci_wage_qoq"],
            "breakeven_5y5y": US_INDICATORS["inflation"]["breakeven_5y5y"],
            # 政策
            "ffr": US_INDICATORS["policy"]["ffr"],
            "fed_total_assets": US_INDICATORS["policy"]["fed_total_assets_usd"],
            # 流动性
            "sofr": US_INDICATORS["liquidity"]["sofr"],
            "effr": US_INDICATORS["liquidity"]["effr"],
            "m2_yoy": US_INDICATORS["liquidity"]["m2_yoy"],
            # 市场定价
            "us_10y_yield": US_INDICATORS["market_pricing"]["10y_ust_yield"],
            "us_2y_yield": US_INDICATORS["market_pricing"]["2y_ust_yield"],
            "sp500_erp": US_INDICATORS["market_pricing"]["sp500_erp"],
            "us_hy_spread": US_INDICATORS["market_pricing"]["us_hy_spread_bp"] / 100,
            "us_ig_spread": US_INDICATORS["market_pricing"]["us_ig_spread_bp"] / 100,
            "dxy_index": 105.8,  # DXY: 2024-06-28 实际值约 105.8（来源：Bloomberg）
        },

        # ===== 跨国数据 =====
        "cross_border": {
            "cn_us_10y_spread": cn_us_10y_spread,
            "usd_cnh": CROSS_BORDER_METRICS["exchange_rate"]["usd_cnh"],
            "vix": CROSS_BORDER_METRICS["risk"]["vix"],
            "copper_price": COMMODITY_DATA["lme_copper_3m_usd_ton"],
            "gold_price": COMMODITY_DATA["comex_gold_usd_oz"],
            "brent_oil": COMMODITY_DATA["brent_oil_usd_bbl"],
            "trade_surplus": CROSS_BORDER_METRICS["exchange_rate"]["trade_surplus_usd_bn"],
            "forex_reserve_change": CROSS_BORDER_METRICS["exchange_rate"]["forex_reserve_change_usd_bn"],
            "pboc_mid_deviation": CROSS_BORDER_METRICS["exchange_rate"]["pboc_mid_rate_deviation_pct"],
            "cnh_cny_spread": CROSS_BORDER_METRICS["exchange_rate"]["cnh_cny_spread_bp"] / 100,
            "north_flow": CROSS_BORDER_METRICS["capital_flow"]["northbound_flow_cny_bn"],
            "global_pmi": CROSS_BORDER_METRICS["global_growth"]["global_manufacturing_pmi"],
            "euro_pmi": CROSS_BORDER_METRICS["global_growth"]["euro_manufacturing_pmi"],
            "geopolitical_score": GEOPOLITICAL_DATA["geopolitical_score"],
        },

        # ===== 大宗商品 =====
        "commodities": {
            "copper_gold_ratio": COMMODITY_DATA["copper_gold_ratio"],
            "oil_gold_ratio": COMMODITY_DATA["oil_gold_ratio"],
            "copper_price": COMMODITY_DATA["lme_copper_3m_usd_ton"],
            "gold_price": COMMODITY_DATA["comex_gold_usd_oz"],
            "brent_oil": COMMODITY_DATA["brent_oil_usd_bbl"],
            "iron_ore_price": COMMODITY_DATA["dce_iron_ore_cny_ton"],
            "iron_ore_usd": COMMODITY_DATA["iron_ore_62_fe_usd_dmt"],
            "nh_industrial_index": COMMODITY_DATA["nh_industrial_index"],
            "soybean_corn_ratio": COMMODITY_DATA["soybean_corn_ratio"],
            "gold_vs_real_rate": COMMODITY_DATA["gold_vs_real_rate"],
            "nh_global_pmi_ratio": COMMODITY_DATA["nh_global_pmi_ratio"],
        },

        # ===== Layer 3 市场定价 =====
        "market_pricing": {
            "csi300_index": MARKET_PRICING_DATA["csi300_index"],
            "csi300_forward": MARKET_PRICING_DATA["csi300_forward"],
            "csi300_put": MARKET_PRICING_DATA["csi300_put"],
            "csi300_call": MARKET_PRICING_DATA["csi300_call"],
            "pc_ratio": MARKET_PRICING_DATA["pc_ratio"],
            "gov_bond_10y_holding_change": MARKET_PRICING_DATA["gov_bond_10y_holding_change"],
            "hshare_ah_spread": MARKET_PRICING_DATA["hshare_ah_spread"],
            "copper_near": MARKET_PRICING_DATA["copper_near_usd_ton"],
            "copper_far": MARKET_PRICING_DATA["copper_far_usd_ton"],
            "oil_near": MARKET_PRICING_DATA["oil_near_usd_bbl"],
            "oil_far": MARKET_PRICING_DATA["oil_far_usd_bbl"],
        },

        # ===== Layer 4 预期差 =====
        "expected_diff": {
            "china_surprise_index": EXPECTED_DIFF_DATA["china_surprise_index"],
            "us_surprise_index": EXPECTED_DIFF_DATA["us_surprise_index"],
            "ff_implied_rate": EXPECTED_DIFF_DATA["ff_implied_rate_dec24"],
        },

        # ===== Layer 4.5 反身性 =====
        "reflexivity": {
            "signal_crowding_score": REFLEXIVITY_DATA["signal_crowding_score"],
            "position_concentration_z": REFLEXIVITY_DATA["position_concentration_z"],
            "self_fulfilling_index": REFLEXIVITY_DATA["self_fulfilling_index"],
            "cross_framework_consensus": REFLEXIVITY_DATA["cross_framework_consensus"],
            "cftc_net_position_pct": REFLEXIVITY_DATA["cftc_net_position_pct"],
            "etf_flow_cny_bn": REFLEXIVITY_DATA["etf_flow_cny_bn"],
            "northbound_flow_cny_bn": REFLEXIVITY_DATA["northbound_flow_cny_bn"],
            "sell_side_bearish_pct": REFLEXIVITY_DATA["sell_side_bearish_pct"],
            "buy_side_bearish_pct": REFLEXIVITY_DATA["buy_side_bearish_pct"],
        },
    }


# =============================================================================
# 数据摘要打印
# =============================================================================

def print_data_summary():
    """打印数据集的关键字段摘要（用于人工核查）。"""
    data = build_complete_mock_data()
    print(f"\n{'='*60}")
    print(f"宏观测试数据集 - {REPORT_DATE}")
    print(f"{'='*60}")

    print("\n【Layer 0 - 增长维度】")
    print(f"  中国 NBS PMI: {data['china']['nbs_manufacturing_pmi']} (荣枯线50)")
    print(f"  中国 财新 PMI: {data['china']['caixin_manufacturing_pmi']} (荣枯线50)")
    print(f"  美国 ISM 制造业PMI: {data['us']['ism_manufacturing_pmi']} (荣枯线50)")
    print(f"  美国 ISM 服务业PMI: {data['us']['ism_services_pmi']} (荣枯线50)")

    print("\n【Layer 0 - 通胀维度】")
    print(f"  中国 CPI: {data['china']['cpi_yoy']}%")
    print(f"  中国 PPI: {data['china']['ppi_yoy']}%")
    print(f"  美国 核心PCE: {data['us']['core_pce_yoy']}%")
    print(f"  美国 CPI: {data['us']['cpi_yoy']}%")

    print("\n【Layer 0 - 政策维度】")
    print(f"  中国 1Y LPR: {data['china']['1y_lpr']}%")
    print(f"  中国 MLF: {data['china']['mlf_rate']}%")
    print(f"  中国 DR007: {data['china']['dr007']}%")
    print(f"  美国 FFR: {data['us']['ffr']}%")
    print(f"  美国 SOFR: {data['us']['sofr']}%")

    print("\n【Layer 0 - 跨国指标】")
    print(f"  中美10Y利差: {data['cross_border']['cn_us_10y_spread']:.2f}% (倒挂)")
    print(f"  USD/CNH: {data['cross_border']['usd_cnh']}")
    print(f"  DXY: ~{data['us']['dxy_index']:.1f}")
    print(f"  VIX: {data['cross_border']['vix']}")
    print(f"  全球PMI: {data['cross_border']['global_pmi']}")

    print("\n【Layer 2.5 - 大宗商品】")
    print(f"  LME铜: ${data['commodities']['copper_price']}/吨")
    print(f"  COMEX黄金: ${data['commodities']['gold_price']}/盎司")
    print(f"  布伦特: ${data['commodities']['brent_oil']}/桶")
    print(f"  铁矿石: ${data['commodities']['iron_ore_usd']}/吨")
    print(f"  铜金比: {data['commodities']['copper_gold_ratio']:.4f}")
    print(f"  铁矿石/铜: {data['commodities']['iron_ore_price'] / data['commodities']['copper_price']:.4f}")

    print("\n【Layer 2 - 政策维度】")
    print(f"  货币政策: {data['china']['monetary_policy_direction']}")
    print(f"  财政政策: {data['china']['fiscal_policy_direction']}")
    print(f"  地产政策: {data['china']['real_estate_policy_direction']}")

    print("\n【Layer 4.5 - 反身性】")
    print(f"  信号拥挤度: {data['reflexivity']['signal_crowding_score']}/100")
    print(f"  跨框架一致性: {data['reflexivity']['cross_framework_consensus']}/100")

    print("\n【通道6 - 地缘政治】")
    print(f"  地缘评分: {data['cross_border']['geopolitical_score']}/10")
    print(f"  {GEOPOLITICAL_DATA['detail']}")


if __name__ == "__main__":
    print_data_summary()
