# Orchestrate Workflow

A structured workflow for implementing GitHub issues using specialized agents.

## Workflow

```
MAP-PLAN → [TEST-PLANNER] → [CONTRACT] → PATCH → PROVE
```

| Agent | Purpose |
|-------|---------|
| MAP-PLAN | Analyze issue, identify files, create implementation plan |
| TEST-PLANNER | Generate test matrix and edge cases (optional) |
| CONTRACT | Define API contracts for fullstack changes |
| PATCH | Implement the changes |
| PROVE | Verify with linting, tests, and build |

## Installation

```bash
./install.sh
```

This installs:
- `orchestrate.md` → `~/.claude/commands/`
- Agent instructions → `~/.claude/agents/`

## Usage

```bash
/orchestrate 184           # Standard workflow
/orchestrate 184 --with-tests  # Include test planning phase
```

## Agent Resolution

Agent instructions use project-first fallback:

1. `.claude/agents/{agent}.md` - Project-specific override
2. `~/.claude/agents/{agent}.md` - Global default

This allows projects to customize specific agents while using global defaults for others.

## Artifacts

All workflow artifacts are written to project-local `.agents/outputs/`:

```
.agents/outputs/
├── map-plan-184-020125.md
├── test-plan-184-020125.md  (if --with-tests)
├── contract-184-020125.md   (if fullstack)
├── patch-184-020125.md
└── prove-184-020125.md
```

## Agents

| File | Purpose |
|------|---------|
| `map-plan.md` | Combined mapping and planning for simple issues |
| `map.md` | File mapping for complex issues |
| `plan.md` | Implementation planning for complex issues |
| `test-planner.md` | Test matrix and edge case generation |
| `contract.md` | API contract definition |
| `patch.md` | Implementation execution |
| `prove.md` | Verification and validation |
