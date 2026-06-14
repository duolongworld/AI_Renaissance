from agents.signal import Signal
from agents.technical.agent import TechnicalAgent


def test_technical_agent_default_does_not_use_synthetic_when_live_missing(monkeypatch):
    import agents.technical.agent as technical_agent_module

    monkeypatch.setattr(technical_agent_module, "load_rows_from_code", lambda *args, **kwargs: ([], ["live failed"]))

    sig = TechnicalAgent(config={}).analyze("600519")

    assert isinstance(sig, Signal)
    assert sig.direction == "neutral"
    assert sig.meta["data_status"] == "missing:ohlcv"
    assert sig.meta["needs_human_review"] is True
    assert sig.meta["technical_agent_policy"]["blocked_reason"] == "missing_real_ohlcv"


def test_technical_agent_allows_synthetic_only_when_explicit():
    sig = TechnicalAgent(config={"use_live_data": False, "allow_synthetic_ohlcv": True}).analyze("600519")

    assert isinstance(sig, Signal)
    assert sig.meta["data_status"] == "offline:synthetic_ohlcv"
    assert sig.meta["rows_count"] > 0
    assert sig.meta["analysis_reports"]

