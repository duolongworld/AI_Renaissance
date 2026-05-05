"""
东方财富股吧数据源

开发3组维护。封装 guba.eastmoney.com 的帖子抓取能力，
供舆情 Agent 调用。对应的数据接口说明见：
skills/data/eastmoney_guba/SKILL.md
"""

import re
from datetime import datetime
from typing import Any, Dict, List

from loguru import logger

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


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


class EastMoneyGubaDataSource:
    """东方财富股吧帖子数据源"""

    def __init__(self):
        self.name = "东方财富股吧数据源"
        logger.info(f"[数据源] {self.name} 初始化完成")

    def get_posts(
        self,
        stock_code: str,
        pages: int = DEFAULT_PAGES,
        fetch_content: bool = True,
    ) -> Dict[str, Any]:
        """
        获取指定股票的股吧帖子。

        Returns:
            {
                "status": "success" | "error",
                "stock_code": "...",
                "posts": [...]
            }
        """
        return fetch_guba_posts(
            stock_code=stock_code,
            pages=pages,
            fetch_content=fetch_content,
        )


def normalize_code(code: str) -> str:
    """标准化股票代码，去除市场前缀"""
    code = code.strip().upper()
    for prefix in ("SH", "SZ", "BJ"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    return code


def fetch_and_parse_page(url: str) -> List[Dict[str, Any]]:
    """抓取并解析单个股吧列表页"""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    # 东方财富股吧页面使用 GBK/GB2312 编码，需显式指定
    resp.encoding = resp.apparent_encoding or "gbk"
    html = resp.text

    title_pattern = re.compile(
        r'postid="(\d+)"\s+data-posttype="\d+"\s+href="([^"]*)">([^<]+)</a>'
    )
    title_matches = title_pattern.findall(html)

    author_pattern = re.compile(r'class="author"><a\s+href="[^"]*">([^<]+)</a>')
    author_matches = author_pattern.findall(html)

    read_pattern = re.compile(r'class="read">(\d+)')
    reply_pattern = re.compile(r'class="reply">(\d+)')
    read_values = [int(v) for v in read_pattern.findall(html)]
    reply_values = [int(v) for v in reply_pattern.findall(html)]

    time_pattern = re.compile(r'class="update">(\d{2}-\d{2}\s+\d{2}:\d{2})')
    time_values = time_pattern.findall(html)

    posts = []
    for i, (post_id, href, title) in enumerate(title_matches):
        title = title.strip()
        if not title:
            continue

        if href.startswith("//"):
            full_url = "https:" + href
        elif href.startswith("/"):
            full_url = GUBA_BASE_URL + href
        else:
            full_url = href

        posts.append({
            "post_id": post_id,
            "title": title,
            "author": author_matches[i] if i < len(author_matches) else "",
            "reads": read_values[i] if i < len(read_values) else 0,
            "replies": reply_values[i] if i < len(reply_values) else 0,
            "post_time": time_values[i] if i < len(time_values) else "",
            "url": full_url,
        })

    return posts


def fetch_post_content(url: str) -> str:
    """抓取单条帖子的正文内容"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        # 403/429 等反爬状态码直接跳过，不重试
        if resp.status_code in (403, 429):
            return ""
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "gbk"
        html = resp.text

        content_pattern = re.compile(
            r'class="newstext[^"]*">(.*?)</div>', re.DOTALL
        )
        match = content_pattern.search(html)
        if not match:
            content_pattern = re.compile(
                r'xeditor_content[^>]*>(.*?)</div>', re.DOTALL
            )
            match = content_pattern.search(html)
        if not match:
            return ""

        text = match.group(1)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]
    except Exception as exc:
        logger.warning(f"[东方财富股吧数据源] 抓取帖子正文失败：{exc}")
        return ""


def fetch_guba_posts(
    stock_code: str,
    pages: int = DEFAULT_PAGES,
    fetch_content: bool = True,
) -> Dict[str, Any]:
    """从东方财富股吧抓取帖子数据"""
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

    for source_type, url_template in (
        ("hot", HOT_POSTS_URL),
        ("latest", LATEST_POSTS_URL),
    ):
        for page in range(1, pages + 1):
            url = url_template.format(code=code, page=page)
            try:
                page_posts = fetch_and_parse_page(url)
                for post in page_posts:
                    if post["post_id"] in seen_ids:
                        continue
                    seen_ids.add(post["post_id"])
                    post["source_type"] = source_type
                    post["content"] = ""
                    all_posts.append(post)
            except Exception as exc:
                logger.warning(f"[东方财富股吧数据源] 抓取列表失败 {url}: {exc}")

    if fetch_content:
        # 限制最多抓取正文条数，避免大量 403 请求拖垮服务
        max_content_fetch = 5
        fetched = 0
        for post in all_posts:
            if fetched >= max_content_fetch:
                break
            if post["source_type"] == "hot" and post.get("url"):
                content = fetch_post_content(post["url"])
                if content:
                    post["content"] = content
                    fetched += 1

    return {
        "status": "success",
        "stock_code": code,
        "fetch_time": datetime.now().isoformat(),
        "total_posts": len(all_posts),
        "posts": all_posts,
    }
