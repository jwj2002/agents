"""Parse Claude Code conversation logs (.jsonl)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ConversationMessage:
    """A single message in the conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None


@dataclass
class SessionInfo:
    """Information about a Claude Code session."""
    session_id: str
    project_path: str
    project_name: str
    messages: list[ConversationMessage]
    git_branch: str = ""

    @property
    def date(self) -> str:
        """Extract date (YYYY-MM-DD) from the first message timestamp.

        Timestamps look like: '2026-02-06T14:23:45.123Z'
        Falls back to empty string if no messages or unparseable.
        """
        if not self.messages:
            return ""
        ts = self.messages[0].timestamp
        if not ts:
            return ""
        # ISO timestamps start with YYYY-MM-DD
        return ts[:10] if len(ts) >= 10 else ""


def extract_content(message_data: dict) -> tuple[str, Optional[str], Optional[dict]]:
    """Extract text content and tool info from a message."""
    msg = message_data.get("message", {})
    content_parts = msg.get("content", [])

    if isinstance(content_parts, str):
        return content_parts, None, None

    text_parts = []
    tool_name = None
    tool_input = None

    for part in content_parts:
        if isinstance(part, dict):
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif part.get("type") == "tool_use":
                tool_name = part.get("name")
                tool_input = part.get("input")
        elif isinstance(part, str):
            text_parts.append(part)

    return "\n".join(text_parts), tool_name, tool_input


def parse_session_log(log_path: Path) -> SessionInfo:
    """Parse a Claude Code session log file."""
    messages = []
    session_id = ""
    project_path = ""
    git_branch = ""

    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            # Skip non-message entries
            if msg_type not in ("user", "assistant"):
                continue

            # Extract session info from first message
            if not session_id:
                session_id = data.get("sessionId", "")
                project_path = data.get("cwd", "")
                git_branch = data.get("gitBranch", "")

            content, tool_name, tool_input = extract_content(data)

            # Skip empty messages and thinking blocks
            if not content and not tool_name:
                continue

            role = data.get("message", {}).get("role", msg_type)
            timestamp = data.get("timestamp", "")

            messages.append(ConversationMessage(
                role=role,
                content=content,
                timestamp=timestamp,
                tool_name=tool_name,
                tool_input=tool_input,
            ))

    # Extract project name from path
    project_name = Path(project_path).name if project_path else "unknown"

    return SessionInfo(
        session_id=session_id,
        project_path=project_path,
        project_name=project_name,
        messages=messages,
        git_branch=git_branch,
    )


def get_conversation_text(session: SessionInfo, max_chars: int = 50000) -> str:
    """Get conversation as readable text for analysis."""
    lines = []

    for msg in session.messages:
        role = "User" if msg.role == "user" else "Assistant"

        if msg.tool_name:
            lines.append(f"[{role} used tool: {msg.tool_name}]")
            if msg.tool_input:
                # Summarize tool input
                input_str = json.dumps(msg.tool_input, indent=2)
                if len(input_str) > 500:
                    input_str = input_str[:500] + "..."
                lines.append(f"  Input: {input_str}")

        if msg.content:
            lines.append(f"{role}: {msg.content}")

        lines.append("")

    text = "\n".join(lines)

    # Truncate if too long (keep end, which has most recent context)
    if len(text) > max_chars:
        text = "...[earlier conversation truncated]...\n\n" + text[-max_chars:]

    return text
