"""Adapter that turns discovered Skills into smolagents Tools.

A Skill that ships a `tool.py` (BUILTIN only — see registry.py) is wrapped here
into a smolagents `Tool` subclass the `CodeAgent` can call. Skills without a
`tool.py` are not yet invocable; they need either a future Python implementation
or the (also future) "instructions-only" agent path that uses general tools to
follow markdown directions.

The agent never sees `vault_root`. Skills that need it declare a `vault_root:
Path` parameter as their first positional arg and the adapter currys it in.
This is the boundary that keeps "read a file from your vault" from accidentally
becoming "read a file from anywhere on the host."
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from smolagents import Tool

from personal_llm.skills.model import Skill, SkillSource

# Python type -> smolagents JSON-schema-ish type tag.
# smolagents recognizes: string, integer, number, boolean, array, object, image,
# audio, any, null. We only handle the basics — extend when a real skill needs more.
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# Signature param name that means "the adapter currys this in, don't expose it."
VAULT_ROOT_PARAM = "vault_root"


def build_smolagents_tools(skills: list[Skill], vault_root: Path | None) -> list[Tool]:
    """Wrap each invocable skill into a smolagents Tool instance.

    Skills without a tool_module_path are silently skipped — they're discoverable
    but not yet runnable. That's fine; the agent still benefits from knowing they
    exist (future: list them in the system prompt).
    """
    tools: list[Tool] = []
    for skill in skills:
        if skill.tool_module_path is None:
            continue
        if skill.source is not SkillSource.BUILTIN:
            # Defense in depth — the registry already blocks this, but guard anyway.
            continue
        tools.append(_build_tool(skill, vault_root))
    return tools


def _build_tool(skill: Skill, vault_root: Path | None) -> Tool:
    """Construct a Tool instance for one skill. Lazy-imports the skill's module."""
    module = _import_tool_module(skill)
    run_fn = getattr(module, "run", None)
    if not callable(run_fn):
        raise RuntimeError(
            f"Skill {skill.name!r}: {skill.tool_module_path} must define a callable `run`."
        )

    sig = inspect.signature(run_fn)
    params = list(sig.parameters.values())
    needs_vault_root = bool(params) and params[0].name == VAULT_ROOT_PARAM
    exposed_params = params[1:] if needs_vault_root else params

    if needs_vault_root and vault_root is None:
        raise RuntimeError(
            f"Skill {skill.name!r} requires a vault_root but none was provided. "
            "Run `personal-llm init` to create a vault, or pass --vault."
        )

    inputs = _params_to_inputs(skill, exposed_params)
    output_type = _annotation_to_type(sig.return_annotation) or "string"

    # Order of parameters as declared in the underlying run() signature, used
    # to map positional args from the agent back to keyword args for run_fn.
    # The agent (CodeAgent) often calls tools positionally, e.g. `tool("foo")`.
    param_names = [p.name for p in exposed_params]

    # Build a Tool subclass per skill. We close over run_fn + vault_root inside
    # forward() — smolagents' Tool base doesn't use inspect.getsource on subclasses,
    # so closures are safe (unlike the @tool decorator path).
    # `skip_forward_signature_validation` is smolagents' documented escape hatch
    # for dynamically-wrapped tools — without it, the *args/**kwargs forward fails
    # the "params must match inputs keys exactly" check at __init__ time.
    class _SkillTool(Tool):
        name = skill.name
        description = skill.description
        skip_forward_signature_validation = True

        def forward(self, *args: Any, **kwargs: Any) -> Any:
            # Map positional args to their declared parameter names. smolagents'
            # CodeAgent generates Python that calls tools positionally; without
            # this mapping the model has to guess kwargs and burn steps recovering.
            for i, value in enumerate(args):
                if i >= len(param_names):
                    raise TypeError(
                        f"{skill.name}: too many positional arguments "
                        f"(expected at most {len(param_names)}, got {len(args)})"
                    )
                key = param_names[i]
                if key in kwargs:
                    raise TypeError(
                        f"{skill.name}: argument {key!r} passed both positionally and as keyword"
                    )
                kwargs[key] = value
            if needs_vault_root:
                return run_fn(vault_root, **kwargs)
            return run_fn(**kwargs)

    _SkillTool.inputs = inputs
    _SkillTool.output_type = output_type
    _SkillTool.__name__ = f"SkillTool_{skill.name}"
    return _SkillTool()


def _import_tool_module(skill: Skill):
    """Lazy-import the tool.py module.

    BUILTIN skills live at a known package path, so we use the real import
    machinery. This preserves class identity — exceptions raised inside the
    skill are catchable as the same class callers imported normally.
    """
    assert skill.tool_module_path is not None
    if skill.source is SkillSource.BUILTIN:
        return importlib.import_module(f"personal_llm.builtin_skills.{skill.name}.tool")
    # No vault/imported tool.py loading in this phase — registry guards against it
    # and build_smolagents_tools filters earlier. Surface a clear error if we get here.
    raise RuntimeError(
        f"Cannot load tool.py for non-builtin skill {skill.name!r}: "
        "user-authored skill code is not enabled in this phase."
    )


def _params_to_inputs(skill: Skill, params: list[inspect.Parameter]) -> dict[str, dict]:
    """Build smolagents `inputs` dict from a function's parameter list."""
    out: dict[str, dict] = {}
    for p in params:
        type_tag = _annotation_to_type(p.annotation) or "string"
        entry: dict[str, Any] = {
            "type": type_tag,
            "description": f"{p.name} (see {skill.name} SKILL.md for details)",
        }
        if p.default is not inspect.Parameter.empty:
            entry["nullable"] = True
        out[p.name] = entry
    return out


def _annotation_to_type(ann) -> str | None:
    """Map a Python type annotation to a smolagents type tag. Returns None on no match."""
    if ann is inspect.Parameter.empty or ann is inspect.Signature.empty:
        return None
    # Strip Path → "string" (paths are passed over the wire as strings anyway).
    if ann is Path:
        return "string"
    return _TYPE_MAP.get(ann)
