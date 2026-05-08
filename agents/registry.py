"""
Skill 注册机制

提供全局注册表，支持：
  - 按领域注册/发现 Skill
  - Agent 启动时自动加载对应领域的 Skill
  - 动态注册新的 Skill（无需重启）
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from loguru import logger


# 领域 -> signal_type 的映射
DOMAIN_SIGNAL_MAP = {
    "financial": "financial",
    "technical": "technical",
    "fundflow": "fundflow",
    "macro": "macro",
    "industry": "industry",
    "news": "news",
    "risk": "risk",
}


@dataclass
class SkillEntry:
    """注册表中的 Skill 条目"""
    name: str                    # Skill 名称
    domain: str                  # 所属领域
    path: Path                   # SKILL.md 文件路径
    signal_type: str = ""        # 对应的 signal_type
    loaded_content: str = ""     # 加载后的内容（懒加载）


class SkillRegistry:
    """
    Skill 全局注册表

    用法：
        registry = SkillRegistry()
        registry.scan_domain("financial")  # 扫描 skills/financial/ 下所有 Skill
        skills = registry.get_skills_by_domain("financial")
        content = registry.load_skill("cash_flow_quality_check")
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self._entries: Dict[str, SkillEntry] = {}  # name -> SkillEntry
        self._domain_index: Dict[str, List[str]] = {}  # domain -> [skill_names]

        if repo_root is None:
            # 自动查找项目根目录
            for parent in Path(__file__).resolve().parents:
                if (parent / "skills").exists() and (parent / "agents").exists():
                    repo_root = parent
                    break
        self.repo_root = repo_root
        logger.info(f"[SkillRegistry] 初始化，根目录：{repo_root}")

    def scan_domain(self, domain: str) -> int:
        """
        扫描指定领域目录下的所有 Skill 并注册

        Args:
            domain: 领域目录名，如 "financial"

        Returns:
            注册的 Skill 数量
        """
        if self.repo_root is None:
            logger.error("[SkillRegistry] 未设置项目根目录")
            return 0

        domain_dir = self.repo_root / "skills" / domain
        if not domain_dir.exists():
            logger.warning(f"[SkillRegistry] 领域目录不存在：{domain_dir}")
            return 0

        count = 0
        for skill_dir in sorted(domain_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                self.register(
                    name=skill_dir.name,
                    domain=domain,
                    path=skill_file,
                    signal_type=DOMAIN_SIGNAL_MAP.get(domain, domain),
                )
                count += 1

        logger.info(f"[SkillRegistry] 扫描 {domain}/，注册 {count} 个 Skill")
        return count

    def scan_all(self) -> int:
        """扫描所有领域目录"""
        total = 0
        for domain in DOMAIN_SIGNAL_MAP:
            total += self.scan_domain(domain)
        return total

    def register(self, name: str, domain: str, path: Path, signal_type: str = ""):
        """注册一个 Skill"""
        entry = SkillEntry(
            name=name,
            domain=domain,
            path=path,
            signal_type=signal_type or DOMAIN_SIGNAL_MAP.get(domain, domain),
        )
        self._entries[name] = entry

        if domain not in self._domain_index:
            self._domain_index[domain] = []
        if name not in self._domain_index[domain]:
            self._domain_index[domain].append(name)

    def load_skill(self, name: str) -> Optional[str]:
        """加载指定 Skill 的内容（懒加载，首次调用时读取文件）"""
        entry = self._entries.get(name)
        if entry is None:
            logger.warning(f"[SkillRegistry] Skill 未注册：{name}")
            return None

        if not entry.loaded_content:
            try:
                entry.loaded_content = entry.path.read_text(encoding="utf-8")
                logger.info(f"[SkillRegistry] 已加载 Skill：{name}")
            except FileNotFoundError:
                logger.error(f"[SkillRegistry] Skill 文件不存在：{entry.path}")
                return None

        return entry.loaded_content

    def get_skills_by_domain(self, domain: str) -> List[SkillEntry]:
        """获取指定领域的所有 Skill"""
        names = self._domain_index.get(domain, [])
        return [self._entries[n] for n in names if n in self._entries]

    def get_skill(self, name: str) -> Optional[SkillEntry]:
        """获取指定 Skill 的注册信息"""
        return self._entries.get(name)

    def list_all(self) -> List[SkillEntry]:
        """列出所有已注册的 Skill"""
        return list(self._entries.values())

    def list_domains(self) -> List[str]:
        """列出所有已注册的领域"""
        return list(self._domain_index.keys())


# 全局单例
_global_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """获取全局 Skill 注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
        _global_registry.scan_all()
    return _global_registry
