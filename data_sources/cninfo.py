"""
巨潮资讯网公告数据源

开发3组维护。委托给独立的开源工具 use_cninfo
(https://github.com/rollysys/use_cninfo) 抓取 A 股法定披露公告
PDF 全文,供财务/事件 Agent 调用。本模块只负责适配数据契约,
真实抓取逻辑不在本仓库。

对应数据接口说明见: skills/data/cninfo/SKILL.md

安装前置工具:
    git clone https://github.com/rollysys/use_cninfo.git
    cd use_cninfo && pip install -e .

可选: 装 announcement_filter 启用 search 的标签过滤
    git clone https://github.com/rollysys/announcement_filter.git
    cd announcement_filter && pip install -e .
"""

import json
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


CLI_NAME = "cninfo"
DEFAULT_TIMEOUT = 120


class CninfoDataSource:
    """巨潮资讯网公告数据源 — 委托给 `cninfo` CLI。"""

    def __init__(self):
        self.name = "巨潮资讯网公告数据源"
        self._cli_path = shutil.which(CLI_NAME)
        if self._cli_path:
            logger.info(f"[数据源] {self.name} 初始化完成 (cli={self._cli_path})")
        else:
            logger.warning(
                f"[数据源] {self.name} 未找到 `{CLI_NAME}` 命令,"
                "请先安装 use_cninfo: https://github.com/rollysys/use_cninfo"
            )

    # ------------------------------------------------------------------ public

    def get_periodic_report(
        self,
        stock_code: str,
        year: int,
        kind: str = "annual",
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        获取指定股票指定年份的定期报告本体(年报/一季/中报/三季)。

        Args:
            stock_code: 6 位股票代码,如 "600519"
            year: 报告所属财年,如 2024
            kind: annual / q1 / h1 / q3
            force: 忽略本地缓存重新下载

        Returns:
            {
                "status": "success" | "error",
                "stock_code": "...",
                "report": {
                    "ann_id": "...", "ann_date": "YYYYMMDD",
                    "title": "...", "pdf_path": "...", "md_path": "...",
                    "total_pages": int, "extracted_pages": int,
                    "text_chars": int, "cache_hit": bool,
                },
                "error": "..."  # 仅失败时
            }
        """
        if not self._cli_path:
            return self._cli_missing_response(stock_code)

        cmd = [
            CLI_NAME, "fetch-report", stock_code,
            "--year", str(year), "--kind", kind,
        ]
        if force:
            cmd.append("--force")
        return self._run_json(cmd, stock_code, key="report")

    def get_announcements(
        self,
        stock_code: str,
        since: str,
        until: str,
        download: bool = False,
    ) -> Dict[str, Any]:
        """
        获取指定股票时间窗内全部公告列表(可选下载 + 解析为 md)。

        Args:
            stock_code: 6 位股票代码
            since: 起始日期 YYYY-MM-DD
            until: 截止日期 YYYY-MM-DD
            download: True 时下载并解析 PDF, False 仅列表

        Returns:
            {
                "status": "success" | "error",
                "stock_code": "...",
                "since": "...", "until": "...",
                "total": int,
                "announcements": [ {ann_id, ann_date, title, ...}, ... ],
            }
        """
        if not self._cli_path:
            return self._cli_missing_response(stock_code)

        cmd = [
            CLI_NAME, "fetch-stock", stock_code,
            "--since", since, "--until", until, "--json",
        ]
        if download:
            cmd.append("--download")

        result = self._run_json(cmd, stock_code, key="announcements", as_list=True)
        if result.get("status") == "success":
            result["since"] = since
            result["until"] = until
            result["total"] = len(result.get("announcements", []))
        return result

    # ------------------------------------------------------------------ helpers

    def _cli_missing_response(self, stock_code: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "stock_code": stock_code,
            "fetch_time": datetime.now().isoformat(timespec="seconds"),
            "error": (
                f"`{CLI_NAME}` 命令未安装。装一下:"
                " git clone https://github.com/rollysys/use_cninfo.git"
                " && cd use_cninfo && pip install -e ."
            ),
        }

    def _run_json(
        self,
        cmd: List[str],
        stock_code: str,
        *,
        key: str,
        as_list: bool = False,
    ) -> Dict[str, Any]:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": f"cninfo CLI 超时 ({DEFAULT_TIMEOUT}s)",
            }

        if r.returncode != 0:
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": (r.stderr or r.stdout).strip() or f"exit code {r.returncode}",
            }

        try:
            payload = json.loads(r.stdout)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "stock_code": stock_code,
                "error": f"无法解析 cninfo 输出: {e}; raw={r.stdout[:200]}",
            }

        empty = [] if as_list else None
        if as_list and not isinstance(payload, list):
            payload = empty

        return {
            "status": "success",
            "stock_code": stock_code,
            "fetch_time": datetime.now().isoformat(timespec="seconds"),
            key: payload if (payload or as_list) else empty,
        }
