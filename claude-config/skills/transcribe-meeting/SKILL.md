---
name: transcribe-meeting
version: 1.0
description: Transcribe + diarize a meeting audio file on the jns GPU server, then map speakers to real names (with your confirmation) and write a summary + action items in the standard meeting format. Use when given an audio/video recording of a meeting to turn into notes. Handles the file transfer to the server itself.
---

# /transcribe-meeting

Turn a recorded meeting (audio/video file) into a speaker-labeled transcript plus a
summary with action items. The heavy lifting (transcription + diarization) runs on
the **jns** GPU server; this skill orchestrates that and adds the LLM layer (speaker
naming, summary, actions). The file transfer to the server is handled for you.

## Usage

```
/transcribe-meeting <audio-file>
/transcribe-meeting ~/Downloads/weekly-vitalai.m4a
/transcribe-meeting call.wav --model large-v3      # extra args pass through to the engine
```

Accepts any ffmpeg-readable audio/video (`.m4a`, `.mp3`, `.wav`, `.mp4`, …).

## Behavior

Execute these steps in order. Do not skip the speaker-confirmation step (3).

### 1. Transcribe + diarize on the GPU server
Run the client wrapper (it scp's the file to jns, runs whisper.cpp on the AMD GPU +
pyannote diarization on CPU, and writes the results next to the input):

```bash
~/agents/bin/earshot "<audio-file>" [passthrough args]
```

It prints progress (`[1/3]…[3/3]`) and, on success, the path to
`<name>.transcript.md`. It also writes `<name>.transcript.json` (turns + timestamps)
in the same directory. If it reports it cannot reach `jns`/`jns-server`, stop and tell
the user (the engine only runs on the server).

### 2. Read the outputs
Read `<name>.transcript.md` (speaker-labeled with generic `SPEAKER_00/01/02`) and, if
useful, `<name>.transcript.json` for turn timestamps and the speaker count.

### 3. Map speakers to real names — PROPOSE, then CONFIRM
The diarizer uses generic labels. **Never guess silently** — first-speaker order is
unreliable (it caused a real Jason/Ryan mix-up before). Instead:
- Infer each speaker's identity from the content: names they're addressed by, roles,
  self-references, who owns which topic.
- Present a proposed mapping as a short table — `SPEAKER_00 → <name>` with the **quote
  or evidence** that supports each guess.
- Ask the user to confirm or correct the mapping (use AskUserQuestion or a direct
  question) **before** relabeling.
- If the user already supplied names (e.g. they said "it's Jason, Ryan, John"), still
  show the mapping you'll apply and let them correct it.

Once confirmed, replace the `SPEAKER_xx` labels with the real names throughout.

### 4. Summarize + extract action items
Using the now name-labeled transcript, write notes in the **standard meeting format**:
- `# <Meeting title> — <date>` and an **Attendees** line.
- **Summary** organized by topic (decisions, status, discussion).
- **Action Items** as a table: `# | Action | Owner | Notes / Context`.
- **Full Transcript** appended verbatim at the bottom (the name-labeled version), under
  a heading, noting it's machine-transcribed.

Save this as `<name>.summary.md` next to the audio file.

### 5. Report (save only — do not email)
Tell the user the two files written:
- `<name>.transcript.md` — speaker-labeled transcript
- `<name>.summary.md` — summary + action items

Do not send anything anywhere; this skill is save-only. (If the user later wants it
emailed, that's `~/agents/google/send_mail.py`.)

## Notes
- The engine lives at `~/projects/earshot` on jns; this skill never
  re-implements transcription — it calls the `earshot` CLI.
- Speakers map by *first appearance* if names are passed straight to the engine via
  `--speakers`, which is why this skill does the mapping in the LLM layer instead.
- Honor any meeting-specific naming/handling rules from the user's CLAUDE.md memory.
