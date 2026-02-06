"""Configuration loader for Obsidian Second Brain Agent.

Precedence: TOML config > env vars > platform defaults.
"""
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

# Python 3.11+ has tomllib in stdlib
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

CONFIG_DIR = Path.home() / ".config" / "obsidian-agent"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Config:
    """Agent configuration."""
    vault_path: Path
    claude_projects_path: Path
    projects_folder: str  # subfolder name inside vault (default: "Projects")
    extraction_model: str  # claude model for extraction (default: "haiku")
    max_conversation_chars: int  # truncation limit (default: 50000)

    @property
    def projects_path(self) -> Path:
        """Full path to the projects folder inside the vault."""
        return self.vault_path / self.projects_folder


def _platform_default_vault() -> Path:
    """Return platform-specific default vault path."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents" / "MyVault"
    elif system == "Windows":
        return Path.home() / "Documents" / "ObsidianVault"
    else:
        # Linux / WSL
        return Path.home() / "obsidian" / "MyVault"


def _load_toml() -> dict:
    """Load TOML config file if it exists."""
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


def load_config() -> Config:
    """Load configuration with precedence: TOML > env vars > platform defaults."""
    toml = _load_toml()
    vault_section = toml.get("vault", {})
    claude_section = toml.get("claude", {})
    extraction_section = toml.get("extraction", {})

    # Vault path
    vault_path = (
        os.environ.get("OBSIDIAN_VAULT_PATH")
        or vault_section.get("path")
        or str(_platform_default_vault())
    )
    vault_path = Path(os.path.expanduser(vault_path))

    # Claude projects path
    claude_projects_path = (
        os.environ.get("CLAUDE_PROJECTS_PATH")
        or claude_section.get("projects_path")
        or str(Path.home() / ".claude" / "projects")
    )
    claude_projects_path = Path(os.path.expanduser(claude_projects_path))

    # Projects subfolder name
    projects_folder = vault_section.get("projects_folder", "Projects")

    # Extraction settings
    extraction_model = extraction_section.get("model", "haiku")
    max_chars = extraction_section.get("max_conversation_chars", 50000)

    return Config(
        vault_path=vault_path,
        claude_projects_path=claude_projects_path,
        projects_folder=projects_folder,
        extraction_model=extraction_model,
        max_conversation_chars=max_chars,
    )


def init_config() -> Path:
    """Create config.toml interactively. Returns path to created file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        print(f"Config already exists: {CONFIG_FILE}")
        overwrite = input("Overwrite? [y/N] ").strip().lower()
        if overwrite != "y":
            print("Keeping existing config.")
            return CONFIG_FILE

    # Gather values
    default_vault = str(_platform_default_vault())
    vault_path = input(f"Obsidian vault path [{default_vault}]: ").strip() or default_vault

    default_claude = str(Path.home() / ".claude" / "projects")
    claude_path = input(f"Claude projects path [{default_claude}]: ").strip() or default_claude

    content = f'''[vault]
path = "{vault_path}"
projects_folder = "Projects"

[claude]
projects_path = "{claude_path}"

[extraction]
model = "haiku"
max_conversation_chars = 50000
'''

    CONFIG_FILE.write_text(content)
    print(f"Config created: {CONFIG_FILE}")
    return CONFIG_FILE
