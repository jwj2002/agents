"""Render a markdown dashboard digest to email-ready HTML.

Output is a complete, self-contained HTML document with inline CSS that
survives Outlook/Gmail's CSS sanitization (no flexbox, no @media, no
external stylesheets). Tables get borders + zebra striping, code/<pre>
gets a monospace box, and the digest's leading
`<!-- dashboard-digest v1 ... -->` header comment is preserved verbatim
inside the rendered body so a downstream agent can still recognize it
in the raw HTML if needed.

Usage:
    python3 render_markdown.py --in digest.md --out digest.html
    python3 render_markdown.py < digest.md > digest.html
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import markdown


# Inline CSS designed for email client compatibility.
# - No flexbox / grid / @media / external links
# - Generic font stack (no @font-face)
# - Table borders rendered as inline borders so Outlook respects them
EMAIL_CSS = """\
body {
    font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    color: #1f2328;
    max-width: 820px;
    margin: 16px auto;
    padding: 0 16px;
}
h1 { font-size: 22px; border-bottom: 2px solid #d0d7de; padding-bottom: 6px; margin-top: 24px; }
h2 { font-size: 18px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; margin-top: 22px; }
h3 { font-size: 16px; margin-top: 18px; color: #57606a; }
p, ul, ol { margin: 8px 0; }
ul, ol { padding-left: 24px; }
li { margin: 2px 0; }
strong { color: #1f2328; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 13px;
}
th, td {
    border: 1px solid #d0d7de;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}
th { background: #f6f8fa; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 12px;
    background: #f6f8fa;
    padding: 2px 4px;
    border-radius: 3px;
}
pre {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 12px;
    background: #f6f8fa;
    padding: 10px 12px;
    border-radius: 4px;
    overflow-x: auto;
    border: 1px solid #d0d7de;
}
pre code { background: transparent; padding: 0; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 18px 0; }
.digest-header {
    color: #6e7781;
    font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 11px;
    margin-bottom: 4px;
}
"""


DIGEST_HEADER_RE = re.compile(r"^<!--\s*(dashboard-digest\s+v\d+\s+.+?)\s*-->", re.MULTILINE)


def render(md_text: str) -> str:
    """Return a complete HTML document for the given markdown digest."""
    # Pull out the digest header so we can also surface it as a visible
    # mono-spaced line at the top of the rendered email — agents grep
    # for the literal HTML comment, humans see the version.
    header_match = DIGEST_HEADER_RE.search(md_text)
    header_text = header_match.group(1) if header_match else None

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )

    header_div = (
        f'<div class="digest-header">&lt;!-- {header_text} --&gt;</div>\n'
        if header_text else ""
    )

    return (
        "<!DOCTYPE html>\n"
        '<html><head><meta charset="utf-8">\n'
        f"<style>{EMAIL_CSS}</style>\n"
        "</head><body>\n"
        f"{header_div}{html_body}\n"
        "</body></html>\n"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="input", help="Markdown source path (default: stdin)")
    p.add_argument("--out", dest="output", help="HTML output path (default: stdout)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    md_text = Path(args.input).read_text() if args.input else sys.stdin.read()
    html = render(md_text)
    if args.output:
        Path(args.output).write_text(html)
    else:
        sys.stdout.write(html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
