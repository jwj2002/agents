# Agentic Engineering — Workflow Extraction Prompt

> **Purpose**: Paste this into a Claude Code session on any machine to extract your complete development workflow, patterns, and practices. The output feeds into training documentation for Agentic Engineering best practices.
>
> **Usage**: Open Claude Code in your home directory and paste the prompt below.

---

## The Prompt

```
I'm building training documentation for "Agentic Engineering" — best practices for AI-assisted software development using tools like Claude Code, Codex, and multi-agent workflows.

I need you to analyze my complete development environment and produce a structured report. This is a READ-ONLY research task — do not modify any files.

## What to Analyze

### 1. AI Agent Configuration
Explore and document:
- `~/agents/` — Full repo structure, README, all config files
- `~/.claude/` — Settings, hooks, commands, agents, rules, skills, memory files
- `~/.codex/` — If exists, rules, skills, settings
- Any MCP server configurations
- Any plugins or extensions enabled
- Keybindings or custom shortcuts

For each config file found, document:
- What it does
- Why it exists (what problem it solves)
- How it connects to the broader workflow

### 2. Project Portfolio
For every directory in `~/projects/`:
- Read CLAUDE.md (if exists) — capture the full content
- Read .claude/ directory (rules, memory, context, settings)
- Read README.md, pyproject.toml, package.json, requirements.txt
- Check for .github/ workflows, Dockerfiles, docker-compose files
- Run `git log --oneline -15` to see recent work patterns
- Identify tech stack, architecture patterns, testing strategy

### 3. Hooks & Lifecycle Management
For every hook script found:
- What event triggers it
- What it does (summarize the logic)
- What problem it solves
- How it connects to other hooks (data flow)

### 4. Slash Commands & Skills
For every command and skill definition:
- Name and purpose
- When to use it
- What agents or tools it invokes
- Input/output format

### 5. Agent Definitions (Orchestrate Workflow)
For every agent .md file:
- Role in the pipeline
- Required inputs (predecessor artifacts)
- Output format and target length
- Key rules and constraints
- Version number

### 6. Rules & Patterns
For every rule file:
- Loading strategy (always vs conditional)
- What failures it prevents
- Specific examples of the pattern

### 7. Memory & Learning System
Look for:
- patterns.md, patterns-critical.md, patterns-full.md
- metrics.jsonl, failures.jsonl
- Any postmortem files
- PERSISTENT_STATE.yaml files
Document the learning loop: how failures become patterns become agent improvements.

### 8. Cross-Machine Setup
Document:
- How config syncs across machines (symlinks, git, cloud)
- What's shared vs local-only
- Bootstrap process for new machines
- Update workflow for config changes

## Output Format

Produce a single document organized into these sections:

### Part 1: Environment Profile
- Machine info, OS, shell, key tools
- AI models used (and when/why each one)
- MCP servers and what they provide

### Part 2: Configuration Architecture
- How global config (`~/agents/`) relates to per-project config (`.claude/`)
- Symlink strategy
- Conditional rule loading
- Hook lifecycle (diagram the data flow)

### Part 3: The Orchestrate Workflow
- Full pipeline with agent roles
- Complexity classification (TRIVIAL/SIMPLE/COMPLEX)
- Parallel execution patterns
- Artifact naming and validation chain
- CONTRACT as mandatory for fullstack

### Part 4: Command Reference
- Every slash command, grouped by category
- When to use each one
- Common workflows (daily, weekly, per-feature)

### Part 5: Self-Learning System
- Metrics schema and what gets tracked
- Failure taxonomy (root cause codes)
- Pattern extraction process (/learn)
- Agent update process (/agent-update)
- Validation (/learn --validate)

### Part 6: Project Patterns
- Common architecture across projects (layered pattern, etc.)
- Shared technology choices and why
- Git workflow and branch strategy
- Testing strategy
- Documentation standards (CLAUDE.md best practices)

### Part 7: Failure Prevention
- Top failure patterns with frequency data
- Specific prevention techniques for each
- How rules encode these preventions
- The "read before assuming" principle

### Part 8: Lessons Learned
- What worked and why
- What failed and what was changed
- Key insights about working with AI agents
- Anti-patterns to avoid

### Part 9: Quick Reference
- New machine setup (step by step)
- New project setup (step by step)
- Daily workflow checklist
- Weekly maintenance checklist

Write the output to `~/agents/docs/AGENTIC_ENGINEERING_WORKFLOW.md`

Be thorough. Read every file. This document will be the foundation for training materials on how to effectively engineer with AI agents.
```

---

## After Extraction: Building the Training Documentation

Once you have the extraction from both machines (WSL + personal), compare them and create the final training guide:

```
Review these two workflow extraction documents:
1. ~/agents/docs/AGENTIC_ENGINEERING_WORKFLOW.md (this machine)
2. [paste or reference the WSL extraction]

Synthesize them into a training curriculum for "Agentic Engineering" organized as:

## Module 1: Foundations
- What is Agentic Engineering
- How AI coding agents work (context windows, tools, hooks)
- The shift from "prompt engineering" to "agent engineering"

## Module 2: Environment Setup
- Portable configuration architecture
- The ~/agents/ repository pattern
- Symlink-based deployment
- Multi-machine synchronization

## Module 3: The Orchestrate Pattern
- Issue-driven development with agents
- Agent pipeline design (MAP → PLAN → PATCH → PROVE)
- Complexity classification and routing
- Artifact chains and validation gates
- Parallel execution strategies

## Module 4: Writing Effective CLAUDE.md Files
- What to include (with examples from real projects)
- Forbidden patterns and guardrails
- Architecture documentation that agents can act on
- The "read before assuming" principle

## Module 5: Hooks & Lifecycle Management
- Session continuity (PreCompact → SessionStart)
- Anti-rationalization (Stop hook)
- State extraction and restoration
- Custom hook development

## Module 6: The Self-Learning Loop
- Structured failure recording
- Root cause taxonomy
- Pattern extraction and validation
- Agent version correlation
- Continuous improvement cadence

## Module 7: Rules Engineering
- Always-loaded vs conditional rules
- Token budget optimization
- Encoding failure patterns as prevention rules
- Project-specific overrides

## Module 8: Multi-Agent Coordination
- Agent role separation
- CONTRACT pattern for fullstack work
- Artifact naming and validation chains
- Parallel execution with scope boundaries
- Swarm-aware behavior

## Module 9: Common Failure Patterns
- ENUM_VALUE, COMPONENT_API, VERIFICATION_GAP
- Why AI agents make these mistakes
- Systematic prevention techniques
- The learning feedback loop

## Module 10: Scaling & Operations
- Cross-project pattern sharing
- Metrics dashboards and trend analysis
- Agent performance optimization
- When to use /quick vs /orchestrate
- Integration with external tools (Obsidian, GitHub, Codex)

Write to ~/agents/docs/AGENTIC_ENGINEERING_TRAINING.md

Target audience: Senior developers who are new to AI-assisted development
and want to build a systematic, repeatable workflow — not just chat with an AI.
```

---

## Notes

- Run the extraction prompt first on your personal Mac, then compare with the WSL extraction already at `~/projects/vaultiq-snow/docs/DEVELOPMENT_WORKFLOW.md`
- The synthesis step merges both into a teachable curriculum
- Consider adding real examples (anonymized) from your projects as case studies in each module
