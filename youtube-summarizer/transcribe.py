"""Whisper transcription abstraction layer."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from config import get_whisper_backend, WHISPER_MODEL, WHISPER_LANGUAGE


def transcribe(audio_path: Path) -> str:
    """Transcribe audio file using available Whisper backend."""
    backend = get_whisper_backend()

    if backend is None:
        raise RuntimeError(
            "No Whisper backend found. Run install.sh to install dependencies."
        )

    print(f"Transcribing with {backend} backend...")

    if backend == "mlx":
        return _transcribe_mlx(audio_path)
    elif backend == "cpp":
        return _transcribe_cpp(audio_path)
    elif backend == "faster":
        return _transcribe_faster(audio_path)
    else:
        raise RuntimeError(f"Unknown backend: {backend}")


def _transcribe_mlx(audio_path: Path) -> str:
    """Transcribe using mlx-whisper (Apple Silicon)."""
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=f"mlx-community/whisper-{WHISPER_MODEL}-mlx",
        language=WHISPER_LANGUAGE,
    )
    return result["text"]


def _transcribe_cpp(audio_path: Path) -> str:
    """Transcribe using whisper.cpp."""
    # whisper.cpp needs 16kHz WAV, convert if needed
    wav_path = audio_path.with_suffix(".wav")

    if audio_path.suffix != ".wav":
        print("Converting to WAV format...")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                str(wav_path)
            ],
            capture_output=True,
            check=True
        )
    else:
        wav_path = audio_path

    # Find model path
    model_paths = [
        Path.home() / ".local/share/whisper-cpp" / f"ggml-{WHISPER_MODEL}.bin",
        Path.home() / "whisper.cpp/models" / f"ggml-{WHISPER_MODEL}.bin",
        Path("/usr/local/share/whisper-cpp") / f"ggml-{WHISPER_MODEL}.bin",
        Path("/opt/homebrew/share/whisper-cpp") / f"ggml-{WHISPER_MODEL}.bin",
    ]

    model_path = None
    for p in model_paths:
        if p.exists():
            model_path = p
            break

    if model_path is None:
        raise RuntimeError(
            f"Whisper model not found. Run: whisper-cpp-download-model {WHISPER_MODEL}"
        )

    # Run whisper.cpp
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        output_path = f.name

    cmd = ["whisper-cpp", "-m", str(model_path), "-f", str(wav_path), "-otxt"]
    if WHISPER_LANGUAGE:
        cmd.extend(["-l", WHISPER_LANGUAGE])

    result = subprocess.run(cmd, capture_output=True, text=True)

    # whisper.cpp outputs to {input}.txt
    txt_path = wav_path.with_suffix(".wav.txt")
    if txt_path.exists():
        text = txt_path.read_text()
        txt_path.unlink()  # Clean up
    else:
        # Try stdout
        text = result.stdout

    # Clean up temp wav if we created it
    if wav_path != audio_path and wav_path.exists():
        wav_path.unlink()

    return text.strip()


def _transcribe_faster(audio_path: Path) -> str:
    """Transcribe using faster-whisper."""
    from faster_whisper import WhisperModel

    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        beam_size=5
    )

    return " ".join(segment.text for segment in segments)
