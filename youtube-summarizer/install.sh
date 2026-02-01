#!/bin/bash
# Install youtube-summarizer dependencies
#
# Detects platform and installs appropriate Whisper backend:
# - macOS Apple Silicon: mlx-whisper
# - macOS Intel: whisper.cpp
# - Linux: whisper.cpp or faster-whisper

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
WHISPER_MODEL="${WHISPER_MODEL:-small}"

echo "YouTube Summarizer - Installation"
echo "================================="
echo ""

# Detect platform
OS=$(uname -s)
ARCH=$(uname -m)

echo "Detected: $OS $ARCH"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip
echo "  ✓ Virtual environment created at $VENV_DIR"
echo ""

# Install common dependencies
echo "Installing common dependencies..."

if [[ "$OS" == "Darwin" ]]; then
    # macOS
    if ! command -v brew &> /dev/null; then
        echo "Error: Homebrew required. Install from https://brew.sh"
        exit 1
    fi

    # Install yt-dlp and ffmpeg via brew
    brew list yt-dlp &>/dev/null || brew install yt-dlp
    brew list ffmpeg &>/dev/null || brew install ffmpeg
    echo "  ✓ yt-dlp and ffmpeg installed"

    if [[ "$ARCH" == "arm64" ]]; then
        # Apple Silicon - use mlx-whisper
        echo ""
        echo "Installing mlx-whisper (Apple Silicon optimized)..."
        pip install --quiet mlx-whisper
        echo "  ✓ mlx-whisper installed"
        echo ""
        echo "Model will download on first use ($WHISPER_MODEL)"
    else
        # Intel Mac - use whisper.cpp
        echo ""
        echo "Installing whisper.cpp..."
        brew list whisper-cpp &>/dev/null || brew install whisper-cpp
        echo "  ✓ whisper.cpp installed"
        echo ""
        echo "Downloading Whisper model ($WHISPER_MODEL)..."
        if command -v whisper-cpp-download-model &> /dev/null; then
            whisper-cpp-download-model $WHISPER_MODEL
        else
            # Manual download
            MODEL_DIR="$HOME/.local/share/whisper-cpp"
            mkdir -p "$MODEL_DIR"
            if [[ ! -f "$MODEL_DIR/ggml-${WHISPER_MODEL}.bin" ]]; then
                curl -L "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${WHISPER_MODEL}.bin" \
                    -o "$MODEL_DIR/ggml-${WHISPER_MODEL}.bin"
            fi
        fi
        echo "  ✓ Model downloaded"
    fi

elif [[ "$OS" == "Linux" ]]; then
    # Linux
    echo "Installing dependencies for Linux..."

    # Try apt (Debian/Ubuntu)
    if command -v apt &> /dev/null; then
        sudo apt update
        sudo apt install -y ffmpeg
    # Try dnf (Fedora)
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y ffmpeg
    else
        echo "Warning: Unknown package manager. Please install ffmpeg manually."
    fi

    # Install yt-dlp via pip in venv
    pip install --quiet yt-dlp
    echo "  ✓ yt-dlp and ffmpeg installed"

    # Install faster-whisper (works well on Linux)
    echo ""
    echo "Installing faster-whisper..."
    pip install --quiet faster-whisper
    echo "  ✓ faster-whisper installed"
    echo ""
    echo "Model will download on first use ($WHISPER_MODEL)"

else
    echo "Error: Unsupported OS: $OS"
    exit 1
fi

deactivate

# Create shell alias
echo ""
echo "Setting up shell alias..."

ALIAS_LINE='alias yt-summarize="~/agents/youtube-summarizer/.venv/bin/python ~/agents/youtube-summarizer/summarize.py"'

# Add to .zshrc if it exists, otherwise .bashrc
if [[ -f "$HOME/.zshrc" ]]; then
    if ! grep -q "yt-summarize" "$HOME/.zshrc"; then
        echo "" >> "$HOME/.zshrc"
        echo "# YouTube Summarizer" >> "$HOME/.zshrc"
        echo "$ALIAS_LINE" >> "$HOME/.zshrc"
        echo "  ✓ Added alias to ~/.zshrc"
    else
        echo "  - Alias already exists in ~/.zshrc"
    fi
fi

if [[ -f "$HOME/.bashrc" ]]; then
    if ! grep -q "yt-summarize" "$HOME/.bashrc"; then
        echo "" >> "$HOME/.bashrc"
        echo "# YouTube Summarizer" >> "$HOME/.bashrc"
        echo "$ALIAS_LINE" >> "$HOME/.bashrc"
        echo "  ✓ Added alias to ~/.bashrc"
    else
        echo "  - Alias already exists in ~/.bashrc"
    fi
fi

# Create output directories
mkdir -p "$HOME/summaries"
echo "  ✓ Created ~/summaries/"

# Make main script executable
chmod +x "$SCRIPT_DIR/summarize.py"

echo ""
echo "================================="
echo "Installation complete!"
echo ""
echo "Usage:"
echo "  yt-summarize \"https://www.youtube.com/watch?v=...\""
echo ""
echo "Or directly:"
echo "  ~/agents/youtube-summarizer/.venv/bin/python ~/agents/youtube-summarizer/summarize.py \"URL\""
echo ""
echo "Options:"
echo "  --transcript-only, -t    Only transcribe, skip summary"
echo "  --keep-audio, -k         Keep downloaded audio file"
echo ""
echo "Reload your shell or run: source ~/.zshrc"
