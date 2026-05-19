"""Skill library (L5).

Skills are the agent's *abilities*, packaged as directories containing a
SKILL.md file (Anthropic Agent Skills open standard). Phase 1 ships the
discovery + parsing layer; smolagents-driven invocation lands later.

See docs/ARCHITECTURE.md §4 L5 for the full design.
"""

from __future__ import annotations

from personal_llm.skills.model import Skill, SkillSource
from personal_llm.skills.registry import (
    SkillParseError,
    discover,
    parse_skill_md,
)

__all__ = [
    "Skill",
    "SkillParseError",
    "SkillSource",
    "discover",
    "parse_skill_md",
]
