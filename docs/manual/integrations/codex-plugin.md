# Codex Plugin

The Codex plugin adds OpenAI's GPT to your Claude Code workflow. It serves two roles: reviewing code that Claude wrote (catching blind spots a different model would notice) and implementing tasks in parallel (frontend work, test writing, debugging -- all in the background while Claude continues).

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

## Codex as Implementation Partner (Not Just Reviewer)

Codex is a **write-capable implementation engine**, not just a reviewer. It can create files, modify code, run tests, and implement features — using GPT in the background while Claude continues working.

### Two Roles for Codex

```
┌──────────────────────────────────────────────────────────────┐
│                    CODEX ROLES                                │
│                                                               │
│  1. REVIEWER (after implementation)                          │
│     └── /codex:review, /codex:adversarial-review             │
│         Read-only. Catches blind spots Claude misses.        │
│                                                               │
│  2. IMPLEMENTER (parallel to Claude)                         │
│     └── /codex:rescue --background --write                   │
│         Write-capable. Builds features, fixes bugs,          │
│         writes tests — all in background.                    │
└──────────────────────────────────────────────────────────────┘
```

### Delegation Patterns

#### Parallel Fullstack Split
Claude handles backend (needs MCP, rules, patterns). Codex handles frontend in background.

```bash
# Claude is implementing backend...
/codex:rescue --background --write \
  "Implement frontend component per CONTRACT:
   - Component: PaymentForm at frontend/src/components/
   - API endpoint: POST /api/payments
   - Enum VALUES: STATUS='pending','completed','failed'
   - Run: npm run lint && npm run build when done"
```

#### Test Writing
Claude implements the feature. Codex writes the tests in parallel.

```bash
# Claude finished PATCH, moving to PROVE...
/codex:rescue --background --write \
  "Write tests for backend/backend/payments/services.py
   Test file: backend/backend/payments/tests/test_services.py
   Use pytest + pytest-asyncio. SQLite in-memory only.
   Cover: success cases, validation errors, edge cases.
   Run: cd backend && pytest -q when done."
```

#### Debug Delegation
Claude is implementing issue A. Tests for issue B start failing.

```bash
/codex:rescue --background \
  "Investigate why tests in backend/auth/tests/ are failing.
   Started failing after commit abc123. Find root cause and fix."
```

#### Prior Failure Rescue
Claude's PATCH was BLOCKED twice. Try a different model first.

```bash
/codex:rescue --write --effort xhigh \
  "Fix issue #184. Prior Claude attempt failed with MULTI_MODEL error:
   forgot to update Advisor model when changing User.
   See .agents/outputs/patch-184-032626.md for what was tried."
```

#### Mechanical Refactoring
Large rename/extract/move operations that don't require judgment.

```bash
/codex:rescue --background --write --model gpt-5.4-mini --effort low \
  "Rename all occurrences of 'UserAccount' to 'Account' across
   backend/backend/. Update imports, type hints, test references.
   Run ruff check . when done."
```

### When to Delegate vs Keep in Claude

| Delegate to Codex | Keep in Claude |
|-------------------|---------------|
| Independent subtask (doesn't block Claude) | Primary implementation thread |
| Prior failure (different model = different approach) | Tasks needing MCP servers |
| Frontend during fullstack (Claude does backend) | Tasks needing project rules/patterns |
| Test writing (mechanical, parallel) | Architectural decisions |
| Bug investigation (parallel debugging) | Orchestrate pipeline state management |
| Mechanical refactoring (rename, extract) | Complex multi-model coordination |

??? info "Model and effort selection guide"

    ### Model Selection

    | Task Type | Model | Effort | Why |
    |-----------|-------|--------|-----|
    | Quick review | `gpt-5.4-mini` | `medium` | Fast, cheap |
    | Adversarial review | `gpt-5.4` | `high` | Needs reasoning depth |
    | Bug investigation | `gpt-5.4-mini` | `medium` | Speed matters |
    | Feature implementation | `gpt-5.4` | `high` | Needs quality |
    | Mechanical refactoring | `gpt-5.4-mini` | `low` | Repetitive |
    | Test writing | `gpt-5.4` | `medium` | Needs understanding |
    | Prior failure rescue | `gpt-5.4` | `xhigh` | Maximum reasoning |

## Automatic Routing (Review + Delegation)

Both review and delegation are **automatically applied based on task complexity** — you don't need to remember to run them. The [implementation routing rule](../workflow/orchestrate.md#implementation-routing) handles this:

| Task Complexity | Codex Review | Codex Delegation |
|-----------------|-------------|-----------------|
| **TRIVIAL** | Skip | None |
| **SIMPLE** | Offer after | None |
| **MODERATE** | Recommended | None (single subsystem) |
| **COMPLEX** | Automatic | Delegate independent subtasks |
| **FULLSTACK** | Automatic (enum/API focus) | Delegate frontend to Codex |
| **PRIOR FAIL** | Automatic | Codex-first implementation |

### Orchestrate Integration

```
MAP-PLAN identifies subtasks
     │
     ├── Backend work → Claude PATCH (primary)
     │       │
     │       └── /codex:rescue --background (frontend/tests/refactoring)
     │
     ▼
PROVE passes → /codex:adversarial-review --background
     │
     ├── No findings → /pr
     └── Findings → fix → re-run PROVE → /pr
```

!!! tip "You don't trigger this manually"
    Claude reads the routing rule, assesses your task, and decides what to delegate. You just describe what you want done.

### Escalation Path (Prior Failures)

1. Re-run Claude PATCH with failure context (standard)
2. `/codex:rescue --effort xhigh` (different model perspective)
3. Escalate to human

??? example "Prompt recipes library (advanced)"

    ## Prompt Engineering for Codex Tasks

    The Codex plugin ships with a **prompt recipes library** — reusable XML blocks and end-to-end templates that dramatically improve task quality. These are used internally by the plugin and available for your own `/codex:rescue` prompts.

    ### Prompt Blocks (Building Blocks)

    Wrap each block in its XML tag. Combine blocks to build task prompts.

    | Block | When to Use | What It Does |
    |-------|------------|-------------|
    | `<task>` | Every prompt | Defines the concrete job and expected end state |
    | `<structured_output_contract>` | Response shape matters | Forces specific output format (findings, evidence, next steps) |
    | `<compact_output_contract>` | Want concise prose | Prevents verbose scene-setting and recap |
    | `<default_follow_through_policy>` | Codex should act without asking | "Default to reasonable interpretation, keep going" |
    | `<completeness_contract>` | Multi-step tasks | "Don't stop at first plausible answer, check for follow-on fixes" |
    | `<verification_loop>` | Correctness matters | "Verify result against requirements before finalizing" |
    | `<missing_context_gating>` | Codex might guess | "Don't guess missing facts — retrieve or state what's unknown" |
    | `<grounding_rules>` | Review or analysis | "Ground every claim in context, label hypotheses" |
    | `<action_safety>` | Write-capable tasks | "Keep changes scoped, no unrelated refactors" |
    | `<dig_deeper_nudge>` | Adversarial review | "Check second-order failures, empty-state, retries, rollback" |

    ### Ready-Made Recipes

    Copy the smallest recipe that fits, then trim what you don't need.

    #### Diagnosis Recipe

    ```bash
    /codex:rescue "
    <task>
    Diagnose why tests in backend/auth/tests/ are failing.
    Use repository context and tools to identify root cause.
    </task>
    <compact_output_contract>
    Return: 1. root cause  2. evidence  3. smallest safe next step
    </compact_output_contract>
    <default_follow_through_policy>
    Keep going until root cause is confident. Only stop if missing detail changes correctness.
    </default_follow_through_policy>
    <verification_loop>
    Verify proposed root cause matches observed evidence before finalizing.
    </verification_loop>"
    ```

    #### Narrow Fix Recipe

    ```bash
    /codex:rescue --write "
    <task>
    Implement the smallest safe fix for the failing payment validation.
    Preserve existing behavior outside the failing path.
    </task>
    <completeness_contract>
    Resolve fully. Don't stop after identifying the issue without applying the fix.
    </completeness_contract>
    <verification_loop>
    Verify fix matches requirements and changed code is coherent.
    </verification_loop>
    <action_safety>
    Keep changes scoped. No unrelated refactors or cleanup.
    </action_safety>"
    ```

    #### Root-Cause Review Recipe

    ```bash
    /codex:adversarial-review "
    <task>
    Analyze this change for correctness and regression risks.
    </task>
    <grounding_rules>
    Ground every claim in repository context. Label inferences clearly.
    </grounding_rules>
    <dig_deeper_nudge>
    Check second-order failures, empty-state handling, retries, stale state, rollback paths.
    </dig_deeper_nudge>"
    ```

    #### Research Recipe

    ```bash
    /codex:rescue "
    <task>
    Research options for migrating from REST to GraphQL in this codebase.
    </task>
    <structured_output_contract>
    Return: 1. observed facts  2. recommendation  3. tradeoffs  4. open questions
    </structured_output_contract>
    <grounding_rules>
    Back claims with references to inspected sources. Prefer primary sources.
    </grounding_rules>"
    ```

    ### Anti-Patterns to Avoid

    | Anti-Pattern | Problem | Better Approach |
    |-------------|---------|-----------------|
    | `"Take a look at this"` | Vague, no direction | Use `<task>` with concrete job description |
    | `"Investigate and report back"` | No output format | Add `<structured_output_contract>` with expected fields |
    | `"Debug this failure"` | No follow-through | Add `<default_follow_through_policy>` to keep going |
    | `"Think harder"` | Reasoning ≠ better contracts | Add `<verification_loop>` for quality |
    | Mixing review + fix + docs in one prompt | Too many jobs | Run review first, then fix, then docs separately |
    | `"Tell me exactly why production failed"` | Demands certainty | Add `<grounding_rules>` to separate facts from inference |

    !!! tip "Applying recipes to your delegation patterns"
        When delegating tasks via the [delegation patterns](#delegation-patterns) above, wrap your task description in the appropriate recipe. For example, the "Test Writing" pattern becomes much more reliable when you add `<completeness_contract>` (don't stop after happy path) and `<verification_loop>` (run the tests before finalizing).

??? warning "Review Gate (experimental)"

    ## Review Gate

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
