"""E15 SECRETS_IN_CODE — hardcoded credentials in added lines.

Precision strategy: provider-prefixed token formats (high confidence) plus
assignment-shaped generic secrets with an entropy-ish length floor.
Placeholders (env lookups, format strings, obvious dummies, fixtures) are
excluded. `# eval-ok: E15` allowlists a line (use for test fixtures with a
reason).
"""

from __future__ import annotations

import re

from .common import ChangeSet, Finding, allowlisted

EVAL_ID = "E15"

# High-confidence provider token shapes.
_TOKEN_RES = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                      # AWS access key id
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"), # OpenAI/Anthropic-style
    re.compile(r"ghp_[A-Za-z0-9]{36}"),                   # GitHub PAT
    re.compile(r"gho_[A-Za-z0-9]{36}"),                   # GitHub OAuth
    re.compile(r"glpat-[A-Za-z0-9_-]{20}"),               # GitLab PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),          # Slack
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),                 # Google API key
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]

# Generic `password = "literal"` style assignment (py/js/yaml/env).
_ASSIGN_RE = re.compile(
    r"(?i)\b(password|passwd|secret|api_?key|auth_?token|access_?token|client_?secret)\b"
    r"\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)

_PLACEHOLDER_RE = re.compile(
    r"(?i)(\$\{|\{\{|%s|%\(|<[^>]+>|x{4,}|\*{3,}|\.\.\.|"
    r"your[-_ ]|example|placeholder|changeme|change[-_ ]me|dummy|fake|test|sample|"
    r"redacted|<<|todo)"
)
_ENV_LOOKUP_RE = re.compile(r"(?i)(os\.environ|getenv|process\.env|secrets\.|vault)")

SKIP_SUFFIXES = (".md", ".lock", ".sum")


def run(cs: ChangeSet) -> list[Finding]:
    findings: list[Finding] = []
    for path in cs.paths:
        if path.endswith(SKIP_SUFFIXES):
            continue
        for lineno, line in cs.added_lines(path):
            if allowlisted(line, EVAL_ID):
                continue
            for rx in _TOKEN_RES:
                if rx.search(line):
                    findings.append(Finding(
                        EVAL_ID, path, lineno,
                        "high-confidence credential pattern "
                        f"({rx.pattern[:30]}…) in added line",
                    ))
                    break
            else:
                m = _ASSIGN_RE.search(line)
                if m and not _PLACEHOLDER_RE.search(line) and not _ENV_LOOKUP_RE.search(line):
                    findings.append(Finding(
                        EVAL_ID, path, lineno,
                        f"hardcoded {m.group(1)} literal — load from env/config "
                        "instead",
                    ))
    return findings
