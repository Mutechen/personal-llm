"""Implementation of the read_vault_file skill.

The skill spec is in the sibling SKILL.md. This module supplies the Python
callable that the smolagents adapter wraps as a tool. The agent never sees
`vault_root` — the adapter currys it in. From the agent's perspective the
tool takes one argument, `relative_path`, and either returns the file contents
as a string or raises with a clear message.

Safety checks (in order):
  1. The resolved path must stay inside the vault. No `..` traversal, no
     symlink-out-of-vault. This is a security boundary, not "file not found."
  2. The path must exist and be a regular file.
  3. The file must be ≤ MAX_BYTES. Chat context is precious; chunk intentionally.
  4. The file must decode as UTF-8. Binary files are out of scope.
"""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 1_000_000  # 1 MB — see SKILL.md


class ReadVaultFileError(ValueError):
    """Raised when a read_vault_file call cannot or should not proceed.

    The agent sees the message verbatim, so phrase it for the agent's benefit
    (clear about *why* — escape vs. missing vs. binary vs. oversize).
    """


def run(vault_root: Path, relative_path: str) -> str:
    """Read a UTF-8 text file inside the vault. See module docstring."""
    vault_root = Path(vault_root).resolve()
    if not relative_path:
        raise ReadVaultFileError("relative_path must not be empty")

    candidate = (vault_root / relative_path).resolve()
    # is_relative_to handles both ../ traversal and symlink-out-of-vault, because
    # we resolved both paths. A symlink inside the vault pointing outward will
    # resolve to a path outside and fail this check.
    if not candidate.is_relative_to(vault_root):
        raise ReadVaultFileError(
            f"{relative_path}: path escapes the vault. Only paths inside the vault are allowed."
        )

    if not candidate.exists():
        raise ReadVaultFileError(f"{relative_path}: file not found in vault")
    if not candidate.is_file():
        raise ReadVaultFileError(f"{relative_path}: not a regular file")

    size = candidate.stat().st_size
    if size > MAX_BYTES:
        raise ReadVaultFileError(
            f"{relative_path}: file is {size} bytes, exceeds {MAX_BYTES}-byte limit. "
            "Ask for a specific section or use a chunked-read skill instead."
        )

    try:
        return candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise ReadVaultFileError(
            f"{relative_path}: file is not valid UTF-8 text. "
            "This skill is for text files only."
        ) from e
