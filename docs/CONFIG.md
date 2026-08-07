# Configuration

Prefer `status-overlook init` when it exists: it should probe `gh` and `acli` and write most identity fields for you. [`config.example.yaml`](../config.example.yaml) stays minimal on purpose.

## Default paths

### macOS (Apple conventions)

| Kind | Path |
|------|------|
| Config + track store | `~/Library/Application Support/status-overlook/` |
| Digests / caches | `~/Library/Caches/status-overlook/` |
| Logs | `~/Library/Logs/status-overlook/` |
| Optional scheduler | `~/Library/LaunchAgents/dev.statusoverlook.sync.plist` |

User-domain only — no `/Library` system agents in v1.

### Linux

| Kind | Path |
|------|------|
| Config | `~/.config/status-overlook/` |
| Data | `~/.local/share/status-overlook/` |
| Cache | `~/.cache/status-overlook/` |

`XDG_*` env vars override when set. `status-overlook paths` prints the resolved list.

## CLIs

| Tool | Role |
|------|------|
| `gh` | GitHub |
| `acli` | Jira |

## Timestamps (digest)

| Field | Meaning |
|-------|---------|
| `remote_updated_at` | Upstream updated time |
| `state_changed_at` | Last change to our derived state (not bumped on no-op runs) |
| `last_read_at` | Last mark-read by you or an agent |
