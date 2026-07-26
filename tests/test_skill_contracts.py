import ast
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"

EXPERT_DOMAINS = {
    "financial",
    "technical",
    "fundflow",
    "macro",
    "industry",
    "news",
    "risk",
}
DATA_DOMAIN = "data"
REFERENCE_DOMAINS = {"examples"}
ORCHESTRATOR_DOMAINS = {"orchestrator"}
ORCHESTRATOR_FRONTMATTER_DOMAINS = {"orchestrator", "orchestration"}

SKILL_FILES = sorted(SKILLS_ROOT.glob("*/*/SKILL.md"))
QUOTED_SIGNAL_TYPE_RE = re.compile(r'"signal_type"\s*:\s*"([^"]+)"')
FORBIDDEN_DATA_SCRIPT_IMPORT_ROOTS = {
    "aiohttp",
    "akshare",
    "bs4",
    "httpx",
    "playwright",
    "requests",
    "selenium",
    "tushare",
    "urllib",
}


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    return yaml.safe_load(parts[1]) or {}


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_runtime_skill_frontmatter_domain_matches_directory() -> None:
    assert SKILL_FILES, "expected at least one runtime or data Skill"

    for path in SKILL_FILES:
        relative = path.relative_to(SKILLS_ROOT)
        top_level = relative.parts[0]
        metadata = _frontmatter(path)

        assert "domain" in metadata, f"{relative} must declare frontmatter domain"
        domain = metadata["domain"]

        if top_level in EXPERT_DOMAINS or top_level == DATA_DOMAIN:
            assert domain == top_level, f"{relative} domain must match skills/{top_level}/"
        elif top_level in ORCHESTRATOR_DOMAINS:
            assert domain in ORCHESTRATOR_FRONTMATTER_DOMAINS, (
                f"{relative} must use an orchestrator domain"
            )
        elif top_level in REFERENCE_DOMAINS:
            assert domain in EXPERT_DOMAINS, (
                f"{relative} is a reference Skill and should point at an expert domain"
            )
        else:
            raise AssertionError(f"{relative} lives under an unsupported Skill directory")


def test_analysis_skill_signal_type_examples_match_domain() -> None:
    for path in SKILL_FILES:
        relative = path.relative_to(SKILLS_ROOT)
        top_level = relative.parts[0]
        if top_level not in EXPERT_DOMAINS and top_level not in REFERENCE_DOMAINS:
            continue

        metadata = _frontmatter(path)
        expected_signal_type = metadata.get("domain")
        signal_types = QUOTED_SIGNAL_TYPE_RE.findall(path.read_text(encoding="utf-8"))

        for signal_type in signal_types:
            assert signal_type == expected_signal_type, (
                f"{relative} has signal_type={signal_type!r}, "
                f"expected {expected_signal_type!r}"
            )


def test_data_skill_examples_do_not_emit_signal_fields() -> None:
    for path in sorted((SKILLS_ROOT / "data").glob("*/SKILL.md")):
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")

        assert '"signal_type"' not in text, f"{relative} should not emit Signal fields"
        assert '"direction"' not in text, f"{relative} should not emit Signal fields"
        assert '"confidence"' not in text, f"{relative} should not emit Signal fields"


def test_data_skill_scripts_are_thin_data_source_wrappers() -> None:
    script_paths = sorted((SKILLS_ROOT / "data").glob("*/scripts/*.py"))

    for path in script_paths:
        relative = path.relative_to(ROOT)
        import_roots = _import_roots(path)

        assert "data_sources" in import_roots, (
            f"{relative} should call data_sources instead of owning provider logic"
        )
        forbidden = import_roots & FORBIDDEN_DATA_SCRIPT_IMPORT_ROOTS
        assert forbidden == set(), (
            f"{relative} imports provider/network modules {sorted(forbidden)}; "
            "put real fetching/parsing in data_sources/"
        )


def test_formal_tests_do_not_live_under_skills_tree() -> None:
    tests_dirs = [path.relative_to(ROOT) for path in SKILLS_ROOT.rglob("tests") if path.is_dir()]
    assert tests_dirs == []
