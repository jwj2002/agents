# Codex Plugin

The Codex plugin brings OpenAI's Codex CLI inside Claude Code as a set of slash commands. This enables cross-model code review, adversarial design challenge, and task delegation -- all without leaving your Claude Code session.

## Installation

### Step 1: Add the marketplace

The Codex plugin is distributed through a custom marketplace. Add it in `settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "openai-codex": {
      "source": {
        "source": "github",
        "repo": "openai/codex-plugin-cc"
      }
    }
  },
  "enabledPlugins": {
    "codex@openai-codex": true
  }
}
```

### Step 2: Install and setup

```bash
# Install the plugin from marketplace
/codex:setup
```

The setup command validates that the Codex CLI is installed and authenticated, and configures the review gate toggle.

### Step 3: Configure Codex

Edit `~/.codex/config.toml` to set defaults:

```toml
[defaults]
model = "o4-mini"
approval_mode = "suggest"
```

## Commands

### /codex:setup

Validates Codex CLI installation and authentication. Toggles the review gate on or off.

```bash
/codex:setup              # Validate + configure
```

### /codex:review

Runs a code review on current git state using Codex.

```bash
/codex:review                        # Review uncommitted changes
/codex:review --base origin/main     # Review against specific base
/codex:review --scope "backend/"     # Limit review scope
/codex:review --background           # Run in background, check later
/codex:review --wait                 # Block until review completes
```

| Flag | Description |
|------|-------------|
| `--wait` | Block until review completes (default for foreground) |
| `--background` | Run asynchronously, retrieve with `/codex:result` |
| `--base` | Git ref to diff against (default: HEAD) |
| `--scope` | Limit review to specific paths |

### /codex:adversarial-review

A devil's advocate review that challenges design decisions rather than finding bugs. Codex evaluates architectural choices, naming conventions, and approach tradeoffs.

```bash
/codex:adversarial-review                           # Review full changes
/codex:adversarial-review "database schema design"  # Focus on specific area
```

!!! tip "Cross-Model Blind Spots"
    Claude and Codex have different training data and different failure modes. Using Codex to review Claude's output catches errors that Claude's own review would miss -- and vice versa.

### /codex:rescue

Delegates a task to Codex when Claude is stuck or when you want a second implementation attempt.

```bash
/codex:rescue                    # Delegate current task
/codex:rescue --resume           # Continue a previous rescue
/codex:rescue --fresh            # Start fresh (ignore prior context)
/codex:rescue --model o4-mini    # Use specific model
/codex:rescue --effort high      # Set effort level
```

| Flag | Description |
|------|-------------|
| `--resume` | Continue from where a previous rescue left off |
| `--fresh` | Discard prior context and start clean |
| `--model` | Override the default Codex model |
| `--effort` | Set effort level (low, medium, high) |

### /codex:status

Shows running and recently completed Codex jobs.

```bash
/codex:status             # Show active jobs
/codex:status --wait      # Block until current job completes
/codex:status --all       # Include completed jobs
```

### /codex:result

Displays the output of a finished Codex job.

```bash
/codex:result             # Show most recent result
```

### /codex:cancel

Cancels an active Codex job.

```bash
/codex:cancel             # Cancel current job
```

## Cross-Model Adversarial Review Strategy

The highest-value use of the Codex plugin is adversarial review: Claude writes code, Codex reviews it.

```
Claude Code (implementation)
       |
       v
/codex:adversarial-review
       |
       v
Codex challenges assumptions
       |
       v
Claude addresses findings
```

**Why this works**: Different models have different blind spots. Claude might produce correct logic but miss an edge case in error handling. Codex might catch that edge case because its training distribution weights error handling differently. The reverse is also true -- Claude catches things Codex misses.

## Automatic Review via Implementation Routing

Codex review is **automatically applied based on task complexity** — you don't need to remember to run it. The [implementation routing rule](../workflow/orchestrate.md#implementation-routing) handles this:

| Task Complexity | Codex Review | What Happens |
|-----------------|-------------|-------------|
| **TRIVIAL** | Skip | Not worth the overhead |
| **SIMPLE** | Offer | "Want a cross-model review?" after implementation |
| **MODERATE** | Recommended | `/codex:review --background` runs after implementation |
| **COMPLEX** | Automatic | `/codex:adversarial-review --background` runs after PROVE |
| **FULLSTACK** | Automatic + focused | Review focuses on enum value mismatches and API contract compliance |
| **PRIOR FAILURE** | Automatic + targeted | Review focuses on the prior root cause |

### How It Works With Orchestrate

For MODERATE+ tasks, the review runs after PROVE passes:

```
PATCH completes
     │
     ▼
PROVE passes (all 4 levels)
     │
     ▼
/codex:adversarial-review --background
  "Focus on: enum value mismatches, API contract
   compliance, access control, transaction integrity"
     │
     ├── No findings → /pr
     └── Findings → fix issues → re-run PROVE → /pr
```

!!! tip "You don't trigger this manually"
    Claude reads the routing rule, assesses your task, and decides whether to run Codex review. You just describe what you want done.

### Rescue as PATCH Fallback

When PATCH is BLOCKED and re-attempting with failure context doesn't fix it:

```bash
# Different model, different approach to the same problem
/codex:rescue "investigate and fix: {description of the stuck issue}"
```

The escalation path:

1. Re-run PATCH with failure context (standard)
2. `/codex:rescue` (different model perspective)
3. Escalate to human

## Review Gate

!!! warning "Experimental Feature"
    The review gate is an experimental feature. Use it cautiously and monitor for false positives that block legitimate changes.

When enabled via `/codex:setup`, the review gate runs an automatic Codex review before certain operations (e.g., commit, PR creation). If the review identifies critical issues, it blocks the operation until the issues are addressed.

Enable or disable the gate:

```bash
/codex:setup    # Toggle review gate on/off
```

## Configuration

Codex configuration lives at `~/.codex/config.toml`:

```toml
[defaults]
model = "o4-mini"           # Default model for all commands
approval_mode = "suggest"   # "suggest" or "auto-approve"
```

The plugin itself is configured in Claude Code's `settings.json` under `enabledPlugins` and `extraKnownMarketplaces`.
