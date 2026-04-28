---
paths: ["**"]
---

# GitHub Multi-Account Setup

This machine has two GitHub accounts configured via `gh auth`. Always ensure the correct account is active before any git/gh operations.

## Account Mapping

| GitHub Account | Used For | Git Email |
|---------------|----------|-----------|
| `jwj2002` | Personal projects | jasonwadejob@gmail.com |
| `jjob-spec` | Maison Financial projects | jason@maisonfinancial.com |

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
| `~/agents` | `jwj2002` | jwj2002/agents |

## Required Steps

1. **Before any git/gh operation**, run `gh auth status` to check the active account
2. **If wrong account is active**, run `gh auth switch -u <correct_account>`
3. **After cloning a jjob-spec repo**, always set:
   ```bash
   git config user.name "Jason Job"
   git config user.email "jason@maisonfinancial.com"
   ```
4. **For jwj2002 repos**, git email should be `jasonwadejob@gmail.com`

## Never

- Push to a jjob-spec repo while logged in as jwj2002 (or vice versa)
- Use global git config for email — always set per-repo for jjob-spec projects
