# Systemd Timer Setup

The timer polls every 60 seconds for new Claude Code sessions. Only sessions
modified since the last run are processed (zero wasted API calls when idle).

## Automatic Install

```bash
python -m obsidian_agent --install-systemd
```

## Manual Install

```bash
cp systemd/*.service systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now obsidian-agent-watcher.timer
```

## Check Status

```bash
systemctl --user status obsidian-agent-watcher.timer
systemctl --user status obsidian-agent-watcher.service
journalctl --user -u obsidian-agent-watcher.service -f
```

## Cron (Rollups)

```bash
python -m obsidian_agent --install-cron
```

Installs:
- Nightly daily rollup at 11:00 PM
- Weekly rollup Sunday 11:30 PM
- Monthly rollup last day of month 11:30 PM
