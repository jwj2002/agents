#!/usr/bin/env python3
"""
Code Review Agent

Reviews staged git changes before commit:
- Security issues
- Likely bugs
- Missing error handling
- Code smells
- Pattern violations

Usage:
    python review.py              # Review staged changes
    python review.py --all        # Review all uncommitted changes
    python review.py --strict     # Exit non-zero if warnings found
    python review.py --fix        # Suggest fixes
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import CRITICAL_PATTERNS

REVIEW_PROMPT = '''You are a code review bot. Review the git diff below and identify issues.

Return ONLY valid JSON with this structure:
{
  "summary": "1-2 sentence overall assessment",
  "issues": [
    {
      "severity": "critical|warning|info",
      "category": "security|bug|error-handling|code-smell|style|todo",
      "file": "path/to/file.py",
      "line": 42,
      "description": "What's wrong",
      "suggestion": "How to fix it"
    }
  ],
  "approved": true|false
}

## Review Checklist

### Critical (block commit)
- SQL injection, XSS, command injection
- Hardcoded secrets, API keys, passwords
- Obvious null/None dereference evident within the diff
- Infinite loops, resource leaks

### Warning (should fix)
- Missing error handling for external calls
- Unchecked array access
- TODO/FIXME left in code
- Console.log / print statements (debug code)
- Magic numbers without explanation

### Info (suggestions)
- Naming improvements
- Simplification opportunities
- Missing type hints
- Documentation gaps

## Critical Patterns to Check
''' + "\n".join(f"- {p}" for p in CRITICAL_PATTERNS) + '''

## Rules
- Only report real issues, not style preferences
- Be specific about line numbers
- approved=false if ANY critical issues
- approved=true if only info/warnings
- Empty issues array if code looks good
- SCOPE: you see ONLY the diff hunks, not whole files. A name used in the diff
  (variable, function, import, attribute) may be defined ELSEWHERE in the file,
  outside this hunk. Do NOT report "undefined variable", "undefined name",
  "X is not defined", NameError-style, or "not imported" issues — you cannot
  verify a definition you cannot see, and ruff's full-file static analysis
  (run separately in the same pre-commit) already catches genuinely-undefined
  names. Only flag an issue if it is FULLY evident within the diff itself.

DIFF:
'''


def get_staged_diff() -> str:
    """Get staged changes."""
    result = subprocess.run(
        ["git", "diff", "--staged", "--no-color"],
        capture_output=True,
        text=True
    )
    return result.stdout


def get_all_diff() -> str:
    """Get all uncommitted changes."""
    result = subprocess.run(
        ["git", "diff", "--no-color", "HEAD"],
        capture_output=True,
        text=True
    )
    return result.stdout


def get_staged_files() -> list[str]:
    """Get list of staged files."""
    result = subprocess.run(
        ["git", "diff", "--staged", "--name-only"],
        capture_output=True,
        text=True
    )
    return [f for f in result.stdout.strip().split("\n") if f]


def get_all_files() -> list[str]:
    """Get list of all uncommitted files."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True
    )
    return [f for f in result.stdout.strip().split("\n") if f]


def review_with_claude(diff: str, *, fail_closed: bool = False) -> dict:
    """Send diff to Claude for review."""
    if not diff.strip():
        return {
            "summary": "No changes to review.",
            "issues": [],
            "approved": True
        }

    truncated = False

    # Truncate very long diffs
    if len(diff) > 50000:
        diff = diff[:50000] + "\n\n... (diff truncated)"
        truncated = True

    prompt = REVIEW_PROMPT + diff

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", "haiku"],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        return {
            "summary": "Review failed",
            "issues": [{"severity": "warning", "category": "tool",
                       "description": f"Claude CLI error: {result.stderr}"}],
            "approved": not fail_closed
        }

    try:
        response = json.loads(result.stdout)
        content = response.get("result", "")

        # Strip markdown code blocks
        if "```" in content:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if match:
                content = match.group(1)

        # Find JSON
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            review = json.loads(content[start:end])
            if truncated:
                review.setdefault("issues", []).append({
                    "severity": "warning",
                    "category": "tool",
                    "file": "?",
                    "line": None,
                    "description": "Diff exceeded 50,000 characters and was truncated before review.",
                    "suggestion": "Split the change or review per file before committing."
                })
                if fail_closed:
                    review["approved"] = False
            return review

    except (json.JSONDecodeError, Exception) as e:
        return {
            "summary": f"Failed to parse review: {e}",
            "issues": [{"severity": "warning", "category": "tool",
                       "description": "Could not parse Claude review output."}],
            "approved": not fail_closed
        }

    return {
        "summary": "No review generated",
        "issues": [{"severity": "warning", "category": "tool",
                   "description": "Claude returned no review content."}],
        "approved": not fail_closed,
    }


def format_review(review: dict, files: list[str]) -> str:
    """Format review for terminal output."""
    lines = []

    # Header
    lines.append("=" * 60)
    lines.append("CODE REVIEW")
    lines.append("=" * 60)
    lines.append("")

    # Files
    lines.append(f"Files: {len(files)}")
    for f in files[:10]:
        lines.append(f"  - {f}")
    if len(files) > 10:
        lines.append(f"  ... and {len(files) - 10} more")
    lines.append("")

    # Summary
    lines.append(f"Summary: {review.get('summary', 'N/A')}")
    lines.append("")

    # Issues by severity
    issues = review.get("issues", [])

    critical = [i for i in issues if i.get("severity") == "critical"]
    warnings = [i for i in issues if i.get("severity") == "warning"]
    info = [i for i in issues if i.get("severity") == "info"]

    if critical:
        lines.append("CRITICAL ISSUES (must fix):")
        lines.append("-" * 40)
        for issue in critical:
            lines.append(f"  [{issue.get('category', '?')}] {issue.get('file', '?')}:{issue.get('line', '?')}")
            lines.append(f"    {issue.get('description', '')}")
            if issue.get("suggestion"):
                lines.append(f"    → {issue['suggestion']}")
            lines.append("")

    if warnings:
        lines.append("WARNINGS (should fix):")
        lines.append("-" * 40)
        for issue in warnings:
            lines.append(f"  [{issue.get('category', '?')}] {issue.get('file', '?')}:{issue.get('line', '?')}")
            lines.append(f"    {issue.get('description', '')}")
            if issue.get("suggestion"):
                lines.append(f"    → {issue['suggestion']}")
            lines.append("")

    if info:
        lines.append("SUGGESTIONS:")
        lines.append("-" * 40)
        for issue in info:
            lines.append(f"  [{issue.get('category', '?')}] {issue.get('file', '?')}:{issue.get('line', '?')}")
            lines.append(f"    {issue.get('description', '')}")
            lines.append("")

    if not issues:
        lines.append("No issues found.")
        lines.append("")

    # Verdict
    lines.append("=" * 60)
    approved = review.get("approved", True)
    if approved:
        lines.append("APPROVED ✓")
    else:
        lines.append("NOT APPROVED ✗ - Fix critical issues before committing")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Review staged git changes")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Review all uncommitted changes")
    parser.add_argument("--strict", "-s", action="store_true",
                        help="Exit non-zero if any issues found")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON")

    args = parser.parse_args()

    # Get diff
    if args.all:
        diff = get_all_diff()
        files = get_all_files()
    else:
        diff = get_staged_diff()
        files = get_staged_files()

    if not diff.strip():
        print("No changes to review.")
        print("Stage changes with: git add <files>")
        return

    print(f"Reviewing {len(files)} staged files...")
    print("")

    # Run review
    review = review_with_claude(diff, fail_closed=args.strict)

    if args.json:
        print(json.dumps(review, indent=2))
    else:
        print(format_review(review, files))

    # Exit code
    if args.strict:
        issues = review.get("issues", [])
        if issues:
            sys.exit(1)

    if not review.get("approved", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
