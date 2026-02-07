"""Extract structured state information from conversations using Claude CLI.

v2: Focuses on project state and deliverables, not file lists.
"""
import json
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class CompletedGroup:
    """A group of related completed items under a heading."""
    heading: str
    items: list[str]


@dataclass
class IssueRef:
    """A GitHub issue reference with metadata."""
    number: str
    title: str
    effort: str = ""
    status: str = "Pending"


@dataclass
class CommitRef:
    """A git commit reference."""
    hash: str
    message: str


@dataclass
class SessionExtract:
    """Extracted project state from a coding session."""
    status: str  # One-line current state
    phase: str  # Current phase/milestone
    summary: str  # 1-2 sentence session summary
    completed: list[str] = field(default_factory=list)  # Flat list (legacy)
    completed_groups: list[CompletedGroup] = field(default_factory=list)  # Grouped by topic
    issues: list[IssueRef] = field(default_factory=list)  # Issue table data
    commits: list[CommitRef] = field(default_factory=list)  # Git commits (injected, not from LLM)
    next_steps: list[str] = field(default_factory=list)  # Actionable items (checkboxes)
    decisions: list[str] = field(default_factory=list)  # Technical choices
    blockers: list[str] = field(default_factory=list)  # What's stuck
    github_refs: list[str] = field(default_factory=list)  # Issue/PR numbers
    knowledge: list[str] = field(default_factory=list)  # [CAPTURE] tagged items
    notes: list[str] = field(default_factory=list)  # Freeform context worth capturing


def extract_captures(conversation_text: str) -> list[str]:
    """Extract [CAPTURE] tagged content from conversation."""
    captures = []

    lines = conversation_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        is_user_capture = line.startswith("User: [CAPTURE]")
        is_assistant_capture = line.startswith("Assistant: [CAPTURE]")

        if is_user_capture or is_assistant_capture:
            if is_user_capture:
                content = line[len("User: [CAPTURE]"):].strip()
            else:
                content = line[len("Assistant: [CAPTURE]"):].strip()

            # Collect multiline content until next speaker or empty line
            i += 1
            while i < len(lines):
                next_line = lines[i]
                if next_line.startswith("User:") or next_line.startswith("Assistant:"):
                    break
                if next_line.startswith("A:"):
                    break
                if not next_line.strip():
                    if i + 1 >= len(lines) or lines[i + 1].startswith(("User:", "Assistant:", "A:", "[")):
                        break
                content += "\n" + next_line
                i += 1

            content = content.strip()
            if content and len(content) > 10:
                captures.append(content)
        else:
            i += 1

    return captures


EXTRACTION_PROMPT = '''You are a JSON extraction bot. Output ONLY valid JSON. No explanations. No markdown. No conversation.

Extract the current PROJECT STATE from the coding session below. Focus on deliverables and status, not file paths.

Return this EXACT JSON structure:
{"status":"<one-line current state, e.g. Implementing JWT auth for FastAPI backend>","phase":"<current phase/milestone, e.g. Phase 1: Authentication, or empty string if unclear>","summary":"<1-2 sentence session summary>","completed_groups":[{"heading":"<topic name, e.g. Background Reindex Worker>","items":["<specific deliverable>"]}],"issues":[{"number":"#123","title":"Short title","effort":"1.5d","status":"Pending"}],"next_steps":["<actionable item with priority, e.g. [HIGH] Wire up refresh token rotation>"],"decisions":["<technical choice, e.g. Chose SQLite over PostgreSQL for zero-infrastructure deployment>"],"blockers":["<what is stuck, e.g. Blocked on Qdrant tag filtering API — docs unclear>"],"github_refs":["<issue or PR, e.g. #105, PR #42>"],"notes":["<freeform context worth remembering, e.g. Expected 36s → <100ms for cached queries>"]}

Extraction rules:
- status: What is the project doing RIGHT NOW? One line, present tense
- phase: Current milestone or sprint phase. Empty string if not clear
- summary: Brief overview of what happened this session
- completed_groups: Group related completed items under a descriptive heading. Each group has a heading (topic name) and items (specific deliverables). Prefer 2-5 groups over a flat list. If only 1-2 items, use a single group.
- issues: GitHub issues created or worked on this session. Include number, title, effort estimate, and status (Done/Pending/In Progress). Empty array if no issues discussed.
- next_steps: Future tasks as actionable items. Prefix with [HIGH], [MED], or [LOW] priority
- decisions: Technical choices with reasoning ("chose X because Y")
- blockers: Things preventing progress ("blocked by", "waiting on", "can't until")
- github_refs: All issue/PR numbers mentioned (#123, PR #45)
- notes: Important context, metrics, or explanations worth remembering (performance numbers, model comparisons, server status). NOT duplicates of completed items.
- Empty array [] if none found for a category

CRITICAL: Output ONLY the JSON object. Start with { and end with }

---SESSION START---
'''


def strip_markdown_code_blocks(text: str) -> str:
    """Remove markdown code block wrappers from text."""
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return text


def _parse_json_response(raw: str) -> dict:
    """Parse JSON from Claude CLI output, handling various response formats."""
    # Try direct parse first
    try:
        response = json.loads(raw)
        content = response.get("result", raw)
    except json.JSONDecodeError:
        content = raw

    if isinstance(content, dict):
        return content

    # Strip markdown code blocks
    content = strip_markdown_code_blocks(content)

    # Find JSON object in the response
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(content[start:end])

    raise ValueError(f"Could not parse JSON from response: {content[:500]}")


def extract_with_claude(conversation_text: str, model: str = "haiku") -> SessionExtract:
    """Use Claude CLI to extract project state from conversation."""
    prompt = EXTRACTION_PROMPT + conversation_text + "\n---SESSION END---\n\nJSON output:"

    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", model],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    data = _parse_json_response(result.stdout)

    # Extract [CAPTURE] tags directly (no LLM needed)
    knowledge = extract_captures(conversation_text)

    # Parse completed_groups
    raw_groups = data.get("completed_groups", [])
    completed_groups = []
    for g in raw_groups:
        if isinstance(g, dict) and g.get("heading"):
            completed_groups.append(CompletedGroup(
                heading=g["heading"],
                items=g.get("items", []),
            ))

    # Parse issues
    raw_issues = data.get("issues", [])
    issues = []
    for i in raw_issues:
        if isinstance(i, dict) and i.get("number"):
            issues.append(IssueRef(
                number=i["number"],
                title=i.get("title", ""),
                effort=i.get("effort", ""),
                status=i.get("status", "Pending"),
            ))

    # Backward compat: flatten completed_groups into completed
    flat_completed = data.get("completed", [])
    if not flat_completed and completed_groups:
        for g in completed_groups:
            flat_completed.extend(g.items)

    return SessionExtract(
        status=data.get("status", "Unknown"),
        phase=data.get("phase", ""),
        summary=data.get("summary", "No summary available"),
        completed=flat_completed,
        completed_groups=completed_groups,
        issues=issues,
        next_steps=data.get("next_steps", []),
        decisions=data.get("decisions", []),
        blockers=data.get("blockers", []),
        github_refs=data.get("github_refs", []),
        knowledge=knowledge,
        notes=data.get("notes", []),
    )
