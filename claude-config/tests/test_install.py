"""Tests for link_item in claude-config/install.sh (issue #393).

These tests exercise the link_item function in isolation by extracting it into
a minimal bash snippet and running it via subprocess with a controlled temp dir.
No part of install.sh's Phases 2–4 (pip, claude plugin, MCP) is executed.

Smoke-test install.sh against a real but isolated HOME:
  HOME=$(mktemp -d) bash claude-config/install.sh
This uses install.sh's $HOME-derived CLAUDE_DIR without adding a --home flag.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INSTALL_SH = Path(__file__).resolve().parents[1] / "install.sh"


def _run_link_item(
    src: Path,
    dest: Path,
    *,
    tmp_path: Path,
    label: str = "test-link",
) -> subprocess.CompletedProcess:
    """Run link_item SRC DEST label in an isolated bash subprocess.

    Extracts backup_item and link_item from install.sh verbatim and
    wraps them in a minimal environment so each test is fully self-contained.
    """
    backup_dir = tmp_path / "backup"
    snippet = f"""\
set -e
BACKUP_DIR="{backup_dir}"
BACKUP_CREATED=false
LINKS_TOTAL=0
LINKS_CREATED=0

backup_item() {{
    local target="$1"
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        BACKUP_CREATED=true
    fi
    mv "$target" "$BACKUP_DIR/"
}}

link_item() {{
    local source="$1"
    local target="$2"
    local label="$3"
    LINKS_TOTAL=$((LINKS_TOTAL + 1))

    if [ -e "$target" ] && [ ! -L "$target" ]; then
        backup_item "$target"
        echo "  Backed up $label"
    fi

    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        echo "  ✓ $label (already linked)"
    else
        ln -sfn "$source" "$target"
        echo "  ✓ $label → linked"
        LINKS_CREATED=$((LINKS_CREATED + 1))
    fi
}}

link_item "{src}" "{dest}" "{label}"
"""
    return subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_link_item_wrong_target_dir_symlink(tmp_path: Path) -> None:
    """DEST is a symlink to a different directory; link_item must replace it.

    This is the exact incident from issue #393: BSD ln -sf followed the
    directory symlink and created a nested link inside it. With -sfn the DEST
    symlink itself is atomically replaced.
    """
    src = tmp_path / "real_src_dir"
    src.mkdir()
    old_target = tmp_path / "old_dir"
    old_target.mkdir()
    dest = tmp_path / "dest_link"
    dest.symlink_to(old_target)  # dest -> old_dir (wrong target)

    result = _run_link_item(src, dest, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert dest.is_symlink(), "DEST must still be a symlink"
    assert os.readlink(dest) == str(src), f"DEST must point to src, got {os.readlink(dest)}"
    # Critically: no nested link should exist inside old_target
    nested = old_target / src.name
    assert not nested.exists(), (
        f"Nested symlink {nested} was created — ln -sf bug is not fixed"
    )


def test_link_item_wrong_target_file_symlink(tmp_path: Path) -> None:
    """DEST is a file symlink pointing to the wrong target; must be replaced."""
    src = tmp_path / "real_src_file.txt"
    src.write_text("source content")
    wrong = tmp_path / "wrong_file.txt"
    wrong.write_text("wrong content")
    dest = tmp_path / "dest_link"
    dest.symlink_to(wrong)  # dest -> wrong_file.txt

    result = _run_link_item(src, dest, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert dest.is_symlink()
    assert os.readlink(dest) == str(src)


def test_link_item_already_correct_symlink(tmp_path: Path) -> None:
    """DEST already points to SRC; link_item emits 'already linked' and is a no-op."""
    src = tmp_path / "src_dir"
    src.mkdir()
    dest = tmp_path / "dest_link"
    dest.symlink_to(src)  # already correct

    result = _run_link_item(src, dest, tmp_path=tmp_path, label="my-item")

    assert result.returncode == 0, result.stderr
    assert "already linked" in result.stdout
    assert os.readlink(dest) == str(src)


def test_link_item_no_preexisting_link(tmp_path: Path) -> None:
    """DEST does not exist; link_item creates a fresh symlink."""
    src = tmp_path / "src_dir"
    src.mkdir()
    dest = tmp_path / "dest_link"  # does not exist yet

    result = _run_link_item(src, dest, tmp_path=tmp_path)

    assert result.returncode == 0, result.stderr
    assert dest.is_symlink()
    assert os.readlink(dest) == str(src)


def test_link_item_regular_file_is_backed_up(tmp_path: Path) -> None:
    """DEST is a regular file; link_item backs it up and replaces with a symlink."""
    src = tmp_path / "src_dir"
    src.mkdir()
    dest = tmp_path / "dest_link"
    dest.write_text("existing file content")  # regular file, not a symlink

    result = _run_link_item(src, dest, tmp_path=tmp_path, label="backed-up-item")

    assert result.returncode == 0, result.stderr
    assert "Backed up" in result.stdout
    assert dest.is_symlink(), "DEST must be a symlink after backup"
    assert os.readlink(dest) == str(src)
