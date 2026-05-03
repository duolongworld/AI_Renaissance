"""
行情数据Agent配置
"""

# 请求设置
REQUEST_TIMEOUT = 10
DEFAULT_COUNT = 300

# 请求头
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 指标参数
MA_PERIODS = [5, 10, 20, 60, 120, 250]
BOLL_PERIOD = 20
BOLL_STD_DEV = 2
RSI_PERIODS = [6, 12, 24]
CHIP_DAYS = 120
CHIP_PRICE_BINS = 50
