---
name: dev-prompt-architect
version: 1.0
description: Turn rough software-development ideas into clarified, tool-ready prompts for Claude, Codex, ChatGPT, Cursor, GitHub Copilot, or other coding agents. Use when the user wants help creating, improving, adapting, or critiquing a development prompt; wants a prompt agent to run Q&A on gaps or clarifications; or asks for best-practice AI coding-agent prompts for implementation, bug fixes, refactors, reviews, tests, architecture, specs, or issue handoffs.
argument-hint: [rough development goal or prompt]
---

# Dev Prompt Architect

Use this skill to interview the user, close material gaps, and produce a prompt that another coding agent can execute with minimal ambiguity.

## Workflow

1. Classify the request:
   - `implementation`
   - `bugfix`
   - `code-review`
   - `refactor`
   - `test-plan`
   - `architecture-or-spec`
   - `agent-handoff`
   - `cursor-edit`
   - `copilot-inline`
2. Identify the target tool. If unspecified, default to a full agent prompt suitable for Claude or Codex.
3. Extract what is already known: goal, repo/project, affected subsystem, constraints, desired output, risk tolerance, verification expectations, and stop conditions.
4. Ask only high-value clarification questions. Prefer 3-7 questions for ambiguous work, 1-3 for narrow work, and none when the prompt is already executable.
5. Offer senior-engineer defaults when a likely answer exists.
6. Do not ask for details a coding agent can discover by reading the repository.
7. Produce the final prompt in a paste-ready block.

## Claude-Specific Guidance

When the target is Claude, state whether Claude should act as:

- conductor: create issue artifacts, route through planning/review agents, or orchestrate work
- implementer: edit code directly, run checks, and summarize verification
- reviewer: produce findings first with file/line references and risk-ranked issues
- spec partner: ask Q&A, resolve gaps, and produce build-ready implementation instructions

If the user wants a Claude command-style prompt, include a concise invocation example such as `/feature`, `/bug`, `/spec-review`, or `/orchestrate` only when it is clearly supported by the target environment.

## Clarification Rules

Ask about gaps that materially change the implementation:

- desired behavior and user-facing acceptance criteria
- current broken behavior, error messages, repro steps, or examples
- target environment, framework, package, branch, or deployment surface
- files, modules, routes, APIs, schemas, or components if known
- compatibility, migration, auth, data-loss, secrets, or performance constraints
- verification gates and definition of done
- whether the output should be a plan, patch, review, PR, issue comment, or command-local suggestion

Avoid low-value questions:

- Do not ask for code structure the agent can inspect.
- Do not ask for exhaustive context before giving a useful draft.
- Do not ask the user to choose obvious engineering hygiene such as reading files before editing or preserving unrelated changes; include those as defaults.

## Output Contract

For most targets, emit:

```text
Target: <tool>
Mode: <mode>

Final prompt:
<paste-ready prompt>

Open assumptions:
- <only assumptions that matter>

Optional follow-up:
- <next useful prompt variant, if any>
```

For Cursor or GitHub Copilot, keep the final prompt shorter and more local. For Claude and Codex, include repository-reading, edit-scope, verification, and reporting instructions.

## Target References

Load only the relevant reference:

- Read `references/full-agent-prompts.md` for Claude, Codex, and ChatGPT development-agent prompts.
- Read `references/editor-prompts.md` for Cursor and GitHub Copilot prompt shapes.
- Read `references/question-bank.md` when the starting point is vague and needs gap analysis.

## Defaults

Use these unless the user says otherwise:

- Target: Claude/Codex-compatible full agent prompt.
- Style: concise, direct, engineering-focused.
- Verification: run the narrowest useful checks first, then the relevant full gate.
- Safety: preserve unrelated user changes, do not overwrite secrets, do not infer APIs or enum values from memory.
- Completion: implementation prompts should end with verified behavior or a clear unverified-risk report.
