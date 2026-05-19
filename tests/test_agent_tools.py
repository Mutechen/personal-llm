"""Tests for the skill -> smolagents Tool adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm.agent.tools import VAULT_ROOT_PARAM, build_smolagents_tools
from personal_llm.skills import discover


def test_builtin_read_vault_file_becomes_a_tool(tmp_path: Path):
    """End-to-end: discover -> adapter -> a Tool that actually reads a file."""
    (tmp_path / "hello.md").write_text("hello!\n", encoding="utf-8")

    skills = discover(None)  # builtins only
    tools = build_smolagents_tools(skills, vault_root=tmp_path)

    by_name = {t.name: t for t in tools}
    assert "read_vault_file" in by_name
    tool = by_name["read_vault_file"]

    # Agent sees only relative_path — vault_root was curried in.
    assert "relative_path" in tool.inputs
    assert VAULT_ROOT_PARAM not in tool.inputs
    assert tool.inputs["relative_path"]["type"] == "string"
    assert tool.output_type == "string"

    # Invoking the tool runs the underlying skill. Accept both keyword and
    # positional — smolagents' CodeAgent calls tools positionally.
    assert tool.forward(relative_path="hello.md") == "hello!\n"
    assert tool.forward("hello.md") == "hello!\n"


def test_positional_arg_collision_raises(tmp_path: Path):
    """Passing the same arg both positionally and by keyword is a clear error."""
    skills = discover(None)
    tools = build_smolagents_tools(skills, vault_root=tmp_path)
    tool = next(t for t in tools if t.name == "read_vault_file")
    with pytest.raises(TypeError, match="passed both positionally and as keyword"):
        tool.forward("a.md", relative_path="b.md")


def test_too_many_positional_args_raises(tmp_path: Path):
    skills = discover(None)
    tools = build_smolagents_tools(skills, vault_root=tmp_path)
    tool = next(t for t in tools if t.name == "read_vault_file")
    with pytest.raises(TypeError, match="too many positional arguments"):
        tool.forward("a.md", "b.md")


def test_adapter_skips_skills_without_tool_py(tmp_path: Path):
    """A vault skill (markdown-only) must not show up as a tool."""
    skill_dir = tmp_path / "skills" / "markdown_only"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: markdown_only\ndescription: just instructions\n---\n\nbody\n",
        encoding="utf-8",
    )
    skills = discover(tmp_path)
    tools = build_smolagents_tools(skills, vault_root=tmp_path)
    assert all(t.name != "markdown_only" for t in tools)
    # The builtin should still come through.
    assert any(t.name == "read_vault_file" for t in tools)


def test_tool_surfaces_skill_safety_errors(tmp_path: Path):
    """When the underlying skill raises (e.g. vault escape), the tool propagates."""
    from personal_llm.builtin_skills.read_vault_file.tool import ReadVaultFileError

    skills = discover(None)
    tools = build_smolagents_tools(skills, vault_root=tmp_path)
    tool = next(t for t in tools if t.name == "read_vault_file")
    with pytest.raises(ReadVaultFileError, match="escapes the vault"):
        tool.forward(relative_path="/etc/passwd")


def test_vault_root_required_for_vault_root_skill():
    """If a tool needs vault_root and none is provided, fail loud at build time."""
    skills = discover(None)
    with pytest.raises(RuntimeError, match="requires a vault_root"):
        build_smolagents_tools(skills, vault_root=None)
