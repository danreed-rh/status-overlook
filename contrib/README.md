# Manual scheduler templates

Prefer `status-overlook install-scheduler --every 15m` on a machine where the CLI is already installed. That command writes PATH and the binary location for **this** computer.

These files are examples for review or offline install. They are **not** dumps from a developer Mac.

| Path | Platform |
|------|----------|
| `macos/dev.statusoverlook.sync.plist.example` | macOS LaunchAgent |
| `systemd/status-overlook.sync.service` + `.timer` | Linux user systemd |
| `windows/StatusOverlook.Sync.xml` | Windows Task Scheduler |

## Replace placeholders

1. Set the program path to your binary (`which status-overlook` / `command -v status-overlook` / `where status-overlook`).
2. On macOS, replace `/Users/YOU/...` log paths with your home directory.
3. On Linux, `%h/.local/bin` in the example unit expands to your home. Enable lingering if the timer should run after logout: `loginctl enable-linger "$USER"`.
4. On Windows, replace `C:\Path\To\status-overlook.exe` with the full path from `where status-overlook`. The example includes `<Duration>P365D</Duration>` (required next to `Interval`). The task runs while you are logged in (`InteractiveToken`). The CLI installer wraps `cmd.exe` so `PATH` includes Python/`gh`/`acli`.
