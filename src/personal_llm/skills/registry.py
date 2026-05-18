"""SKILL.md discovery, parsing, and namespace merging.

The agent (Phase 1+) calls `discover(vault_path)` to get the merged skill list
that's currently invokable. Three sources are scanned, in precedence order:

    1. <vault>/skills/<name>/SKILL.md          (VAULT)    — user wins
    2. personal_llm.builtin_skills.<name>      (BUILTIN)  — package-shipped
    3. <vault>/skills/imported/<author>/<lobe>/<name>/SKILL.md  (IMPORTED) — lobes

VAULT and BUILTIN compete on bare names: a vault skill named "search" hides the
builtin "search". IMPORTED skills are *never* shadow-promoted into the bare
namespace — they're always callable, but only by their `author/lobe/name`
qualified form. This is the rule that makes installing a lobe safe.

Failure mode: a malformed SKILL.md raises SkillParseError immediately. We don't
silently skip — the user needs to know which file in their vault is broken.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from personal_llm.skills.model import Skill, SkillSource

SKILL_FILENAME = "SKILL.md"


class SkillParseError(ValueError):
    """Raised when a SKILL.md is missing required fields or has invalid frontmatter."""


def discover(vault_path: Path | None) -> list[Skill]:
    """Return all currently-invokable skills, deduped by precedence.

    vault_path can be None (e.g. unit tests, or pre-init) — in that case only
    BUILTIN skills are returned.
    """
    vault_skills = _discover_dir(vault_path / "skills", SkillSource.VAULT) if vault_path else []
    builtin_skills = _discover_builtins()
    imported_skills = (
        _discover_imported(vault_path / "skills" / "imported") if vault_path else []
    )

    # VAULT > BUILTIN on bare names. Build a name set from VAULT, then add only
    # non-colliding BUILTINs. IMPORTED skills always go in (they never collide
    # because their qualified_name carries author/lobe).
    taken: set[str] = {s.name for s in vault_skills}
    merged: list[Skill] = list(vault_skills)
    for s in builtin_skills:
        if s.name not in taken:
            merged.append(s)
            taken.add(s.name)
    merged.extend(imported_skills)
    return merged


def parse_skill_md(path: Path, source: SkillSource) -> Skill:
    """Parse a single SKILL.md file into a Skill.

    `path` is the SKILL.md file itself. The skill's directory is `path.parent`
    and is what callers reference for scripts/, references/, etc.
    """
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text, path)

    name = frontmatter.pop("name", None)
    description = frontmatter.pop("description", None)
    if not name or not isinstance(name, str):
        raise SkillParseError(f"{path}: missing or non-string `name` in frontmatter")
    if not description or not isinstance(description, str):
        raise SkillParseError(f"{path}: missing or non-string `description` in frontmatter")

    version = frontmatter.pop("version", None)
    tags = _as_tuple_of_strings(frontmatter.pop("tags", ()), path, "tags")
    capabilities = _as_tuple_of_strings(
        frontmatter.pop("capabilities", ()), path, "capabilities"
    )

    return Skill(
        name=name,
        description=description.strip(),
        source=source,
        path=path.parent,
        body=body.strip(),
        version=str(version) if version is not None else None,
        tags=tags,
        capabilities=capabilities,
        extra=frontmatter,  # whatever else the user put in frontmatter, preserved verbatim
    )


# ---------------------------------------------------------------------------- internals


def _discover_dir(root: Path, source: SkillSource) -> list[Skill]:
    """Find all <root>/<name>/SKILL.md (one level deep). Skips `imported/`."""
    if not root.is_dir():
        return []
    out: list[Skill] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name == "imported":
            continue
        skill_md = child / SKILL_FILENAME
        if skill_md.is_file():
            out.append(parse_skill_md(skill_md, source))
    return out


def _discover_builtins() -> list[Skill]:
    """Walk personal_llm/builtin_skills/*/SKILL.md inside the installed package."""
    here = Path(__file__).resolve()
    builtins_dir = here.parent.parent / "builtin_skills"
    return _discover_dir(builtins_dir, SkillSource.BUILTIN)


def _discover_imported(imported_root: Path) -> list[Skill]:
    """Walk <vault>/skills/imported/<author>/<lobe>/<name>/SKILL.md (3 levels deep)."""
    if not imported_root.is_dir():
        return []
    out: list[Skill] = []
    for author_dir in sorted(imported_root.iterdir()):
        if not author_dir.is_dir():
            continue
        for lobe_dir in sorted(author_dir.iterdir()):
            if not lobe_dir.is_dir():
                continue
            for skill_dir in sorted(lobe_dir.iterdir()):
                skill_md = skill_dir / SKILL_FILENAME
                if skill_dir.is_dir() and skill_md.is_file():
                    parsed = parse_skill_md(skill_md, SkillSource.IMPORTED)
                    out.append(replace(parsed, author=author_dir.name, lobe=lobe_dir.name))
    return out


def _split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """Split a `---\\nyaml\\n---\\nbody` document. Frontmatter is required."""
    if not text.startswith("---"):
        raise SkillParseError(f"{path}: missing YAML frontmatter (file must start with `---`)")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillParseError(f"{path}: frontmatter not terminated (no closing `---`)")
    try:
        loaded = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"{path}: invalid YAML frontmatter: {e}") from e
    if not isinstance(loaded, dict):
        raise SkillParseError(f"{path}: frontmatter must be a YAML mapping, got {type(loaded).__name__}")
    return loaded, parts[2]


def _as_tuple_of_strings(value, path: Path, field_name: str) -> tuple[str, ...]:
    if value in (None, "", []):
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        if not all(isinstance(v, str) for v in value):
            raise SkillParseError(f"{path}: `{field_name}` must be a list of strings")
        return tuple(value)
    raise SkillParseError(f"{path}: `{field_name}` must be a string or list of strings")
