"""Skill dataclass — the in-memory representation of one parsed SKILL.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SkillSource(StrEnum):
    """Where a skill was discovered from. Determines namespace + precedence."""

    VAULT = "vault"      # <vault>/skills/<name>/         — user-authored, highest priority
    BUILTIN = "builtin"  # personal_llm.builtin_skills.   — ships with the package
    IMPORTED = "imported"  # <vault>/skills/imported/<author>/<lobe>/<name>/ — from a lobe


@dataclass(frozen=True)
class Skill:
    """One discovered skill.

    `name` is the unqualified skill name (the directory name containing SKILL.md).
    `qualified_name` distinguishes imported skills, which carry their author/lobe
    in the name to avoid collisions and to make provenance explicit at the call site.
    """

    name: str
    description: str
    source: SkillSource
    path: Path                       # directory containing SKILL.md
    body: str = ""                   # markdown body after the frontmatter
    version: str | None = None
    tags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()  # e.g. ("filesystem", "network", "subprocess")
    author: str | None = None        # only set for IMPORTED skills (from lobe namespace)
    lobe: str | None = None          # only set for IMPORTED skills
    tool_module_path: Path | None = None  # set when a tool.py sibling exists. BUILTIN-only
                                          # for now — vault-authored Python is a separate
                                          # security conversation.
    extra: dict = field(default_factory=dict)  # any other frontmatter keys, untouched

    @property
    def qualified_name(self) -> str:
        if self.source is SkillSource.IMPORTED and self.author and self.lobe:
            return f"{self.author}/{self.lobe}/{self.name}"
        return self.name

    @property
    def skill_md_path(self) -> Path:
        return self.path / "SKILL.md"
