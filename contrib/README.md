# Manual scheduler templates

Prefer `status-overlook install-scheduler --every 15m` on a machine where the CLI is installed.

These files are examples for review or offline install:

| Path | Platform |
|------|----------|
| `macos/dev.statusoverlook.sync.plist.example` | macOS LaunchAgent |
| `systemd/status-overlook.sync.service` + `.timer` | Linux user systemd |
| `windows/StatusOverlook.Sync.xml` | Windows Task Scheduler |

Replace the program path with your `status-overlook` binary (`which status-overlook` / `where status-overlook`).
