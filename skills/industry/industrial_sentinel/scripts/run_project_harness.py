#!/usr/bin/env python3
"""CLI wrapper for the Industrial Sentinel project harness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.industry.industrial_sentinel.harness import (  # noqa: E402
    FIXTURE_NAMES,
    REFERENCE_DATE,
    run_live_project_harness,
    run_project_harness,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Industrial Sentinel through the real project arbitration path.")
    parser.add_argument("--stock", default="300782", help="stock code or supported stock name")
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--fixture", default="all", choices=("all", *FIXTURE_NAMES))
    parser.add_argument("--output", type=Path, default=Path("reports/industry_harness"))
    parser.add_argument("--reference-date")
    parser.add_argument("--agent-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--peer-fetch-workers", type=int, default=4)
    parser.add_argument(
        "--live-smoke-summary",
        type=Path,
        help="optional JSON summary from the non-blocking 7-Agent live smoke",
    )
    args = parser.parse_args()

    live_smoke = None
    if args.live_smoke_summary:
        live_smoke = json.loads(args.live_smoke_summary.read_text(encoding="utf-8"))

    if args.mode == "live":
        report = run_live_project_harness(
            stock_code=args.stock,
            output_dir=args.output,
            reference_date=args.reference_date or date.today().isoformat(),
            agent_timeout_seconds=args.agent_timeout_seconds,
            peer_fetch_workers=args.peer_fetch_workers,
        )
    else:
        report = run_project_harness(
            stock_code=args.stock,
            fixture=args.fixture,
            output_dir=args.output,
            reference_date=args.reference_date or REFERENCE_DATE,
            live_smoke=live_smoke,
        )
    print(json.dumps({
        "run_id": report["run_id"],
        "status": report["status"],
        "artifacts": report["artifacts"],
        "cases": [{"fixture": case["fixture"], "status": case["status"]} for case in report["cases"]],
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
