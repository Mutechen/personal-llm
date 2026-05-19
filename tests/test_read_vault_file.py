"""Safety-check tests for the read_vault_file builtin skill.

These pin down the security boundary that keeps the agent from being tricked
(or tricking itself) into reading host files outside the vault.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from personal_llm.builtin_skills.read_vault_file.tool import (
    MAX_BYTES,
    ReadVaultFileError,
    run,
)


def test_reads_simple_file(tmp_path: Path):
    (tmp_path / "hello.md").write_text("# hi\n", encoding="utf-8")
    assert run(tmp_path, "hello.md") == "# hi\n"


def test_reads_nested_file(tmp_path: Path):
    nested = tmp_path / "wiki" / "topics"
    nested.mkdir(parents=True)
    (nested / "python.md").write_text("notes", encoding="utf-8")
    assert run(tmp_path, "wiki/topics/python.md") == "notes"


def test_rejects_dotdot_escape(tmp_path: Path):
    """`../foo` must be rejected even if foo exists on the host."""
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        with pytest.raises(ReadVaultFileError, match="escapes the vault"):
            run(tmp_path, f"../{outside.name}")
    finally:
        outside.unlink(missing_ok=True)


def test_rejects_absolute_path_outside_vault(tmp_path: Path):
    """An absolute path that resolves outside the vault must be rejected.

    Note: Path('/etc/passwd') joined onto vault_root resolves to /etc/passwd
    (absolute components reset the join), so this would otherwise leak.
    """
    with pytest.raises(ReadVaultFileError, match="escapes the vault"):
        run(tmp_path, "/etc/passwd")


def test_rejects_symlink_pointing_outside(tmp_path: Path):
    """A symlink inside the vault that resolves outside it must be rejected.

    This is the subtle case the resolve() + is_relative_to() guard catches.
    """
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("nope", encoding="utf-8")
    link = tmp_path / "looks_inside.md"
    try:
        os.symlink(outside, link)
        with pytest.raises(ReadVaultFileError, match="escapes the vault"):
            run(tmp_path, "looks_inside.md")
    finally:
        link.unlink(missing_ok=True)
        outside.unlink(missing_ok=True)


def test_missing_file_is_clear_error(tmp_path: Path):
    with pytest.raises(ReadVaultFileError, match="file not found in vault"):
        run(tmp_path, "nope.md")


def test_directory_is_rejected(tmp_path: Path):
    (tmp_path / "adir").mkdir()
    with pytest.raises(ReadVaultFileError, match="not a regular file"):
        run(tmp_path, "adir")


def test_empty_relative_path_rejected(tmp_path: Path):
    with pytest.raises(ReadVaultFileError, match="must not be empty"):
        run(tmp_path, "")


def test_oversize_file_rejected(tmp_path: Path):
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (MAX_BYTES + 1))
    with pytest.raises(ReadVaultFileError, match="exceeds"):
        run(tmp_path, "big.txt")


def test_binary_file_rejected(tmp_path: Path):
    binfile = tmp_path / "blob.bin"
    binfile.write_bytes(b"\x00\xff\xfe\xfd binary noise")
    with pytest.raises(ReadVaultFileError, match="not valid UTF-8"):
        run(tmp_path, "blob.bin")
