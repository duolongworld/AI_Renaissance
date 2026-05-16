"""
Agent基类 - 所有Agent的父类

8 Agent + N Skill 架构下：
  - 每个 Agent 原生继承 AgentScope AgentBase，可通过 Msg 调用
  - 每个 Agent 可通过 load_skill() 动态加载 Skill
  - 每个 Agent 有 signal_type 属性，标识输出信号类型
  - Orchestrator Agent 不加载 Skill，负责编排仲裁
"""

import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger
from agentscope.agent import AgentBase as AgentScopeAgentBase

from agents.agentscope_message import (
    AgentScopeMessageError,
    extract_stock_code,
    signal_to_msg,
)
from agents.signal import Signal


class AgentContractError(RuntimeError):
    """Raised when an Agent violates the project-level Signal contract."""


class BaseAgent(AgentScopeAgentBase):
    """
    所有 Agent 的基类，同时也是 AgentScope-native Agent。

    子类需要实现:
    - name: Agent名称
    - signal_type: 信号类型标识
    - analyze(): 核心分析逻辑，返回标准 Signal

    可选:
    - load_skill(): 加载指定 Skill
    - list_skills(): 列出已加载的 Skill
    """

    # 子类可覆盖的类属性
    signal_type: str = ""  # 如 "financial", "technical", "fundflow" 等

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        if self.__class__.analyze is BaseAgent.analyze:
            raise TypeError(f"{self.__class__.__name__} must implement analyze()")

        super().__init__()
        self.name = name
        self.config = config or {}
        self._skills: Dict[str, str] = {}  # skill_name -> skill_content
        self._skill_paths: Dict[str, Path] = {}  # skill_name -> skill_path
        self._observed_messages: List[Any] = []
        logger.info(f"[{self.name}] Agent initialized (signal_type={self.signal_type})")

    # ── Skill 管理 ──────────────────────────────────────────

    def load_skill(self, skill_path: str, skill_name: Optional[str] = None) -> None:
        """
        加载一个 Skill 文件

        Args:
            skill_path: SKILL.md 文件路径
            skill_name: Skill 名称（默认用路径的倒数第二级目录名）
        """
        path = Path(skill_path)
        if not path.exists():
            logger.error(f"[{self.name}] Skill 文件不存在：{skill_path}")
            return

        if skill_name is None:
            skill_name = path.parent.name  # skills/financial/xxx/SKILL.md -> xxx

        content = path.read_text(encoding="utf-8")
        self._skills[skill_name] = content
        self._skill_paths[skill_name] = path
        logger.info(f"[{self.name}] 已加载 Skill：{skill_name}")

    def load_skills_from_domain(self, domain: str) -> int:
        """
        从 skills/{domain}/ 目录批量加载所有 Skill

        Args:
            domain: Skill 领域目录名，如 "financial", "technical"

        Returns:
            加载的 Skill 数量
        """
        repo_root = self._find_repo_root()
        domain_dir = repo_root / "skills" / domain
        if not domain_dir.exists():
            logger.warning(f"[{self.name}] Skill 领域目录不存在：{domain_dir}")
            return 0

        count = 0
        for skill_dir in sorted(domain_dir.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                self.load_skill(str(skill_file), skill_dir.name)
                count += 1

        logger.info(f"[{self.name}] 从 {domain}/ 加载了 {count} 个 Skill")
        return count

    def get_skill(self, skill_name: str) -> Optional[str]:
        """获取已加载的 Skill 内容"""
        return self._skills.get(skill_name)

    def list_skills(self) -> List[str]:
        """列出已加载的 Skill 名称"""
        return list(self._skills.keys())

    # ── 核心接口 ──────────────────────────────────────────

    def analyze(self, *args, **kwargs):
        """
        核心分析逻辑（子类必须实现）

        Returns:
            Signal: 标准化的信号对象
        """
        raise NotImplementedError(f"{self.__class__.__name__}.analyze() is not implemented")

    async def reply(self, msg: Any) -> Any:
        """AgentScope 调用入口：Msg -> analyze(stock_code) -> Signal Msg。"""
        try:
            stock_code = extract_stock_code(msg)
        except AgentScopeMessageError:
            raise
        except Exception as exc:
            raise AgentScopeMessageError(f"invalid AgentScope task message: {exc}") from exc

        signal = await asyncio.to_thread(self.analyze, stock_code)
        if not isinstance(signal, Signal):
            raise AgentContractError(
                f"{self.name} returned {type(signal).__name__}, expected Signal",
            )

        return signal_to_msg(signal, name=self.name)

    async def observe(self, msg: Any | List[Any] | None) -> None:
        """记录 AgentScope 观察消息；当前项目不在 observe 中触发业务副作用。"""
        if msg is None:
            return
        if isinstance(msg, list):
            self._observed_messages.extend(msg)
        else:
            self._observed_messages.append(msg)

    async def handle_interrupt(self, *args, **kwargs) -> Any:
        """向上抛出取消，让 Orchestrator 将 wait_for 取消记录为 timeout。"""
        raise asyncio.CancelledError()

    def pre_analyze(self, *args, **kwargs) -> Dict[str, Any]:
        """
        前置处理（可选重写）
        数据获取、预处理等
        """
        return {}

    def post_analyze(self, signal, *args, **kwargs):
        """
        后置处理（可选重写）
        信号校验、日志记录等
        """
        return signal

    def run(self, *args, **kwargs):
        """
        Agent执行入口（模板方法模式）
        """
        # 1. 前置处理
        context = self.pre_analyze(*args, **kwargs)

        # 2. 核心分析
        signal = self.analyze(*args, **kwargs, **context)

        # 3. 后置处理
        signal = self.post_analyze(signal, *args, **kwargs)

        return signal

    # ── 工具方法 ──────────────────────────────────────────

    def log(self, message: str, level: str = "info"):
        """统一的日志记录"""
        getattr(logger, level)(f"[{self.name}] {message}")

    def _find_repo_root(self) -> Path:
        """查找项目根目录"""
        for parent in Path(__file__).resolve().parents:
            if (parent / "skills").exists() and (parent / "agents").exists():
                return parent
        raise RuntimeError("找不到项目根目录")
