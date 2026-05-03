#!/usr/bin/env python3
"""Local validation for bridgewater_economic_machine_lite examples.

This script only checks local package files. It does not fetch data, call APIs,
or execute any trading/action workflow.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SKILL = ROOT / "SKILL.md"

REQUIRED_FRONTMATTER = {"name", "description", "owner_group", "domain", "status"}
REQUIRED_TOP = [
    "direction",
    "confidence",
    "reasoning",
    "signals",
    "source",
    "signal_type",
    "stock_code",
    "weight",
    "meta",
]
REQUIRED_META = [
    "output_version",
    "skill_version",
    "skill_name",
    "owner_group",
    "target",
    "period",
    "time_horizon",
    "risk_level",
    "key_findings",
    "evidence",
    "risk_notes",
    "uncertainties",
    "needs_human_review",
]
REQUIRED_EVIDENCE = ["source_type", "source_name", "date", "metric", "value", "comparison", "note"]

DIRECTIONS = {"bullish", "bearish", "neutral"}
SIGNAL_TYPES = {"financial", "technical", "fundflow", "macro", "news", "valuation", "industry", "risk"}
TIME_HORIZONS = {"short", "mid", "long"}
RISK_LEVELS = {"low", "medium", "high"}
QUADRANTS = {
    "Q1_goldilocks",
    "Q2_reflation_overheating",
    "Q3_stagflation",
    "Q4_recession_disinflation",
    "mixed_boundary",
}
SHORT_DEBT = {"recovery", "overheating", "tightening", "recession", "transition"}
LONG_DEBT = {"low_debt_expansion", "high_debt_boom", "debt_pressure", "deleveraging_or_monetary_reset", "unclear"}
ASSET_TILT = {"overweight", "slight_overweight", "neutral", "slight_underweight", "underweight", "underweight_or_neutral"}


def fail(errors: list[str], where: str, msg: str) -> None:
    errors.append(f"{where}: {msg}")


def load_json(path: Path, errors: list[str]) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        fail(errors, path.name, f"invalid JSON: {exc}")
        return {}


def validate_frontmatter(errors: list[str]) -> None:
    text = SKILL.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(errors, "SKILL.md", "missing YAML front matter start")
        return
    parts = text.split("---", 2)
    if len(parts) < 3:
        fail(errors, "SKILL.md", "missing YAML front matter end")
        return
    fm = parts[1]
    found = {line.split(":", 1)[0].strip() for line in fm.splitlines() if ":" in line}
    missing = REQUIRED_FRONTMATTER - found
    if missing:
        fail(errors, "SKILL.md", f"front matter missing {sorted(missing)}")


def parse_signal_prefix(signals: list[str], prefix: str) -> str | None:
    for item in signals:
        if item.startswith(prefix + ":"):
            return item.split(":", 1)[1].strip()
    return None


def validate_output(path: Path, errors: list[str]) -> None:
    obj = load_json(path, errors)
    if not obj:
        return

    for key in REQUIRED_TOP:
        if key not in obj:
            fail(errors, path.name, f"missing top-level field {key}")

    if obj.get("direction") not in DIRECTIONS:
        fail(errors, path.name, f"bad direction {obj.get('direction')!r}")
    confidence = obj.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        fail(errors, path.name, f"bad confidence {confidence!r}")
    if obj.get("signal_type") not in SIGNAL_TYPES:
        fail(errors, path.name, f"bad signal_type {obj.get('signal_type')!r}")
    if obj.get("signal_type") != "technical":
        fail(errors, path.name, "bridgewater skill output should use signal_type='technical'")
    if obj.get("stock_code") != "":
        fail(errors, path.name, "stock_code should be empty string for market-level technical skill")
    if not isinstance(obj.get("signals"), list) or not all(isinstance(x, str) for x in obj.get("signals", [])):
        fail(errors, path.name, "signals must be list[str]")

    signals = obj.get("signals", [])
    quadrant = parse_signal_prefix(signals, "quadrant_position")
    short_debt = parse_signal_prefix(signals, "short_debt_cycle")
    long_debt = parse_signal_prefix(signals, "long_debt_pressure")
    if quadrant not in QUADRANTS:
        fail(errors, path.name, f"bad quadrant_position {quadrant!r}")
    if short_debt not in SHORT_DEBT:
        fail(errors, path.name, f"bad short_debt_cycle {short_debt!r}")
    if long_debt not in LONG_DEBT:
        fail(errors, path.name, f"bad long_debt_pressure {long_debt!r}")

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        fail(errors, path.name, "meta must be object")
        return
    for key in REQUIRED_META:
        if key not in meta:
            fail(errors, path.name, f"missing meta field {key}")

    if meta.get("time_horizon") not in TIME_HORIZONS:
        fail(errors, path.name, f"bad time_horizon {meta.get('time_horizon')!r}")
    if meta.get("risk_level") not in RISK_LEVELS:
        fail(errors, path.name, f"bad risk_level {meta.get('risk_level')!r}")
    if meta.get("macro_quadrant") and meta.get("macro_quadrant") not in QUADRANTS:
        fail(errors, path.name, f"bad meta.macro_quadrant {meta.get('macro_quadrant')!r}")

    evidence = meta.get("evidence", [])
    if not isinstance(evidence, list):
        fail(errors, path.name, "meta.evidence must be a list")
    else:
        for idx, item in enumerate(evidence):
            if not isinstance(item, dict):
                fail(errors, path.name, f"evidence[{idx}] must be object")
                continue
            for key in REQUIRED_EVIDENCE:
                if key not in item:
                    fail(errors, path.name, f"evidence[{idx}] missing {key}")

    if confidence is not None and confidence < 0.4:
        if obj.get("direction") != "neutral":
            fail(errors, path.name, "confidence < 0.4 should use direction='neutral'")
        if meta.get("needs_human_review") is not True:
            fail(errors, path.name, "confidence < 0.4 should set needs_human_review=true")

    missing_required = meta.get("data_quality", {}).get("missing_required", [])
    if missing_required and meta.get("needs_human_review") is not True:
        fail(errors, path.name, "missing required data should set needs_human_review=true")

    tilts = meta.get("asset_allocation_tilt", {})
    if tilts:
        for key, value in tilts.items():
            if value not in ASSET_TILT:
                fail(errors, path.name, f"bad asset tilt {key}={value!r}")


def validate_input(path: Path, errors: list[str]) -> None:
    obj = load_json(path, errors)
    if not obj:
        return
    for key in ["target", "period", "time_horizon", "data_mode", "indicators"]:
        if key not in obj:
            fail(errors, path.name, f"missing input field {key}")
    if obj.get("time_horizon") not in TIME_HORIZONS:
        fail(errors, path.name, f"bad input time_horizon {obj.get('time_horizon')!r}")
    indicators = obj.get("indicators", {})
    if not isinstance(indicators, dict):
        fail(errors, path.name, "indicators must be object")
        return
    for bucket in ["growth", "inflation", "credit", "policy", "debt_cycle"]:
        if bucket not in indicators:
            fail(errors, path.name, f"missing indicators.{bucket}")


def main() -> int:
    errors: list[str] = []
    validate_frontmatter(errors)
    for path in sorted(EXAMPLES.glob("*input.json")):
        validate_input(path, errors)
    for path in sorted(EXAMPLES.glob("*output.json")):
        validate_output(path, errors)

    if errors:
        print("FAIL")
        for err in errors:
            print(f"- {err}")
        return 1

    print("PASS")
    print(f"Validated {len(list(EXAMPLES.glob('*input.json')))} input examples and {len(list(EXAMPLES.glob('*output.json')))} output examples.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
