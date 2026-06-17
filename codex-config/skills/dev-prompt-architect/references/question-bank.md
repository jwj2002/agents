# Question Bank

Use these questions selectively. Ask only what materially affects the prompt.

## Universal

- What should be true when the work is done?
- What is the current starting point: rough idea, bug, issue, spec, failing test, or existing code?
- Which repo, branch, product area, or subsystem should the agent work in?
- Is the desired output a plan, code patch, review, test plan, PR, issue comment, or handoff prompt?
- Are there stop gates such as human sign-off, production risk, release timing, or "PR only"?

## Implementation

- What user-visible behavior should change?
- Are there examples, screenshots, API payloads, or acceptance criteria?
- Should the agent add tests, update docs, wire UI, create migrations, or handle deployment config?
- What existing behavior must remain unchanged?

## Bug Fix

- What are the exact repro steps?
- What is expected versus actual behavior?
- Are there logs, stack traces, request IDs, screenshots, or failing tests?
- How should the agent prove the fix?

## Review

- Should the review focus on correctness, security, architecture, performance, tests, maintainability, or all of them?
- Should findings be blocking only, or include medium/low-priority improvement notes?
- What changed code, branch, PR, commit, or diff should be reviewed?

## Refactor

- What behavior must remain identical?
- What is the reason for the refactor: readability, duplication, performance, architecture, API cleanup, or testability?
- Are public APIs, schemas, migrations, or generated files off limits?

## Architecture Or Spec

- Who will implement this, and in what repo/tooling?
- What decisions are already made versus open?
- What are the risky unknowns?
- Should the output be build-ready instructions, an ADR, an implementation plan, or a critique?
