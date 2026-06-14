from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fusion import fuse_signals
from .runner import RunContext, load_rows_from_code, load_rows_from_csv, run_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Four-model traditional technical fusion v0.1")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--csv", help="CSV path with date, open?, high, low, close, volume")
    g.add_argument("--code", help="Stock/index code (CN A-share supported by EastMoney heuristic)")
    parser.add_argument("--start", default="", help="Start date YYYY-MM-DD (required when --code)")
    parser.add_argument("--end", default="", help="End date YYYY-MM-DD (required when --code)")
    parser.add_argument("--freq", default="D", choices=["D", "W", "M"], help="Kline frequency for --code")
    parser.add_argument("--adjust", default="none", choices=["none", "qfq", "hfq"], help="Adjust type (v0.1: recorded only)")
    parser.add_argument("--threshold", type=float, default=0.6, help="Fusion threshold T")
    parser.add_argument("--json-output", help="Write the full fusion JSON result to this path")
    parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    args = parser.parse_args()

    uncertainties = []
    if args.csv:
        rows, u = load_rows_from_csv(args.csv)
        uncertainties.extend(u)
        ctx = RunContext(stock_code="", target=Path(args.csv).stem, source_name=Path(args.csv).name)
    else:
        if not args.start or not args.end:
            raise SystemExit("--code 模式需要同时提供 --start 与 --end")
        rows, u = load_rows_from_code(args.code, args.start, args.end, freq=args.freq, adjust=args.adjust)
        uncertainties.extend(u)
        source_name = next((item.replace("行情来源：", "") for item in u if str(item).startswith("行情来源：")), f"market_data:{args.code}")
        ctx = RunContext(stock_code=args.code, target=args.code, source_name=source_name)

    model_signals = run_models(rows, ctx)
    # propagate input uncertainties into fused meta
    result = fuse_signals(model_signals, threshold=float(args.threshold))
    fused = result["fused_signal"]
    if isinstance(fused.get("meta"), dict) and uncertainties:
        fused["meta"].setdefault("uncertainties", [])
        fused["meta"]["uncertainties"].extend(uncertainties)

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
