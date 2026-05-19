---
name: read_vault_file
description: Read a UTF-8 text file from inside the user's vault and return its contents.
version: 0.1.0
tags: [vault, filesystem, read-only]
capabilities: [filesystem]
---

# read_vault_file

Read the contents of a single text file located **inside the user's vault** and
return it as a string. This is the smallest useful filesystem skill: it lets the
agent look at the user's notes, identity, growth logs, and any other markdown
they've written, without exposing arbitrary paths on the host.

## Inputs

- `relative_path` (string, required) — path relative to the vault root.
  Example: `wiki/topics/python.md`.

## Behavior

1. Resolve `relative_path` against the vault root.
2. Refuse if the resolved path escapes the vault (no `..` traversal, no
   symlink-out-of-vault). Surface a clear error instead of silently failing.
3. Refuse if the file is larger than 1 MB — chat context is precious; chunk it
   intentionally instead.
4. Return the file contents as a UTF-8 string.

## Errors to surface clearly

- File does not exist (`relative_path` typo or stale reference).
- Path escapes vault (security boundary; not a "file not found").
- File is binary or non-UTF-8 (this skill is for text only).
- File exceeds size limit.

## Not in scope

- Writing or modifying files (that's a separate skill, with stricter sandbox).
- Listing directory contents (separate skill: `list_vault_dir`).
- Reading paths outside the vault (host filesystem access is never part of
  this skill — that's by design, not a missing feature).
