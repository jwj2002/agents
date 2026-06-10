"""Tests for the `bin/memory` CLI frontmatter parser (#430).

Focus: the CLI's `_split_frontmatter` must strip surrounding quotes from values
exactly like the SessionStart hook's `_fact_meta`, so a valid-YAML quoted form
such as `durability: "durable"` is honored as durable by the same code path
`memory doctor` / `memory archive` use (and is therefore NOT flagged stale).
"""

import datetime
import importlib.machinery
import importlib.util
import sys
import time
from pathlib import Path

# `bin/memory` is extensionless; load it as a module via its file path.
_MEMORY_PATH = Path(__file__).resolve().parents[2] / "bin" / "memory"
_spec = importlib.util.spec_from_loader(
    "memory_cli",
    importlib.machinery.SourceFileLoader("memory_cli", str(_MEMORY_PATH)),
)
memory_cli = importlib.util.module_from_spec(_spec)
sys.modules["memory_cli"] = memory_cli
_spec.loader.exec_module(memory_cli)


def test_split_frontmatter_strips_quotes_from_durability():
    """`durability: "durable"` parses to the unquoted literal `durable`."""
    text = '---\nname: f\ntype: project\ndurability: "durable"\n---\n\nbody'
    meta, _body = memory_cli._split_frontmatter(text)
    assert meta["durability"] == "durable"


def test_split_frontmatter_strips_single_quotes():
    text = "---\nname: f\ntype: project\nsummary: 'a quoted summary'\n---\n\nbody"
    meta, _body = memory_cli._split_frontmatter(text)
    assert meta["summary"] == "a quoted summary"


def test_quoted_durable_not_flagged_stale_via_doctor_path(tmp_path):
    """A perishable-named, old, `type: project` fact with `durability: "durable"`
    (quoted) must be honored as durable by the SAME helper `memory doctor` /
    `memory archive` use — i.e. it is NOT a TTL candidate. Before #430 the CLI
    saw the literal `"durable"` (with quotes) and still flagged it stale."""
    mem = tmp_path / "-Users-x-proj" / "memory"
    mem.mkdir(parents=True)
    # Perishable filename ('summary') + old mtime would normally trip the
    # stale-perishable heuristic; quoted durable must override it.
    fact = mem / "session-summary.md"
    fact.write_text(
        '---\nname: session-summary\ntype: project\ndurability: "durable"\n---\n\nthe why',
        encoding="utf-8",
    )
    old = time.time() - 200 * 86400  # 200 days untouched
    import os

    os.utime(fact, (old, old))

    today = datetime.date.today()
    now = time.time()
    # Drive the exact helper doctor/archive use to list TTL candidates.
    cands = memory_cli._ttl_candidates(mem, today, now, memory_cli.STALE_DAYS)
    names = [name for name, _reason in cands]
    assert "session-summary.md" not in names
