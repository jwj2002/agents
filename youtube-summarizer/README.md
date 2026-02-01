# YouTube Summarizer

Download YouTube videos, transcribe with local Whisper, and summarize with Claude.

## Features

- **Local transcription** - No API costs, private
- **Platform optimized** - Uses best Whisper backend for your system
- **Claude summarization** - Key points, action items, quotes
- **Obsidian integration** - Saves to your vault

## Installation

```bash
~/agents/youtube-summarizer/install.sh
```

This installs:
- `yt-dlp` - YouTube downloader
- `ffmpeg` - Audio processing
- Whisper backend (platform-specific)
- Shell alias `yt-summarize`

### Whisper Backends

| Platform | Backend | Notes |
|----------|---------|-------|
| macOS Apple Silicon | mlx-whisper | Fastest, uses Metal GPU |
| macOS Intel | whisper.cpp | CPU-based |
| Linux | faster-whisper | CPU/CUDA |

## Usage

```bash
# Basic usage
yt-summarize "https://www.youtube.com/watch?v=abc123"

# Transcript only (no summary)
yt-summarize -t "https://www.youtube.com/watch?v=abc123"

# Keep audio file
yt-summarize -k "https://www.youtube.com/watch?v=abc123"
```

## Output

Summaries are saved to:
- `~/summaries/` - Standalone folder
- `~/Library/.../MyVault/Media/YouTube/` - Obsidian vault

### Output Format

```markdown
# Video Title

| Field | Value |
|-------|-------|
| **Channel** | Channel Name |
| **Duration** | 18:32 |
| **URL** | https://... |

---

## Summary
2-3 sentence overview...

## Key Points
- Point 1
- Point 2
...

## Action Items
- [ ] Item 1
- [ ] Item 2

## Notable Quotes
> "Quote here"

---

## Full Transcript
<details>
<summary>Click to expand</summary>
...
</details>
```

## Configuration

Edit `config.py` to customize:

```python
WHISPER_MODEL = "small"      # tiny, base, small, medium, large
WHISPER_LANGUAGE = "en"      # None for auto-detect
OUTPUT_TO_OBSIDIAN = True    # Save to Obsidian vault
OUTPUT_TO_SUMMARIES = True   # Save to ~/summaries/
```

### Model Sizes

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| tiny | 75 MB | Fastest | Good for clear audio |
| base | 142 MB | Fast | Better accuracy |
| small | 466 MB | Medium | Recommended |
| medium | 1.5 GB | Slow | High accuracy |
| large | 3 GB | Slowest | Best accuracy |

## How It Works

```
YouTube URL
    ↓
[yt-dlp] Download audio
    ↓
[Whisper] Transcribe locally
    ↓
[Claude CLI] Generate summary
    ↓
Save to ~/summaries/ + Obsidian
```

## Troubleshooting

### "No Whisper backend found"
Run `install.sh` again or manually install:
```bash
# macOS Apple Silicon
pip3 install mlx-whisper

# macOS Intel / Linux
brew install whisper-cpp  # or pip3 install faster-whisper
```

### Slow transcription
- Use a smaller model: edit `WHISPER_MODEL = "tiny"` in config.py
- For Apple Silicon, ensure mlx-whisper is installed (uses GPU)

### Claude CLI errors
Ensure Claude CLI is installed and authenticated:
```bash
claude --version
claude -p "test"
```
