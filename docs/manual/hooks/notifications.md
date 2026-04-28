# Notifications

`notify_completion.py` sends a macOS Notification Center alert when a Claude Code session finishes. This lets you step away from the terminal and get notified when the agent completes its work.

## How It Works

The hook runs on the `Stop` event, after `verify_completion.py`. It follows this sequence:

1. **Platform guard** -- Check `sys.platform`. If not `darwin` (macOS), exit 0 immediately. The hook is a no-op on Linux, WSL, and Windows.
2. **Read context** -- Call `state_manager.get_active_work()` to get the current issue number, phase, and last action.
3. **Build message** -- Construct a notification message from the context.
4. **Send notification** -- Execute `osascript -e 'display notification ...'` via subprocess.
5. **Exit 0** -- Always exit successfully. Notification failure must never block a session.

## Notification Content

The message adapts to available context:

| Context Available | Notification Message |
|-------------------|---------------------|
| Phase and issue number | `PATCH finished for issue #184` |
| Last action only | `Session complete -- Implemented backend models` |
| No context | `Session complete` |

The notification title is always `Claude Code`.

## Sound Alert

The notification plays the `Glass` sound via the AppleScript `sound name "Glass"` parameter. This is a built-in macOS alert sound that is distinct enough to notice without being intrusive.

```applescript
display notification "PATCH finished for issue #184" with title "Claude Code" sound name "Glass"
```

!!! success "What the macOS notification looks like"
    A standard Notification Center banner appears in the top-right corner with:

    - **Title**: Claude Code
    - **Body**: PATCH finished for issue #184
    - **Sound**: Glass chime

## iPhone Relay via Handoff

macOS Notification Center notifications automatically forward to paired iPhones through Apple's Handoff / Continuity features. No additional configuration is needed beyond having Handoff enabled on both devices and being signed into the same Apple ID.

This means you can start a long-running orchestrate pipeline, leave your desk, and receive a notification on your phone when the session finishes.

!!! tip "iPhone Handoff setup"
    1. On your Mac: System Settings > General > AirDrop & Handoff > enable Handoff
    2. On your iPhone: Settings > General > AirPlay & Continuity > enable Handoff
    3. Both devices must be signed into the same Apple ID and on the same Wi-Fi network
    4. Ensure Notification Center is allowed for Terminal (or your terminal app) in System Settings > Notifications

## AppleScript Injection Sanitization

Since notification text is embedded in an AppleScript string, the `sanitize()` function prevents injection:

```python
def sanitize(text: str) -> str:
    # Strip control characters
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    # Escape backslashes, then double quotes
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    # Truncate to 200 characters
    return text[:200]
```

!!! warning "Why Sanitization Matters"
    Without sanitization, a malicious or unexpected string in the state file (e.g., containing `"`) could break the AppleScript command or, in theory, execute arbitrary AppleScript. The `sanitize()` function strips control characters, escapes quotes and backslashes, and truncates to 200 characters.

## Pairing with --parallel

When running multiple issues in parallel (each in its own terminal tab with `--parallel`), each session sends its own notification on completion. The notification includes the issue number and phase, so you can tell which session finished:

```
+-- Terminal Tab 1 --+    +-- Terminal Tab 2 --+
| /orchestrate 184   |    | /orchestrate 185   |
|   --parallel        |    |   --parallel        |
+--------+------------+    +--------+------------+
         |                          |
    [completes]                [completes]
         |                          |
  "PATCH finished            "PROVE finished
   for issue #184"            for issue #185"
```

## Error Handling

The hook is designed to never interfere with the session:

- `osascript` call has a 5-second timeout
- All exceptions are caught and logged to `~/.claude/hooks.log`
- The hook always exits 0 regardless of whether the notification was sent
- If `state_manager` import fails, the hook falls back to a generic "Session complete" message

## Configuration

The hook is registered as the second Stop hook in `settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/hooks/verify_completion.py"},
          {"type": "command", "command": "python3 ~/.claude/hooks/notify_completion.py"}
        ]
      }
    ]
  }
}
```

Order matters: `verify_completion.py` runs first so its advisory warning appears before `notify_completion.py` sends the alert.
