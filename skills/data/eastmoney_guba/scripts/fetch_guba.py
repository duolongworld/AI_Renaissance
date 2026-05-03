"""
东方财富股吧数据获取脚本

从 guba.eastmoney.com 抓取指定个股的帖子数据，
输出结构化 JSON，供舆情分析 Skill 使用。

使用方式：
    python fetch_guba.py --stock_code 600519 [--pages 2] [--no-content]
"""

import re
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ── 配置常量 ──────────────────────────────────────────

GUBA_BASE_URL = "https://guba.eastmoney.com"

HOT_POSTS_URL = GUBA_BASE_URL + "/list,{code},99_{page}.html"
LATEST_POSTS_URL = GUBA_BASE_URL + "/list,{code}_{page}.html"

DEFAULT_PAGES = 2
REQUEST_TIMEOUT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://guba.eastmoney.com/",
}


# ── 核心函数 ──────────────────────────────────────────

def normalize_code(code: str) -> str:
    """标准化股票代码，去除市场前缀"""
    code = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    return code


def fetch_and_parse_page(url: str) -> List[Dict[str, Any]]:
    """抓取并解析单个页面"""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    # 东方财富股吧页面使用 GBK/GB2312 编码，需显式指定
    resp.encoding = resp.apparent_encoding or "gbk"
    html = resp.text

    # 提取帖子信息
    title_pattern = re.compile(
        r'postid="(\d+)"\s+data-posttype="\d+"\s+href="([^"]*)">([^<]+)</a>'
    )
    title_matches = title_pattern.findall(html)

    # 提取作者
    author_pattern = re.compile(
        r'class="author"><a\s+href="[^"]*">([^<]+)</a>'
    )
    author_matches = author_pattern.findall(html)

    # 提取阅读数和回复数
    read_pattern = re.compile(r'class="read">(\d+)')
    reply_pattern = re.compile(r'class="reply">(\d+)')
    read_values = [int(v) for v in read_pattern.findall(html)]
    reply_values = [int(v) for v in reply_pattern.findall(html)]

    # 提取帖子发布时间（格式: MM-DD HH:mm）
    time_pattern = re.compile(r'class="update">(\d{2}-\d{2}\s+\d{2}:\d{2})')
    time_values = time_pattern.findall(html)

    posts = []
    for i, (post_id, href, title) in enumerate(title_matches):
        title = title.strip()
        if not title:
            continue

        author = author_matches[i] if i < len(author_matches) else ""
        reads = read_values[i] if i < len(read_values) else 0
        replies = reply_values[i] if i < len(reply_values) else 0
        post_time = time_values[i] if i < len(time_values) else ""

        # 构建完整 URL
        if href.startswith("//"):
            full_url = "https:" + href
        elif href.startswith("/"):
            full_url = GUBA_BASE_URL + href
        else:
            full_url = href

        posts.append({
            "post_id": post_id,
            "title": title,
            "author": author,
            "reads": reads,
            "replies": replies,
            "post_time": post_time,
            "url": full_url,
        })

    return posts


def fetch_post_content(url: str) -> str:
    """抓取单条帖子的正文内容"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # 东方财富股吧页面使用 GBK/GB2312 编码
        resp.encoding = resp.apparent_encoding or "gbk"
        html = resp.text

        # guba 帖子页
        content_pattern = re.compile(
            r'class="newstext[^"]*">(.*?)</div>', re.DOTALL
        )
        match = content_pattern.search(html)
        if not match:
            # caifuhao 文章页
            content_pattern = re.compile(
                r'xeditor_content[^>]*>(.*?)</div>', re.DOTALL
            )
            match = content_pattern.search(html)
        if not match:
            return ""

        text = match.group(1)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]
    except Exception:
        return ""


def fetch_guba_posts(
    stock_code: str,
    pages: int = DEFAULT_PAGES,
    fetch_content: bool = True,
) -> Dict[str, Any]:
    """
    从东方财富股吧抓取帖子数据

    Args:
        stock_code: 股票代码
        pages: 每种列表抓取的页数
        fetch_content: 是否为热门帖子抓取正文

    Returns:
        结构化帖子数据 dict
    """
    if not HAS_REQUESTS:
        return {
            "status": "error",
            "stock_code": stock_code,
            "error": "requests 库未安装",
            "posts": [],
        }

    code = normalize_code(stock_code)
    all_posts = []
    seen_ids = set()

    # 热门帖子
    for page in range(1, pages + 1):
        url = HOT_POSTS_URL.format(code=code, page=page)
        try:
            page_posts = fetch_and_parse_page(url)
            for post in page_posts:
                if post["post_id"] not in seen_ids:
                    seen_ids.add(post["post_id"])
                    post["source_type"] = "hot"
                    post["content"] = ""
                    all_posts.append(post)
        except Exception:
            pass

    # 最新帖子
    for page in range(1, pages + 1):
        url = LATEST_POSTS_URL.format(code=code, page=page)
        try:
            page_posts = fetch_and_parse_page(url)
            for post in page_posts:
                if post["post_id"] not in seen_ids:
                    seen_ids.add(post["post_id"])
                    post["source_type"] = "latest"
                    post["content"] = ""
                    all_posts.append(post)
        except Exception:
            pass

    # 抓取热门帖子正文
    if fetch_content:
        for post in all_posts:
            if post["source_type"] == "hot" and post.get("url"):
                content = fetch_post_content(post["url"])
                if content:
                    post["content"] = content

    return {
        "status": "success",
        "stock_code": code,
        "fetch_time": datetime.now().isoformat(),
        "total_posts": len(all_posts),
        "posts": all_posts,
    }


# ── CLI 入口 ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="东方财富股吧数据获取")
    parser.add_argument("--stock_code", required=True, help="股票代码")
    parser.add_argument("--pages", type=int, default=DEFAULT_PAGES, help="每种列表抓取页数")
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
