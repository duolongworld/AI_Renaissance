#!/usr/bin/env python3
"""System B 测试入口 — 触发 core/system_b.py 自测"""
import sys
from pathlib import Path

core_dir = Path(__file__).parent.parent.parent / "skills" / "industry" / "industrial_sentinel" / "core"
sys.path.insert(0, str(core_dir))

import runpy
runpy.run_path(str(core_dir / "system_b.py"), run_name="__main__")
