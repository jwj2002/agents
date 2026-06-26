---
paths: ["**/.github/**"]
---

# GitHub Multi-Account Setup

This machine has two GitHub accounts configured via `gh auth`. Always ensure the correct account is active before any git/gh operations.

## Account Mapping

| GitHub Account | Used For | Git Author Name | Git Email |
|---------------|----------|-----------------|-----------|
| `jwj2002` | Personal projects | `jwj2002` | jasonwadejob@gmail.com |
| `jjob-spec` | Maison Financial / VitalAI work | `jjob-spec` | jjob@vital-enterprises.com |

> Verified from commit history (2026-06-09): jjob-spec commits as
> `jjob-spec <jjob@vital-enterprises.com>` and jwj2002 as
> `jwj2002 <jasonwadejob@gmail.com>`. The author NAME is the literal login,
> not "Jason Job". (Earlier versions of this file wrongly listed
> `jason@maisonfinancial.com` for jjob-spec.)

## Project → Account Mapping

| Project Path | GitHub Account | Repo |
|-------------|---------------|------|
| `~/projects/buddy` | `jwj2002` | jwj2002/meeting-buddy |
| `~/projects/mymoney-dev` | `jwj2002` | jwj2002/mymoney-dev |
| `~/projects/OpenJarvis` | `jwj2002` | open-jarvis/OpenJarvis |
| `~/projects/safe174th` | `jwj2002` | jwj2002/safe174th |
| `~/projects/temper` | `jwj2002` | jwj2002/temper |
| `~/projects/fastapi-architect-agent` | `jwj2002` | jwj2002/fastapi-architect-agent |
| `~/projects/social_media_poster` | `jjob-spec` | jjob-spec/social-media-poster |
| `~/projects/ai-channels` | `jjob-spec` (this laptop, collaborator) | jwj2002/ai-channels |
| `~/agents` | `jwj2002` | jwj2002/agents |

> `ai-channels` is cross-account: repo is **owned by jwj2002**, but the personal
> laptop commits as jwj2002 while this (work) laptop commits as a **jjob-spec
> collaborator**. The work-laptop clone uses a username-qualified remote
> (`https://jjob-spec@github.com/jwj2002/ai-channels.git`) so the credential
> store resolves the jjob-spec token regardless of the active gh account.

## Required Steps

1. **Before any git/gh operation**, run `gh auth status` to check the active account
2. **If wrong account is active**, run `gh auth switch -u <correct_account>`
3. **After cloning a jjob-spec repo**, always set (per-repo, not global):
   ```bash
   git config user.name "jjob-spec"
   git config user.email "jjob@vital-enterprises.com"
   ```
4. **For jwj2002 repos**, set `user.name "jwj2002"` and `user.email "jasonwadejob@gmail.com"`

## Never

- Push to a jjob-spec repo while logged in as jwj2002 (or vice versa)
- Use global git config for email — always set per-repo for jjob-spec projects
