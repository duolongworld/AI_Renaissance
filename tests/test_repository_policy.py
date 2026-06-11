from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MAIN_ENTRYPOINT = ROOT / "main.py"


def _load_ci_workflow() -> dict:
    return yaml.load(CI_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _ci_run_commands() -> list[str]:
    workflow = _load_ci_workflow()
    steps = workflow["jobs"]["test"]["steps"]
    return [step["run"] for step in steps if "run" in step]


def test_ci_workflow_exists_and_runs_on_main_prs() -> None:
    assert CI_WORKFLOW.exists()

    workflow = _load_ci_workflow()
    triggers = workflow["on"]

    assert "pull_request" in triggers
    assert "main" in triggers["pull_request"]["branches"]
    assert "push" in triggers
    assert "main" in triggers["push"]["branches"]


def test_ci_keeps_required_repository_checks() -> None:
    commands = _ci_run_commands()

    assert any("python -m pytest -q" in command for command in commands)
    assert any(
        "python -m compileall main.py agents data_sources debug_ui samples tests" in command
        for command in commands
    )


def test_main_entrypoint_keeps_orchestrator_expert_flow() -> None:
    source = MAIN_ENTRYPOINT.read_text(encoding="utf-8")

    assert "from agents.orchestrator.agent import OrchestratorAgent" in source
    assert "EXPERT_AGENTS = {" in source
    assert "orchestrator = OrchestratorAgent(config=config)" in source
    assert "register_experts(orchestrator, config, enabled_agents)" in source
    assert "orchestrator.analyze_many(stock_codes)" in source
