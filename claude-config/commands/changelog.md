# PR Changelog

Update the project changelog from merged PRs.

## Instructions

Run the PR changelog agent to detect merged PRs and update:
- Project's CHANGELOG.md
- Obsidian vault changelog

Execute this command:

```bash
python3 ~/agents/pr-changelog/update_changelog.py
```

For a specific PR:

```bash
python3 ~/agents/pr-changelog/update_changelog.py --pr <number>
```

After running, report what was added to the changelog.
