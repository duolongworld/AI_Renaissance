from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PR_TEMPLATE = ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
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
    whitespace_command = "\n".join(commands)

    assert "git fetch --no-tags --prune origin \"$BASE_REF\"" in whitespace_command
    assert "git diff --check FETCH_HEAD...HEAD" in whitespace_command
    assert "git diff --check \"$BEFORE_SHA\" HEAD" in whitespace_command
    assert "git diff --check HEAD^ HEAD" in whitespace_command
    assert any("python -m pytest -q" in command for command in commands)
    assert any(
        "python -m compileall main.py agents data_sources debug_ui samples tests" in command
        for command in commands
    )


def test_pr_template_stays_minimal_and_non_redundant() -> None:
    source = PR_TEMPLATE.read_text(encoding="utf-8")

    assert "## 摘要" in source
    assert "## 相关背景" in source
    assert "## 影响范围" in source
    assert "## 测试" in source
    assert "Agent / Orchestrator" in source
    assert "data_sources" in source
    assert "Tests / CI / Docs" in source
    assert "关联问题" not in source
    assert "Close #" not in source
    assert "自动检查" not in source
    assert "CI 会自动检查" not in source
    assert "Skill contract" not in source
    assert "data Skill 边界" not in source
    assert "8 Agent + N Skill + data layer" not in source
    assert "Checklist" not in source
    assert "Signal" not in source
    assert "python -m pytest ..." not in source
    assert "如何测试" not in source
    assert "不可自动验证的风险" not in source
    assert "感知层" not in source
    assert "研究层" not in source
    assert "认知层" not in source


def test_main_entrypoint_keeps_orchestrator_expert_flow() -> None:
    source = MAIN_ENTRYPOINT.read_text(encoding="utf-8")

    assert "from agents.orchestrator.agent import OrchestratorAgent" in source
    assert "EXPERT_AGENTS = {" in source
    assert "orchestrator = OrchestratorAgent(config=config)" in source
    assert "register_experts(orchestrator, config, enabled_agents)" in source
    assert "orchestrator.analyze_many(stock_codes)" in source
