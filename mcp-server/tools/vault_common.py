"""Shared utilities for vault access."""
from __future__ import annotations

import os
import platform
from pathlib import Path


def get_vault_path() -> Path:
    """Get Obsidian vault path from environment or platform default."""
    if env_path := os.environ.get("OBSIDIAN_VAULT_PATH"):
        return Path(env_path).expanduser()

    defaults = {
        "Darwin": "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault",
        "Linux": "~/obsidian-vault",
        "Windows": "~/Documents/ObsidianVault",
    }
    return Path(defaults.get(platform.system(), "~/obsidian-vault")).expanduser()


def get_project_memory_dir(project_path: str | None = None) -> Path:
    """Get .claude/memory/ directory for a project."""
    if project_path:
        return Path(project_path) / ".claude" / "memory"

    # Try CLAUDE_PROJECT_DIR env var
    if proj_dir := os.environ.get("CLAUDE_PROJECT_DIR"):
        return Path(proj_dir) / ".claude" / "memory"

    return Path.cwd() / ".claude" / "memory"
