"""Tests for the SKILL.md discovery + parsing layer.

This is the first test in the repo. It nails down the namespace precedence
rules from ARCHITECTURE.md §4 L5 so we don't regress them as Phase 1 fills in
agent-loop invocation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm.skills import SkillParseError, discover, parse_skill_md
from personal_llm.skills.model import SkillSource

# ---------------------------------------------------------------------------- helpers


def write_skill(dir_: Path, name: str, description: str, **frontmatter: object) -> Path:
    """Create <dir_>/<name>/SKILL.md with the given frontmatter. Returns the skill dir."""
    skill_dir = dir_ / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", f"description: {description}"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v!r}" if isinstance(v, str) else f"{k}: {v}")
    lines += ["---", "", f"# {name}", "", "Body."]
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_dir


# ---------------------------------------------------------------------------- builtins


def test_builtin_read_vault_file_is_discovered():
    """The bundled read_vault_file skill must always be visible (no vault required)."""
    skills = discover(None)
    names = {s.name for s in skills}
    assert "read_vault_file" in names
    skill = next(s for s in skills if s.name == "read_vault_file")
    assert skill.source is SkillSource.BUILTIN
    assert "filesystem" in skill.capabilities


# ---------------------------------------------------------------------------- vault


def test_vault_skill_appears_alongside_builtin(tmp_path: Path):
    write_skill(tmp_path / "skills", "do_a_thing", "user-authored skill")
    skills = discover(tmp_path)
    by_name = {s.name: s for s in skills}
    assert by_name["do_a_thing"].source is SkillSource.VAULT
    assert "read_vault_file" in by_name  # builtin still present


def test_vault_skill_overrides_builtin_on_name_collision(tmp_path: Path):
    """A vault skill named the same as a builtin must hide the builtin."""
    write_skill(tmp_path / "skills", "read_vault_file", "my override")
    skills = discover(tmp_path)
    matching = [s for s in skills if s.name == "read_vault_file"]
    assert len(matching) == 1, "builtin should be shadowed, not duplicated"
    assert matching[0].source is SkillSource.VAULT
    assert matching[0].description == "my override"


# ---------------------------------------------------------------------------- imported


def test_imported_skill_uses_qualified_name_and_never_overrides(tmp_path: Path):
    """Imported skills are visible only by author/lobe/name. They can collide
    with bare names without shadowing the trusted skill."""
    imported = tmp_path / "skills" / "imported" / "alice" / "filesystem-tools"
    write_skill(imported, "read_vault_file", "alice's flavor")

    skills = discover(tmp_path)
    bare = [s for s in skills if s.name == "read_vault_file" and s.source is SkillSource.BUILTIN]
    imported_skills = [s for s in skills if s.source is SkillSource.IMPORTED]
    assert len(bare) == 1, "builtin must still own the bare name"
    assert len(imported_skills) == 1
    imp = imported_skills[0]
    assert imp.author == "alice"
    assert imp.lobe == "filesystem-tools"
    assert imp.qualified_name == "alice/filesystem-tools/read_vault_file"


# ---------------------------------------------------------------------------- parsing errors


def test_missing_frontmatter_raises(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="missing YAML frontmatter"):
        discover(tmp_path)


def test_missing_name_field_raises(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "nameless"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: no name\n---\n\nbody\n", encoding="utf-8"
    )
    with pytest.raises(SkillParseError, match="missing or non-string `name`"):
        discover(tmp_path)


def test_unterminated_frontmatter_raises(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "unterm"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: x\ndescription: y\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="not terminated"):
        discover(tmp_path)


def test_capabilities_must_be_strings(tmp_path: Path):
    skill_dir = tmp_path / "skills" / "bad_caps"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: bad_caps\ndescription: d\ncapabilities: [1, 2]\n---\n\nb\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillParseError, match="`capabilities` must be a list of strings"):
        discover(tmp_path)


# ---------------------------------------------------------------------------- direct parse


def test_parse_skill_md_preserves_unknown_frontmatter_in_extra(tmp_path: Path):
    skill_dir = tmp_path / "future_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: future\ndescription: d\nfuture_field: hello\n---\n\nbody\n",
        encoding="utf-8",
    )
    skill = parse_skill_md(skill_dir / "SKILL.md", SkillSource.VAULT)
    assert skill.extra == {"future_field": "hello"}
