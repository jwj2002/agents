"""Configuration for Daily Standup Agent."""
import os
import platform
from pathlib import Path

# Obsidian vault path - configurable via environment variable
# Falls back to platform-specific defaults
_default_vault_paths = {
    "Darwin": "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault",
    "Linux": "~/obsidian/MyVault",
    "Windows": "~/Documents/ObsidianVault",
}

VAULT_PATH = Path(os.path.expanduser(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        _default_vault_paths.get(platform.system(), "~/obsidian/MyVault")
    )
))

# Projects folder within vault
PROJECTS_FOLDER = VAULT_PATH / "Projects"
