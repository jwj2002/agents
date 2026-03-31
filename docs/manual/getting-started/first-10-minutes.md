# Your First 10 Minutes

**Go from installation to your first AI-generated pull request.**

!!! tip
    No prior knowledge of agents, pipelines, or orchestration needed. We'll explain everything as we go.

---

## Step 1: Verify Installation (1 minute)

Open your terminal and run:

```bash
claude --version
ls ~/.claude/agents/    # Should show agent files
ls ~/.claude/commands/  # Should show command files
```

!!! success "Expected output"
    You should see a version number (e.g., `1.x.x`) and a list of files in both directories. The `agents/` folder contains the AI specialists that do the work. The `commands/` folder contains the slash commands you'll use to talk to them.

If either directory is empty or missing, head back to the [Installation](installation.md) page and re-run `install.sh`.

---

## Step 2: Open Your Project (1 minute)

Navigate to any project that has a GitHub repo and launch Claude Code:

```bash
cd ~/projects/myapp    # Your project directory
claude                 # Launch Claude Code
```

!!! success "Expected output"
    Claude Code starts an interactive session in your terminal, ready for instructions.

Claude Code reads your project's `CLAUDE.md` for project-specific instructions. If you don't have one, that's fine — everything works without it.

!!! tip
    Want to customize how Claude handles your project? See [Project Setup](project-setup.md) to learn about writing a `CLAUDE.md`.

---

## Step 3: Try a Quick Fix (2 minutes)

Let's start simple. Ask Claude to fix something obvious:

```
You: Fix the typo in README.md where it says "dependancies"
```

Claude identifies this as a one-file, obvious fix — and makes the change directly:

```
I found the typo on line 14 of README.md. Changed "dependancies" → "dependencies".
```

!!! success "Expected output"
    Claude edits the file and reports what it changed. No fanfare, no pipeline — just a fix.

!!! info "What just happened?"
    Claude assessed the task complexity and chose the simplest approach: a direct edit. For small, obvious changes, this is all you need. The full pipeline is reserved for bigger work.

---

## Step 4: Create a GitHub Issue (1 minute)

Now let's try something bigger. First, create an issue in your repo:

```bash
gh issue create --title "Add health check endpoint" \
  --body "Add a GET /health endpoint that returns {status: 'ok'}"
```

Note the issue number (e.g., `#42`). You'll use it in the next step.

!!! success "Expected output"
    GitHub confirms the issue was created and prints its URL and number.

---

## Step 5: Run the Full Pipeline (5 minutes)

This is where things get interesting. Tell Claude to handle the entire issue:

```
You: /orchestrate 42
```

Here's what happens, step by step:

1. Claude **investigates** your codebase to understand existing patterns, file structure, and conventions.
2. It creates a **plan** — which files to modify, what code to add, how it fits with what's already there.
3. It **implements** the changes, following your project's patterns and style.
4. It **verifies** the implementation — runs linting, checks for placeholder code, and confirms tests pass.
5. It reports the result.

```
Issue #42 classified as: SIMPLE (backend)

  Investigating codebase...              done
  Planning implementation...             done
  Implementing changes...   2 files modified
  Verifying implementation...        all passed

Workflow complete for issue #42
Next: /pr 42 to create pull request
```

!!! success "You just ran a multi-agent pipeline"
    Behind the scenes, three specialized AI agents handled this: one investigated your code, one implemented the changes, and one verified the result. Each produced a report (a markdown file in `.agents/outputs/`) that the next agent read before starting its own work.

!!! info "What just happened?"
    The `/orchestrate` command is the main entry point for non-trivial work. It breaks a task into phases, assigns each phase to a specialist, and chains their outputs together. You described *what* you wanted; the system figured out *how*.

---

## Step 6: Create the Pull Request (1 minute)

Now turn that work into a PR:

```
You: /pr
```

Claude creates a pull request with a summary, test plan, and a link back to issue `#42`.

!!! success "Expected output"
    ```
    Created PR #43: feat: add health check endpoint
    https://github.com/you/myapp/pull/43
    ```

---

## What You Just Did

```
You described what you wanted
    |
    v
Claude investigated your codebase       (MAP-PLAN phase)
    |
    v
Claude wrote the code                   (PATCH phase)
    |
    v
Claude verified it works                (PROVE phase)
    |
    v
You got a pull request
```

The three phases — MAP-PLAN, PATCH, and PROVE — are the core workflow. Each is handled by a dedicated agent with a specific job. For bigger tasks, additional phases (like CONTRACT for cross-stack work) are added automatically.

---

## What's Next?

!!! tip "Learn about the agents"
    Each phase is handled by a specialist with its own rules and checks. See the [Agent Overview](../agents/overview.md) to learn what each one does and when it's called.

!!! tip "Run issues in parallel"
    Got multiple independent issues? You can run them simultaneously with `--parallel`. See [Parallel Execution](../workflow/parallel.md) to learn how.

!!! tip "Set up cross-model review"
    Add a second AI model as a code reviewer for extra safety. See [Codex Plugin](../integrations/codex-plugin.md) to get started.
