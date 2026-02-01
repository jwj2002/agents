"""Configuration for youtube-summarizer."""
from pathlib import Path
import platform
import subprocess

# Output directories
SUMMARIES_DIR = Path.home() / "summaries"
DOWNLOADS_DIR = Path.home() / "summaries" / ".downloads"
OBSIDIAN_VAULT = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/MyVault"
OBSIDIAN_OUTPUT = OBSIDIAN_VAULT / "Media" / "YouTube"

# Whisper settings
WHISPER_MODEL = "small"  # tiny, base, small, medium, large
WHISPER_LANGUAGE = "en"  # None for auto-detect

# Output settings
OUTPUT_TO_OBSIDIAN = True
OUTPUT_TO_SUMMARIES = True

def get_platform():
    """Detect platform and architecture."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        if machine == "arm64":
            return "macos-arm64"
        return "macos-intel"
    elif system == "linux":
        return "linux"
    return "unknown"

def get_whisper_backend():
    """Determine which whisper backend to use."""
    plat = get_platform()

    # Check if mlx-whisper is available (preferred for Apple Silicon)
    if plat == "macos-arm64":
        try:
            import mlx_whisper
            return "mlx"
        except ImportError:
            pass

    # Check for whisper.cpp
    result = subprocess.run(["which", "whisper-cpp"], capture_output=True)
    if result.returncode == 0:
        return "cpp"

    # Fallback to faster-whisper
    try:
        import faster_whisper
        return "faster"
    except ImportError:
        pass

    return None
