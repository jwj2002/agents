# Full Agent Prompts

Use these patterns for Codex, Claude, ChatGPT, or another agent that can inspect a repository, edit files, run commands, and report verification.

## Prompt Skeleton

```text
You are working in <repo/project>. I need you to <goal>.

Context:
- <business/product context>
- <current behavior or starting point>
- <important constraints>

Scope:
- Work in/around <files, modules, routes, components, commands, or subsystems if known>.
- Preserve unrelated user changes.
- Do not rewrite broad areas unless required to satisfy the goal.

Requirements:
- <functional requirement 1>
- <functional requirement 2>
- <edge case or non-functional requirement>

Engineering rules:
- Read the actual source before assuming APIs, schemas, enum values, component props, or command behavior.
- Follow existing project patterns.
- Add or update focused tests when behavior changes.
- Treat auth, permissions, migrations, secrets, and data-loss risk explicitly.

Verification:
- Run <narrow check>.
- Run <full relevant gate>.
- If any check cannot run, explain exactly why and what remains unverified.

Definition of done:
- <observable result>
- <tests/checks pass or risks reported>
- <handoff expectation: commit, PR, review only, patch only, etc.>
```

## Codex Notes

Codex prompts can assume an autonomous coding loop. Include explicit expectations for reading files, editing, running tests, preserving user work, and reporting blocked verification. If shipping is desired, say so directly.

Add when appropriate:

```text
Take this end to end in the current workspace. Implement the change, run the relevant checks, and summarize changed files plus verification.
```

## Claude Notes

Claude prompts benefit from an explicit role and artifact expectation. If using Claude as conductor, specify whether it should plan, orchestrate, create issue artifacts, or perform direct edits.

Add when appropriate:

```text
Use your normal project workflow. If this should be routed through planning/review agents, create the necessary artifacts; otherwise implement directly.
```

## ChatGPT Notes

When ChatGPT cannot access the repo, ask it to produce a patch plan, test matrix, or prompt for a local coding agent instead of pretending to inspect files.

Add when appropriate:

```text
If you cannot inspect the repository directly, ask for the relevant files or produce a local-agent prompt instead of inventing codebase details.
```
