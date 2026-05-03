from agents.perception.market_data.data_source.tencent import TencentDataSource

DATA_SOURCES = {
    "tencent": TencentDataSource,
}

DEFAULT_SOURCE = "tencent"


def get_data_source(name: str = DEFAULT_SOURCE, **kwargs):
    cls = DATA_SOURCES.get(name)
    if not cls:
        raise ValueError(
            f"未知数据源: {name}，可选: {list(DATA_SOURCES.keys())}"
        )
    return cls(**kwargs)
