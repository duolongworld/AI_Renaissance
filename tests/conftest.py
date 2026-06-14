import pytest


class FakeNewsSource:
    def get_posts(self, stock_code: str, pages: int = 1, fetch_content: bool = False):
        return {
            "status": "success",
            "stock_code": stock_code,
            "posts": [
                {"title": "offline post 1", "content": "fixture", "reads": 100, "post_time": "", "source_type": "test"},
                {"title": "offline post 2", "content": "fixture", "reads": 90, "post_time": "", "source_type": "test"},
                {"title": "offline post 3", "content": "fixture", "reads": 80, "post_time": "", "source_type": "test"},
                {"title": "offline post 4", "content": "fixture", "reads": 70, "post_time": "", "source_type": "test"},
                {"title": "offline post 5", "content": "fixture", "reads": 60, "post_time": "", "source_type": "test"},
            ],
        }

    def get_sentiment_data(self):
        return {
            "status": "success",
            "score": 50.0,
            "stage": {"name": "neutral", "position": "30-50%", "direction": "neutral"},
            "direction": "neutral",
            "confidence": 0.3,
            "indicators": {},
            "raw_data": {},
            "special_signals": [],
            "uncertainties": [],
        }

    def get_industry_sentiment(self, stock_code: str):
        return {
            "status": "success",
            "industry_name": "test industry",
            "score": 50.0,
            "stage": {"name": "neutral", "position": "30-50%", "direction": "neutral"},
            "direction": "neutral",
            "confidence": 0.3,
            "position_suggestion": "30-50%",
            "special_signals": [],
            "indicators": {},
            "raw_data_summary": {},
            "uncertainties": [],
        }


@pytest.fixture
def fake_news_source():
    return FakeNewsSource()


@pytest.fixture
def offline_config(fake_news_source):
    def build(signal_type: str):
        if signal_type == "technical":
            return {"use_live_data": False, "allow_synthetic_ohlcv": True, "use_cninfo_company_data": False}
        if signal_type != "news":
            return {}

        return {
            "pages": 1,
            "fetch_content": False,
            "guba_data_source": fake_news_source,
            "market_sentiment_source": fake_news_source,
            "industry_sentiment_source": fake_news_source,
        }

    return build
