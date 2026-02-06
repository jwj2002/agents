# Core Failure Patterns (Always Loaded)

These 3 patterns cause >50% of agent failures. Apply proactively.

| Pattern | Trigger | Prevention |
|---------|---------|------------|
| **ENUM_VALUE** (26%) | Fullstack issue with role/status/type fields | Read backend enum, use VALUE string not Python name (`"CO-OWNER"` not `"CO_OWNER"`) |
| **COMPONENT_API** (17%) | Reusing existing frontend component/hook | Read actual source file, extract PropTypes before using |
| **VERIFICATION_GAP** | Any assumption about code structure | Verify by reading actual code — never assume |

**Full patterns**: `.claude/memory/patterns-full.md` (load for COMPLEX issues)
