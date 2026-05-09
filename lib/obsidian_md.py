"""Obsidian markdown frontmatter read/write — atomic and body-preserving.

Tool-agnostic. Used by project/cli.py and decision/cli.py to mutate the
manually-edited frontmatter of project notes and decision records without
disturbing the body content.

File format::

    ---
    key: value
    ...
    ---

    # body markdown here
    ...

A file with no leading ``---`` is treated as body-only with empty
frontmatter (callers can decide whether that's an error). The body is
everything after the closing ``---``, preserved byte-for-byte except for
a single leading newline.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import yaml


class ObsidianMdError(Exception):
    """Raised when a file isn't valid frontmatter+body."""


# ---------- parse / dump ----------

def parse(text: str) -> tuple[dict, str]:
    """Parse text into ``(frontmatter_dict, body_str)``.

    The closing fence ``\\n---`` may be followed by a newline (standard
    case) or end-of-file. A single optional blank separator line between
    the closing fence and the body is treated as decoration and stripped.
    """
    if not text.startswith("---\n"):
        return ({}, text)
    end_idx = text.find("\n---\n", 4)
    if end_idx != -1:
        body_start = end_idx + 5  # past `\n---\n`
    elif text.endswith("\n---"):
        end_idx = len(text) - 4
        body_start = len(text)
    else:
        raise ObsidianMdError("frontmatter not terminated by closing `---`")

    fm_text = text[4:end_idx]
    body = text[body_start:]
    # Strip one optional blank separator line between fence and body.
    if body.startswith("\n"):
        body = body[1:]

    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        raise ObsidianMdError(
            f"frontmatter must be a mapping, got {type(fm).__name__}"
        )
    return (fm, body)


def dump(
    frontmatter: dict,
    body: str,
    field_order: list[str] | None = None,
) -> str:
    """Render ``(frontmatter, body)`` back to markdown text.

    ``field_order`` controls frontmatter key ordering: listed keys appear
    first in that order, then any remaining keys in their original order.
    """
    if field_order:
        ordered: dict = {}
        for k in field_order:
            if k in frontmatter:
                ordered[k] = frontmatter[k]
        for k, v in frontmatter.items():
            if k not in ordered:
                ordered[k] = v
    else:
        ordered = dict(frontmatter)
    fm_text = yaml.safe_dump(
        ordered,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=80,
    ).rstrip()
    body = body.lstrip("\n")
    if body and not body.endswith("\n"):
        body = body + "\n"
    if body:
        return f"---\n{fm_text}\n---\n\n{body}"
    return f"---\n{fm_text}\n---\n"


# ---------- file I/O ----------

def load(path: Path) -> tuple[dict, str]:
    """Read ``path`` and return ``(frontmatter_dict, body_str)``."""
    if not path.exists():
        raise ObsidianMdError(f"file not found: {path}")
    return parse(path.read_text(encoding="utf-8"))


def write_atomic(path: Path, text: str) -> None:
    """Atomic write via tmp file + ``os.replace`` in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def write(
    path: Path,
    frontmatter: dict,
    body: str,
    field_order: list[str] | None = None,
) -> None:
    """Atomic write of ``(frontmatter, body)`` to ``path``."""
    write_atomic(path, dump(frontmatter, body, field_order))


# ---------- body section helpers ----------

def _section_pattern(section: str) -> re.Pattern:
    return re.compile(
        rf"(^## {re.escape(section)}\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )


def get_section(body: str, section: str) -> str:
    """Return the content of ``## section`` (without the heading line)."""
    m = _section_pattern(section).search(body)
    if not m:
        raise ObsidianMdError(f"section '## {section}' not found in body")
    return m.group(2).rstrip()


def replace_section(body: str, section: str, content: str) -> str:
    """Replace content of ``## section`` heading with ``content``.

    Content extends until the next ``## `` heading or end of body. The
    new content is normalized to end with one blank line before the next
    section (or end of file). Raises if the section isn't present.
    """
    pattern = _section_pattern(section)
    if not pattern.search(body):
        raise ObsidianMdError(f"section '## {section}' not found in body")
    new = content.rstrip() + "\n\n"
    return pattern.sub(lambda m: m.group(1) + new, body)


def has_section(body: str, section: str) -> bool:
    """Return True if ``## section`` exists in body."""
    return bool(_section_pattern(section).search(body))
