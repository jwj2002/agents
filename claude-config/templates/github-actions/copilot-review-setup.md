# GitHub Copilot Automatic Code Review Setup

No API keys required — uses your existing GitHub Copilot subscription.

## Prerequisites

- GitHub Copilot Pro, Pro+, Business, or Enterprise plan
- Repository admin access

## Setup (per repo)

### Option A: Automatic on all PRs

1. Go to **Settings → Copilot → Code Review**
2. Enable **Automatic code review**
3. Done — Copilot reviews every PR automatically

### Option B: Required reviewer via Rulesets

1. Go to **Settings → Rules → Rulesets → New ruleset**
2. Add branch rule targeting your default branch
3. Under **Require pull request reviews**, add `copilot-code-review` as a required reviewer
4. Save

### Option C: Request per-PR (manual)

On any PR, click **Reviewers → Copilot** to request a one-off review.

## What it does

- Reviews full architectural context (not just diff)
- Posts inline comments on specific lines
- Focuses on correctness, security, and architectural integrity
- Agentic architecture: pulls relevant code, directory structure, and references as needed

## References

- [Using Copilot code review](https://docs.github.com/copilot/using-github-copilot/code-review/using-copilot-code-review)
- [Configuring automatic review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/configure-automatic-review)
