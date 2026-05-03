# Validation Report

## Result

PASS

## Command

```bash
python tests/validate_signal_outputs.py
```

## Output

```text
PASS
Validated 7 input examples and 7 output examples.
```

## Scope

This validation only checks local package structure and example JSON outputs. It does not fetch external data, call APIs, access broker accounts, or execute trading actions.

Checked items:

- `SKILL.md` YAML front matter exists and contains required fields.
- Example input JSON files are syntactically valid and include required input sections.
- Example output JSON files match the project Signal top-level fields.
- `direction`, `confidence`, `signal_type`, `time_horizon`, `risk_level`, quadrant, debt cycle, and asset tilt values stay within allowed enums.
- `signals` is `list[str]`.
- `meta.evidence` contains `source_type`, `source_name`, `date`, `metric`, `value`, `comparison`, and `note`.
- Low-confidence outputs remain `neutral` and require human review.
