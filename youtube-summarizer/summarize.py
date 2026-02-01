#!/usr/bin/env python3
"""
YouTube Summarizer

Downloads a YouTube video, transcribes it with local Whisper,
and generates a summary using Claude.

Usage:
    python summarize.py "https://www.youtube.com/watch?v=..."
    yt-summarize "https://www.youtube.com/watch?v=..."
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add script directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    SUMMARIES_DIR, DOWNLOADS_DIR, OBSIDIAN_OUTPUT,
    OUTPUT_TO_OBSIDIAN, OUTPUT_TO_SUMMARIES
)
from transcribe import transcribe


def get_video_info(url: str) -> dict:
    """Get video metadata using yt-dlp."""
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-download", url],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)


def download_audio(url: str, output_dir: Path) -> Path:
    """Download audio from YouTube video."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Download as m4a (usually fastest, good quality)
    output_template = str(output_dir / "%(id)s.%(ext)s")

    subprocess.run(
        [
            "yt-dlp",
            "-x",  # Extract audio
            "--audio-format", "m4a",
            "--audio-quality", "0",  # Best quality
            "-o", output_template,
            url
        ],
        check=True
    )

    # Find the downloaded file
    for f in output_dir.iterdir():
        if f.suffix in [".m4a", ".mp3", ".wav", ".webm"]:
            return f

    raise RuntimeError("Failed to find downloaded audio file")


def summarize_with_claude(transcript: str, video_info: dict) -> str:
    """Generate summary using Claude CLI."""
    title = video_info.get("title", "Unknown")
    channel = video_info.get("channel", "Unknown")
    duration = video_info.get("duration", 0)
    duration_str = f"{duration // 60}:{duration % 60:02d}"

    prompt = f"""Summarize this YouTube video transcript. Be concise but comprehensive.

Video: {title}
Channel: {channel}
Duration: {duration_str}

Provide:
1. A 2-3 sentence summary
2. Key points (bullet list, 5-10 items)
3. Any action items or recommendations mentioned
4. Notable quotes (if any, max 3)

Transcript:
{transcript[:50000]}  # Limit to ~50k chars for context window

Format your response as markdown."""

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    response = json.loads(result.stdout)
    return response.get("result", result.stdout)


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text[:50].strip('-')


def create_output(video_info: dict, transcript: str, summary: str) -> list[Path]:
    """Write output files."""
    title = video_info.get("title", "Unknown")
    channel = video_info.get("channel", "Unknown")
    video_id = video_info.get("id", "unknown")
    duration = video_info.get("duration", 0)
    duration_str = f"{duration // 60}:{duration % 60:02d}"
    url = video_info.get("webpage_url", "")

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(title)
    filename = f"{date_str}-{slug}.md"

    content = f"""# {title}

| Field | Value |
|-------|-------|
| **Channel** | {channel} |
| **Duration** | {duration_str} |
| **Date** | {date_str} |
| **URL** | {url} |

---

{summary}

---

## Full Transcript

<details>
<summary>Click to expand transcript</summary>

{transcript}

</details>
"""

    outputs = []

    if OUTPUT_TO_SUMMARIES:
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        output_path = SUMMARIES_DIR / filename
        output_path.write_text(content)
        outputs.append(output_path)
        print(f"  ✓ Saved to: {output_path}")

    if OUTPUT_TO_OBSIDIAN:
        OBSIDIAN_OUTPUT.mkdir(parents=True, exist_ok=True)
        obsidian_path = OBSIDIAN_OUTPUT / filename
        obsidian_path.write_text(content)
        outputs.append(obsidian_path)
        print(f"  ✓ Saved to Obsidian: {obsidian_path}")

    return outputs


def main():
    parser = argparse.ArgumentParser(
        description="Download and summarize YouTube videos"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--transcript-only", "-t",
        action="store_true",
        help="Only transcribe, skip summarization"
    )
    parser.add_argument(
        "--keep-audio", "-k",
        action="store_true",
        help="Keep downloaded audio file"
    )

    args = parser.parse_args()

    print(f"Processing: {args.url}\n")

    # Step 1: Get video info
    print("1. Fetching video info...")
    video_info = get_video_info(args.url)
    print(f"   Title: {video_info.get('title')}")
    print(f"   Channel: {video_info.get('channel')}")
    print(f"   Duration: {video_info.get('duration', 0) // 60} minutes\n")

    # Step 2: Download audio
    print("2. Downloading audio...")
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = download_audio(args.url, DOWNLOADS_DIR)
    print(f"   Downloaded: {audio_path.name}\n")

    # Step 3: Transcribe
    print("3. Transcribing with Whisper...")
    transcript = transcribe(audio_path)
    print(f"   Transcribed: {len(transcript)} characters\n")

    # Clean up audio unless --keep-audio
    if not args.keep_audio:
        audio_path.unlink()

    if args.transcript_only:
        print("\n--- Transcript ---\n")
        print(transcript)
        return

    # Step 4: Summarize
    print("4. Generating summary with Claude...")
    summary = summarize_with_claude(transcript, video_info)
    print("   Summary generated\n")

    # Step 5: Save output
    print("5. Saving output...")
    outputs = create_output(video_info, transcript, summary)

    print(f"\nDone! Summary saved to {len(outputs)} location(s)")


if __name__ == "__main__":
    main()
