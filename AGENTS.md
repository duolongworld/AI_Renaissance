# AGENTS.md

This is the project-facing instruction file for coding agents. Keep it short: only stable architecture rules and repo-specific boundaries belong here.

## Core Architecture

AI Renaissance uses an **8 Agent + N Skill + data layer** architecture.

- `agents/orchestrator/`: the single Orchestrator Agent. It collects expert Signals and performs arbitration. It does not load Skills.
- `agents/{financial,technical,fundflow,macro,industry,news_agent,risk}/`: the 7 expert Agents. Each expert Agent owns one domain and returns a standard `Signal`.
- `skills/{financial,technical,fundflow,macro,industry,news,risk}/`: expert analysis Skills. They describe domain reasoning rules.
- `skills/data/`: data interface Skills. They describe call parameters, output fields, failure shape, and usage boundaries.
- `skills/examples/` and `skills/expert_skill_authoring/`: reference material only, not runtime expert Skill domains.
- `data_sources/`: executable data source code. Real fetching, parsing, normalization, and provider-specific handling belong here.

New domain reasoning should go into analysis Skills first. Expert Agents should focus on loading Skills, obtaining data, orchestrating analysis, and wrapping results as `Signal`. New data acquisition should become a `data_sources/` implementation plus, when useful, a `skills/data/` interface description.

## Agent Rules

- All expert Agents inherit `BaseAgent` from `agents/base.py`; `BaseAgent` provides the AgentScope-native Signal boundary for expert Agents.
- All expert Agents return `Signal` from `agents/signal.py`.
- Expert Agents should load their own analysis Skill domain.
- Expert Agents may read `skills/data/` to understand how a data source is called and shaped, but runtime data access should call `data_sources/`.
- Prefer injecting data sources through `config` so Agents can be tested with fake sources.
- Keep shared infrastructure changes to `agents/base.py`, `agents/signal.py`, and `agents/registry.py` narrow and intentional.

## Skill Rules

Analysis Skills:

- Use `docs/ANALYSIS_SKILL_TEMPLATE.md`.
- Live under `skills/{domain}/{skill_name}/SKILL.md`.
- Define expert judgment, evidence, confidence, uncertainty, and expected Signal-shaped output.
- Align top-level output with `agents.signal.Signal`; put traceability and extra context in `meta`.

Data interface Skills:

- Use `docs/DATA_SKILL_TEMPLATE.md`.
- Live under `skills/data/{source_name}/SKILL.md`.
- Describe how to call a data source and interpret its returned fields, not an investment judgment.
- Do not use `direction`, `confidence`, or other Signal-only fields as the data output.
- Do not place core fetching/parsing logic in a data Skill script. Scripts under `skills/data/**/scripts/` should be thin debugging wrappers around `data_sources/`.

## Data Layer Rules

- `data_sources/` is the only home for real provider integration logic.
- Keep provider API details out of expert Agents.
- Keep data-source outputs stable and dictionary-based when they are consumed by Skills or Agents.
- When implementation status matters, inspect the current code directly instead of relying on this file.

## Documentation Map

- `README.md`: human-facing project overview.
- `docs/ARCHITECTURE.md`: system architecture.
- `docs/AGENT_GUIDE.md`: expert Agent implementation guide.
- `docs/ANALYSIS_SKILL_TEMPLATE.md`: expert analysis Skill template.
- `docs/DATA_SKILL_TEMPLATE.md`: data interface Skill template.
- `docs/AGENT_MATRIX.md`: navigation for Agents, Skills, and data sources; inspect code for current implementation status.
- `docs/TEAM.md`: ownership boundaries.

When architecture boundaries change, update the relevant docs together instead of only changing code.
