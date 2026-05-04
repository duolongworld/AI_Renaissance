"""
东方财富股吧数据获取 CLI 包装器

核心抓取逻辑已收口到 data_sources/eastmoney_guba.py。
本脚本保留给命令行调试和 Skill 文档示例使用。

使用方式：
    python fetch_guba.py --stock_code 600519 [--pages 2] [--no-content]
"""

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_sources.eastmoney_guba import fetch_guba_posts


def main():
    parser = argparse.ArgumentParser(description="东方财富股吧数据获取")
    parser.add_argument("--stock_code", required=True, help="股票代码")
    parser.add_argument("--pages", type=int, default=2, help="每种列表抓取页数")
    parser.add_argument("--no-content", action="store_true", help="不抓取正文")
    args = parser.parse_args()

    result = fetch_guba_posts(
        stock_code=args.stock_code,
        pages=args.pages,
        fetch_content=not args.no_content,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
