from main import collect_signals


def test_collect_signals_loads_enabled_agent_by_short_name():
    bundle = collect_signals("000001", {"agents": ["cash_flow"]})

    assert len(bundle.signals) == 1
    assert bundle.signals[0].source == "现金流验证Agent"


def test_collect_signals_returns_empty_bundle_for_unknown_agent():
    bundle = collect_signals("000001", {"agents": ["does_not_exist"]})

    assert bundle.stock_code == "000001"
    assert bundle.signals == []
