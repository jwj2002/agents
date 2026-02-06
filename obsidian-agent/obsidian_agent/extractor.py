"""Extract structured state information from conversations using Claude CLI.

v2: Focuses on project state and deliverables, not file lists.
"""
import json
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class SessionExtract:
    """Extracted project state from a coding session."""
    status: str  # One-line current state
    phase: str  # Current phase/milestone
    summary: str  # 1-2 sentence session summary
    completed: list[str] = field(default_factory=list)  # Deliverables finished
    next_steps: list[str] = field(default_factory=list)  # Actionable items
    decisions: list[str] = field(default_factory=list)  # Technical choices
    blockers: list[str] = field(default_factory=list)  # What's stuck
    github_refs: list[str] = field(default_factory=list)  # Issue/PR numbers
    knowledge: list[str] = field(default_factory=list)  # [CAPTURE] tagged items


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
{"status":"<one-line current state, e.g. Implementing JWT auth for FastAPI backend>","phase":"<current phase/milestone, e.g. Phase 1: Authentication, or empty string if unclear>","summary":"<1-2 sentence session summary>","completed":["<deliverable finished, e.g. Added login endpoint with bcrypt hashing>"],"next_steps":["<actionable item with priority, e.g. [HIGH] Wire up refresh token rotation>"],"decisions":["<technical choice, e.g. Chose SQLite over PostgreSQL for zero-infrastructure deployment>"],"blockers":["<what is stuck, e.g. Blocked on Qdrant tag filtering API — docs unclear>"],"github_refs":["<issue or PR, e.g. #105, PR #42>"]}

Extraction rules:
- status: What is the project doing RIGHT NOW? One line, present tense
- phase: Current milestone or sprint phase. Empty string if not clear
- summary: Brief overview of what happened this session
- completed: Finished DELIVERABLES (features, fixes, specs), not individual file edits
- next_steps: Future tasks. Prefix with [HIGH], [MED], or [LOW] priority
- decisions: Technical choices with reasoning ("chose X because Y")
- blockers: Things preventing progress ("blocked by", "waiting on", "can't until")
- github_refs: Issue/PR numbers (#123, PR #45)
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

    return SessionExtract(
        status=data.get("status", "Unknown"),
        phase=data.get("phase", ""),
        summary=data.get("summary", "No summary available"),
        completed=data.get("completed", []),
        next_steps=data.get("next_steps", []),
        decisions=data.get("decisions", []),
        blockers=data.get("blockers", []),
        github_refs=data.get("github_refs", []),
        knowledge=knowledge,
    )
