from agents.loader import discover_agent_classes, list_available_agents, load_agents


def test_discover_agent_classes_finds_cash_flow_agent():
    canonical_agents, aliases = discover_agent_classes()

    assert "research.financial.cash_flow" in canonical_agents
    assert aliases["cash_flow"] == "research.financial.cash_flow"


def test_load_agents_supports_short_name_selection():
    agents = load_agents(["cash_flow"])

    assert len(agents) == 1
    assert agents[0].name == "现金流验证Agent"


def test_load_agents_supports_canonical_name_selection():
    agents = load_agents(["research.financial.cash_flow"])

    assert len(agents) == 1
    assert agents[0].name == "现金流验证Agent"


def test_load_agents_loads_all_when_config_empty_list():
    agents = load_agents([])
    agent_names = {agent.name for agent in agents}

    assert "现金流验证Agent" in agent_names


def test_list_available_agents_contains_short_and_canonical_names():
    available_agents = list_available_agents()

    assert "cash_flow" in available_agents
    assert "research.financial.cash_flow" in available_agents
