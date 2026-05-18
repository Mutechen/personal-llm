# skills/

Your skill library. Each skill is a directory containing a `SKILL.md` file,
following the [Anthropic Agent Skills](https://github.com/anthropics/skills)
open standard.

## Layout

```
skills/
  <your-skill>/
    SKILL.md         # YAML frontmatter (name, description, …) + markdown body
    scripts/         # optional — executable artifacts the skill references
    references/      # optional — supporting docs, examples, schemas
    assets/          # optional — non-text resources
    tests/           # convention — programmatic tests (required for promotion)
    CHANGELOG.md     # convention — versioned edit history
  imported/
    <author>/
      <lobe>/
        <skill>/...  # skills installed from a lobe (see docs §6)
```

## Namespace precedence (when the agent looks up "skill X")

1. `skills/X/` — your own skills. Highest priority. **You always win.**
2. `personal_llm.builtin_skills.X` — skills that ship with the package.
3. `skills/imported/<author>/<lobe>/X/` — skills from imported lobes.

Imported skills are *never* shadow-promoted into the bare namespace, even if
they share a name with a builtin. They're always callable, but only by their
fully-qualified `author/lobe/name` form. This is what makes installing a lobe
safe — it can't silently replace trusted code.

## Minimal SKILL.md

```markdown
---
name: my_skill
description: One sentence the agent reads to decide whether to invoke this.
version: 0.1.0
tags: [example]
capabilities: [filesystem]
---

# my_skill

Instructions for the agent on when and how to use this skill.
```

## See also

- `docs/ARCHITECTURE.md` §4 L5 — the skill library design.
- `personal-llm skills list` — show what's currently discovered.
