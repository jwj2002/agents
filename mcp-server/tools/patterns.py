"""MCP tools for managing reusable code patterns.

Patterns are stored as YAML files in mcp-server/patterns/.
Agents query patterns on-demand instead of loading large files into context.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

PATTERNS_DIR = Path(__file__).parent.parent / "patterns"


def _load_pattern(path: Path) -> dict:
    """Load a single pattern YAML file."""
    if HAS_YAML:
        with open(path) as f:
            return yaml.safe_load(f)
    else:
        # Fallback: simple YAML parsing for flat structures
        return _parse_yaml_simple(path.read_text())


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser for pattern files (no external deps)."""
    result = {}
    current_key = None
    current_value_lines = []
    in_multiline = False

    for line in text.split("\n"):
        # Skip comments and empty lines at top level
        if line.startswith("#") or (not line.strip() and not in_multiline):
            continue

        # Key: value on one line
        if not in_multiline and re.match(r"^[a-z_]+:", line):
            # Save previous multiline value
            if current_key and current_value_lines:
                result[current_key] = "\n".join(current_value_lines).strip()
                current_value_lines = []

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()

            if value == "|":
                current_key = key
                in_multiline = True
                current_value_lines = []
            elif value.startswith("[") and value.endswith("]"):
                # Inline list
                items = [i.strip().strip("'\"") for i in value[1:-1].split(",") if i.strip()]
                result[key] = items
                current_key = None
            elif value:
                result[key] = value.strip("'\"")
                current_key = None
            else:
                result[key] = ""
                current_key = None
        elif in_multiline:
            if line and not line[0].isspace() and re.match(r"^[a-z_]+:", line):
                # New key — end multiline
                result[current_key] = "\n".join(current_value_lines).strip()
                current_value_lines = []
                in_multiline = False
                # Re-process this line
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip().strip("'\"")
                current_key = None
            else:
                current_value_lines.append(line)

    # Final multiline value
    if current_key and current_value_lines:
        result[current_key] = "\n".join(current_value_lines).strip()

    return result


def get_pattern(name: str) -> dict:
    """Get a single pattern by name.

    Args:
        name: Pattern name (e.g., 'fastapi-module', 'websocket-singleton')

    Returns:
        Dict with pattern data: name, category, description, tags, content, usage_notes
    """
    pattern_file = PATTERNS_DIR / f"{name}.yaml"
    if not pattern_file.exists():
        # Try partial match
        matches = list(PATTERNS_DIR.glob(f"*{name}*.yaml"))
        if len(matches) == 1:
            pattern_file = matches[0]
        elif len(matches) > 1:
            return {
                "error": f"Ambiguous pattern name '{name}'. Matches: {[m.stem for m in matches]}",
                "suggestion": "Use list_patterns() to see all available patterns",
            }
        else:
            return {
                "error": f"Pattern '{name}' not found",
                "available": [p.stem for p in sorted(PATTERNS_DIR.glob("*.yaml"))],
            }

    data = _load_pattern(pattern_file)
    data["_source"] = str(pattern_file)
    return data


def list_patterns(category: str = "") -> dict:
    """List available patterns with names and descriptions.

    Args:
        category: Optional filter (e.g., 'backend', 'frontend', 'workflow')

    Returns:
        Dict with patterns list and categories summary
    """
    patterns = []
    categories = set()

    for path in sorted(PATTERNS_DIR.glob("*.yaml")):
        data = _load_pattern(path)
        cat = data.get("category", "uncategorized")
        categories.add(cat)

        if category and cat != category:
            continue

        patterns.append({
            "name": data.get("name", path.stem),
            "category": cat,
            "description": data.get("description", ""),
            "tags": data.get("tags", []),
        })

    return {
        "total": len(patterns),
        "filter": category or "all",
        "categories": sorted(categories),
        "patterns": patterns,
    }


def create_pattern(
    name: str,
    category: str,
    description: str,
    content: str,
    tags: str = "",
    usage_notes: str = "",
) -> dict:
    """Create a new pattern YAML file.

    Args:
        name: Pattern name (kebab-case, e.g., 'my-custom-pattern')
        category: Category ('backend', 'frontend', 'workflow', 'convention')
        description: One-line description
        content: The pattern content (code templates, conventions, rules)
        tags: Comma-separated tags (e.g., 'fastapi,crud,async')
        usage_notes: When and how to use this pattern

    Returns:
        Dict with created file path and pattern summary
    """
    # Sanitize name
    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    if not safe_name:
        return {"error": "Invalid pattern name"}

    pattern_file = PATTERNS_DIR / f"{safe_name}.yaml"
    if pattern_file.exists():
        return {"error": f"Pattern '{safe_name}' already exists. Use a different name."}

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)

    # Build YAML content manually (no yaml dependency needed for writing)
    yaml_content = f"""name: {safe_name}
category: {category}
description: "{description}"
tags: [{', '.join(f'"{t}"' for t in tag_list)}]
created: "{datetime.now().strftime('%Y-%m-%d')}"
content: |
"""
    # Indent content for YAML block scalar
    for line in content.split("\n"):
        yaml_content += f"  {line}\n"

    if usage_notes:
        yaml_content += "usage_notes: |\n"
        for line in usage_notes.split("\n"):
            yaml_content += f"  {line}\n"

    pattern_file.write_text(yaml_content)

    return {
        "created": str(pattern_file),
        "name": safe_name,
        "category": category,
        "description": description,
        "tags": tag_list,
    }
