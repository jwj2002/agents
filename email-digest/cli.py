#!/usr/bin/env python3
"""email-digest — preset-driven email reports built from pulse digests.

Renders a markdown digest using ``pulse digest --vault VAULT``, validates
that every project in the rendering belongs to the preset's client (spec
§6.5 #1), and walks the user through an interactive Y/E/S/N confirmation
before sending via Microsoft Graph (``~/agents/m365/send_mail.py``).

Subcommands:

- ``email-digest preset list``
- ``email-digest preset <name> [--window W]``
- ``email-digest send <draft-file>``    — resume a saved draft
- ``email-digest sent --since DATE``   — list recently sent digests

Config: ``~/.claude/digest-config.yaml`` (per-machine, not synced). A
``digest-config.yaml.example`` ships in this repo for reference.

Cross-vault digests are NOT supported via presets — every preset targets
exactly one vault. To produce a cross-vault view, run
``pulse digest --all-vaults`` directly (which is jns-mac-only per spec
§6.5 #2) and pipe to ``m365/send_mail.py`` manually.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import obsidian_md  # noqa: E402
from lib import project_resolver as pr  # noqa: E402
from pulse import cli as pulse_cli  # noqa: E402

HOME = Path.home()
CONFIG_PATH = HOME / ".claude" / "digest-config.yaml"
DRAFTS_DIR = HOME / ".claude" / "digests" / "draft"
SENT_DIR = HOME / ".claude" / "digests" / "sent"
SEND_MAIL_SCRIPT = HOME / "agents" / "m365" / "send_mail.py"

REQUIRED_PRESET_FIELDS = ("vault", "client", "recipient", "subject_template")
ALLOWED_WINDOWS = ("daily", "weekly", "monthly", "full")


class DigestError(Exception):
    """User-facing error → stderr + exit 1."""


# ---------- config loading ----------

def load_config(path: Path | None = None) -> dict:
    """Parse the digest config; validate every preset shape."""
    path = path or CONFIG_PATH
    if not path.is_file():
        raise DigestError(
            f"config not found: {path}\n"
            f"  Hint: cp ~/agents/email-digest/digest-config.yaml.example {path}"
        )
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise DigestError(f"malformed YAML in {path}: {e}") from e
    if not isinstance(data, dict):
        raise DigestError(f"{path}: expected mapping at top level")
    presets = data.get("presets") or {}
    if not isinstance(presets, dict):
        raise DigestError(f"{path}: `presets:` must be a mapping")
    for name, preset in presets.items():
        if not isinstance(preset, dict):
            raise DigestError(f"preset {name!r}: must be a mapping")
        missing = [f for f in REQUIRED_PRESET_FIELDS if f not in preset]
        if missing:
            raise DigestError(
                f"preset {name!r}: missing required fields: {', '.join(missing)}"
            )
    return data


def list_presets(config: dict) -> str:
    """Render a human table of configured presets."""
    presets = config.get("presets") or {}
    if not presets:
        return "no presets configured.\n"
    lines = [f"{'name':<24} {'vault':<22} {'client':<12} {'recipient':<32} description"]
    lines.append("─" * 110)
    for name in sorted(presets):
        p = presets[name]
        desc = p.get("description") or ""
        lines.append(
            f"{name:<24} {p.get('vault', '?'):<22} {p.get('client', '?'):<12} "
            f"{p.get('recipient', '?'):<32} {desc}"
        )
    return "\n".join(lines) + "\n"


# ---------- digest rendering ----------

def render_preset_digest(
    preset: dict,
    *,
    vaults_base: Path | None = None,
    window: str | None = None,
) -> str:
    """Render markdown digest body for a preset.

    Calls ``pulse.cli.render_vault_digest`` for the preset's vault. The
    rendered digest is the full vault — ``pulse digest`` v1 does not
    support project-level filtering, so a preset with ``project`` set to
    anything other than ``"*"`` is **refused** rather than silently
    including sibling projects (Codex adversarial review, 2026-05-13:
    project-level confidentiality leakage within a single-client vault
    when the confirmation line presents a narrower scope than the payload).

    ``owner_filter`` is informational only; pulse v1 doesn't filter by
    owner. The annotation lands in the digest header so the recipient can
    see the intended scope.
    """
    vault = preset["vault"]
    w = window or preset.get("default_window") or "daily"
    if w not in ALLOWED_WINDOWS:
        raise DigestError(f"invalid window {w!r}; allowed: {', '.join(ALLOWED_WINDOWS)}")

    proj = preset.get("project") or "*"
    if proj != "*":
        raise DigestError(
            f"preset {proj!r} project-level filtering is not yet enforced — "
            f"`pulse digest` v1 renders the whole vault.\n"
            f"  Refusing rather than silently emailing sibling projects in vault "
            f"{vault!r}.\n"
            f"  Workaround: set `project: \"*\"` in this preset to send the full "
            f"vault digest, or wait for `pulse digest --project NAME` filtering."
        )

    body = pulse_cli.render_vault_digest(vault, vaults_base=vaults_base, window=w)

    owner = preset.get("owner_filter") or ""
    if owner:
        body = body.replace(
            f"# {vault} —",
            f"# {vault} (owner filter: {owner}) —",
            1,
        )
    return body


# ---------- §6.5 #1 vault validation ----------

def projects_in_digest(body: str) -> list[str]:
    """Extract project names from `## <project> —` headings in a digest body."""
    out = []
    for line in body.splitlines():
        if line.startswith("## "):
            rest = line[3:].strip()
            # Format: "<project> — <status>" or just "<project>"
            name = rest.split("—", 1)[0].strip()
            if name and name not in out:
                out.append(name)
    return out


def validate_vault_consistency(
    preset: dict,
    digest_body: str,
    *,
    vaults_base: Path | None = None,
) -> None:
    """§6.5 #1: every project mentioned must have ``client:`` matching preset.

    Raises ``DigestError`` (treated as send-refused) with an explicit pointer
    when any mismatch is found.
    """
    vault = preset["vault"]
    expected_client = preset["client"]
    base = vaults_base if vaults_base is not None else pr.VAULTS_BASE
    mismatches: list[tuple[str, str]] = []
    for project in projects_in_digest(digest_body):
        note_path = base / vault / "Projects" / f"{project}.md"
        if not note_path.is_file():
            continue  # project note absent — pulse digest already showed a placeholder
        try:
            fm, _ = obsidian_md.load(note_path)
        except obsidian_md.ObsidianMdError:
            continue  # treat as opaque; audit catches this separately
        actual = fm.get("client")
        if actual != expected_client:
            mismatches.append((project, actual or "(unset)"))
    if mismatches:
        details = "\n".join(f'    - "{p}" has client={c}' for p, c in mismatches)
        raise DigestError(
            f"digest scope mismatch — refusing to send.\n"
            f"  preset expects client = {expected_client!r}\n"
            f"  but the rendered digest includes:\n"
            f"{details}\n"
            f"\n"
            f"Likely causes:\n"
            f"  (a) a project's client: frontmatter is set incorrectly\n"
            f"  (b) the preset's `client:` doesn't match the projects in this vault\n"
            f"\n"
            f"Run `pulse audit --vault-clients ~/.claude/vault-clients.yaml` to investigate."
        )


# ---------- §6.5 #3 confirmation line ----------

def confirmation_line(preset: dict) -> str:
    """One-line context shown immediately before the Y/E/S/N prompt."""
    parts = [f"vault: {preset['vault']}"]
    proj = preset.get("project") or "*"
    parts.append(f"project: {proj}")
    if preset.get("owner_filter"):
        parts.append(f"owner-filter: {preset['owner_filter']}")
    return f"Sending to {preset['recipient']} (" + ", ".join(parts) + "). Confirm?"


# ---------- subject + draft management ----------

def format_subject(preset: dict, today_iso: str) -> str:
    template = preset.get("subject_template") or ""
    return template.format(date=today_iso, vault=preset["vault"])


def write_draft(
    preset_name: str, body: str, *,
    drafts_dir: Path | None = None, today_iso: str | None = None,
) -> Path:
    d = drafts_dir or DRAFTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    today = today_iso or dt.date.today().isoformat()
    path = d / f"{preset_name}-{today}.md"
    path.write_text(body)
    return path


def archive_sent(
    preset_name: str, body: str, *,
    sent_dir: Path | None = None, today_iso: str | None = None,
) -> Path:
    d = sent_dir or SENT_DIR
    d.mkdir(parents=True, exist_ok=True)
    today = today_iso or dt.date.today().isoformat()
    path = d / f"{preset_name}-{today}.md"
    path.write_text(body)
    return path


# ---------- editor ----------

def open_in_editor(path: Path, *, editor: str | None = None) -> None:
    """Open ``path`` in $EDITOR (or `editor` override). Blocks until editor exits."""
    cmd_str = editor or os.environ.get("EDITOR") or "vi"
    # Use shell=True semantics: split safely via shlex but allow simple editors
    import shlex
    cmd = shlex.split(cmd_str) + [str(path)]
    subprocess.run(cmd, check=False)


# ---------- send ----------

def send_via_graph(
    recipient: str, subject: str, body_md: str,
    *,
    send_mail_script: Path | None = None,
    runner=subprocess.run,
) -> tuple[int, str, str]:
    """Shell out to ``m365/send_mail.py``. Returns (rc, stdout, stderr)."""
    script = send_mail_script or SEND_MAIL_SCRIPT
    with tempfile.NamedTemporaryFile(
        "w", delete=False, suffix=".md", prefix="email-digest-",
    ) as tmp:
        tmp.write(body_md)
        body_path = Path(tmp.name)
    try:
        result = runner(
            [
                "python3", str(script),
                "--to", recipient,
                "--subject", subject,
                "--body-file", str(body_path),
                "--content-type", "Markdown",
            ],
            capture_output=True, text=True, check=False,
        )
        return (result.returncode, result.stdout, result.stderr)
    finally:
        if body_path.exists():
            body_path.unlink()


# ---------- interactive flow ----------

def prompt_choice(message: str, *, input_fn=input) -> str:
    """Loop until user gives one of y/e/s/n. Returns lowercase single char."""
    while True:
        try:
            raw = input_fn(message).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "n"
        if raw in ("y", "e", "s", "n"):
            return raw
        print("  please enter one of: y / e / s / n")


def interactive_flow(
    preset_name: str, preset: dict, body: str,
    *,
    drafts_dir: Path | None = None,
    sent_dir: Path | None = None,
    send_mail_script: Path | None = None,
    editor: str | None = None,
    input_fn=input,
    runner=subprocess.run,
    today_iso: str | None = None,
    auto_choice: str | None = None,
) -> tuple[str, Path | None]:
    """Walk the Y/E/S/N loop. Returns ``(outcome, path)``.

    Outcomes:
    - ``"sent"`` — Graph send succeeded; ``path`` is the sent-archive file
    - ``"saved"`` — draft persisted; ``path`` is the draft file
    - ``"cancelled"`` — draft removed (if any); ``path`` is None
    - ``"send-failed"`` — Graph returned non-zero; ``path`` is the draft

    ``auto_choice`` short-circuits the prompt for testing.
    """
    today = today_iso or dt.date.today().isoformat()
    draft = write_draft(preset_name, body, drafts_dir=drafts_dir, today_iso=today)

    print()
    print("──" * 30)
    sys.stdout.write(body)
    print("──" * 30)
    print()
    print(confirmation_line(preset))
    print("  [y] yes, send now")
    print("  [e] edit in $EDITOR before sending")
    print("  [s] save draft and exit (review later)")
    print("  [n] cancel")
    print()

    while True:
        if auto_choice is not None:
            choice = auto_choice
            auto_choice = None
        else:
            choice = prompt_choice("Choice [y/e/s/n]: ", input_fn=input_fn)

        if choice == "y":
            subject = format_subject(preset, today)
            rc, _out, err = send_via_graph(
                preset["recipient"], subject, draft.read_text(),
                send_mail_script=send_mail_script, runner=runner,
            )
            if rc == 0:
                archived = archive_sent(
                    preset_name, draft.read_text(),
                    sent_dir=sent_dir, today_iso=today,
                )
                draft.unlink(missing_ok=True)
                return ("sent", archived)
            print(f"send failed (rc={rc}): {err.strip()}", file=sys.stderr)
            print("draft preserved for later retry.", file=sys.stderr)
            return ("send-failed", draft)

        if choice == "e":
            open_in_editor(draft, editor=editor)
            # Re-display after edit, re-prompt
            print()
            sys.stdout.write(draft.read_text())
            print()
            print(confirmation_line(preset))
            continue

        if choice == "s":
            return ("saved", draft)

        if choice == "n":
            draft.unlink(missing_ok=True)
            return ("cancelled", None)


# ---------- list sent ----------

def list_sent(since: str | None = None, *, sent_dir: Path | None = None) -> list[Path]:
    d = sent_dir or SENT_DIR
    if not d.is_dir():
        return []
    cutoff = since
    out = []
    for p in sorted(d.glob("*.md")):
        if cutoff is None or p.stem.split("-", 1)[-1] >= cutoff:
            out.append(p)
    return out


# ---------- argparse + main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="email-digest",
        description="Preset-driven email reports built from pulse digests.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    preset = sub.add_parser("preset", help="Render and send a preset digest")
    preset_sub = preset.add_subparsers(dest="preset_cmd", required=True)

    plist = preset_sub.add_parser("list", help="List all presets")
    plist.add_argument("--config", default=None)

    prun = preset_sub.add_parser("run", help="Render + interactive send")
    prun.add_argument("name", help="Preset name")
    prun.add_argument("--window", default=None,
                      choices=list(ALLOWED_WINDOWS),
                      help="Override the preset's default_window")
    prun.add_argument("--config", default=None)
    prun.add_argument("--vaults-base", default=None)

    send = sub.add_parser("send", help="Send a saved draft")
    send.add_argument("draft", help="Path to a draft .md file")
    send.add_argument("--config", default=None)
    send.add_argument("--preset", default=None,
                      help="Preset name (default: inferred from draft filename)")

    sent = sub.add_parser("sent", help="List recently sent digests")
    sent.add_argument("--since", default=None,
                      help="ISO date (YYYY-MM-DD); only show digests sent on or after")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        args = parse_args(argv)

        if args.cmd == "preset" and args.preset_cmd == "list":
            cfg = load_config(Path(args.config) if args.config else None)
            sys.stdout.write(list_presets(cfg))
            return 0

        if args.cmd == "preset" and args.preset_cmd == "run":
            cfg = load_config(Path(args.config) if args.config else None)
            presets = cfg.get("presets") or {}
            if args.name not in presets:
                raise DigestError(
                    f"unknown preset {args.name!r}. "
                    f"Run `email-digest preset list` to see configured presets."
                )
            preset = presets[args.name]
            vaults_base = Path(args.vaults_base) if args.vaults_base else None
            body = render_preset_digest(preset, vaults_base=vaults_base, window=args.window)
            validate_vault_consistency(preset, body, vaults_base=vaults_base)
            outcome, path = interactive_flow(args.name, preset, body)
            print(f"\noutcome: {outcome}{(' — ' + str(path)) if path else ''}")
            return 0 if outcome in ("sent", "saved", "cancelled") else 1

        if args.cmd == "send":
            cfg = load_config(Path(args.config) if args.config else None)
            draft = Path(args.draft)
            if not draft.is_file():
                raise DigestError(f"draft not found: {draft}")
            preset_name = args.preset or draft.stem.rsplit("-", 3)[0]
            presets = cfg.get("presets") or {}
            if preset_name not in presets:
                raise DigestError(
                    f"could not infer preset from {draft.name}; "
                    f"pass --preset NAME."
                )
            preset = presets[preset_name]
            body = draft.read_text()
            validate_vault_consistency(preset, body)
            subject = format_subject(preset, dt.date.today().isoformat())
            rc, _out, err = send_via_graph(preset["recipient"], subject, body)
            if rc != 0:
                print(f"send failed (rc={rc}): {err.strip()}", file=sys.stderr)
                return 1
            archive_sent(preset_name, body)
            draft.unlink(missing_ok=True)
            print(f"sent: {preset['recipient']}")
            return 0

        if args.cmd == "sent":
            paths = list_sent(args.since)
            for p in paths:
                print(p)
            return 0

        raise DigestError(f"unknown subcommand: {args.cmd}")

    except DigestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
