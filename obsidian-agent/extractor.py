"""Extract structured information from conversations using Claude."""
import json
import re
import subprocess
from dataclasses import dataclass


@dataclass
class SessionExtract:
    """Extracted information from a coding session."""
    summary: str
    next_steps: list[str]
    completed: list[str]
    decisions: list[str]
    blockers: list[str]
    github_refs: list[str]
    files_touched: list[str]
    knowledge: list[str]  # [CAPTURE] tagged items


def extract_captures(conversation_text: str) -> list[str]:
    """Extract [CAPTURE] tagged content from conversation."""
    captures = []

    # Split into lines and look for User:/Assistant: messages with [CAPTURE]
    lines = conversation_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        # Only match explicit User: [CAPTURE] or Assistant: [CAPTURE]
        is_user_capture = line.startswith('User: [CAPTURE]')
        is_assistant_capture = line.startswith('Assistant: [CAPTURE]')

        if is_user_capture or is_assistant_capture:
            # Extract the capture content
            if is_user_capture:
                content = line[len('User: [CAPTURE]'):].strip()
            else:
                content = line[len('Assistant: [CAPTURE]'):].strip()

            # Collect multiline content until next User:/Assistant: or empty line
            i += 1
            while i < len(lines):
                next_line = lines[i]
                # Stop at next speaker
                if next_line.startswith('User:') or next_line.startswith('Assistant:'):
                    break
                if next_line.startswith('A:'):
                    break
                # Stop at empty line followed by content (paragraph break)
                if not next_line.strip():
                    # Check if this is end of capture
                    if i + 1 >= len(lines) or lines[i + 1].startswith(('User:', 'Assistant:', 'A:', '[')):
                        break
                content += '\n' + next_line
                i += 1

            content = content.strip()
            if content and len(content) > 10:  # Filter out noise
                captures.append(content)
        else:
            i += 1

    return captures


EXTRACTION_PROMPT = '''You are a JSON extraction bot. Your ONLY job is to output valid JSON. No explanations. No markdown. No conversation. Just JSON.

Extract information from the coding session below and return this EXACT JSON structure:

{"summary":"<1-2 sentences>","next_steps":["<task>"],"completed":["<item>"],"decisions":["<decision>"],"blockers":["<blocker>"],"github_refs":["<ref>"],"files_touched":["<path>"]}

Extraction rules:
- next_steps: Future tasks mentioned ("need to", "should", "TODO", "next step")
- completed: Finished work ("created", "fixed", "implemented", "done", "built")
- decisions: Technical choices ("chose X", "using Y because", "decided to")
- blockers: Impediments ("blocked by", "waiting on", "can't until")
- github_refs: Issue/PR numbers (#123, PR #45)
- files_touched: File paths from tool calls or mentions
- Empty array [] if none found

CRITICAL: Output ONLY the JSON object. No other text. Start with { and end with }

---SESSION START---
'''


def strip_markdown_code_blocks(text: str) -> str:
    """Remove markdown code block wrappers from text."""
    # Remove ```json ... ``` or ``` ... ```
    pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return text


def extract_with_claude(conversation_text: str) -> SessionExtract:
    """Use Claude CLI to extract information from conversation."""

    prompt = EXTRACTION_PROMPT + conversation_text + "\n---SESSION END---\n\nJSON output:"

    # Use claude CLI in non-interactive mode with haiku for speed
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json", "--model", "haiku"],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    # Parse the response - claude outputs JSON with result field
    try:
        response = json.loads(result.stdout)
        # Extract the actual content from Claude's response
        content = response.get("result", result.stdout)

        # Strip markdown code blocks if present
        if isinstance(content, str):
            content = strip_markdown_code_blocks(content)
            # Find JSON in the response
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                content = content[start:end]
            data = json.loads(content)
        else:
            data = content

    except json.JSONDecodeError:
        # If parsing fails, try to extract JSON from the raw output
        output = result.stdout
        output = strip_markdown_code_blocks(output)
        start = output.find('{')
        end = output.rfind('}') + 1
        if start >= 0 and end > start:
            data = json.loads(output[start:end])
        else:
            raise ValueError(f"Could not parse Claude response as JSON: {output[:500]}")

    # Extract [CAPTURE] tags directly from conversation (no LLM needed)
    knowledge = extract_captures(conversation_text)

    return SessionExtract(
        summary=data.get("summary", "No summary available"),
        next_steps=data.get("next_steps", []),
        completed=data.get("completed", []),
        decisions=data.get("decisions", []),
        blockers=data.get("blockers", []),
        github_refs=data.get("github_refs", []),
        files_touched=data.get("files_touched", []),
        knowledge=knowledge
    )
