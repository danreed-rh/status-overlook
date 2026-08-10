# Status Overlook

One local view of your **Jira** and **GitHub** work: what is tracked, what needs you, and what changed since you last looked.

Uses the `gh` and `acli` CLIs (prompts to install or log in when needed). Writes digests that humans and coding agents can both read.

## Capabilities

- Track assigned Jira issues and relevant GitHub PRs
- Classify items as actionable, pending, blocked, or done
- Emit `digest.md` + `digest.json`
- Optional scheduled refresh on Mac (`install-scheduler`)

## Out of scope for v1

- Slack, email, or chat integrations
- Writing back to Jira or GitHub (read and classify only)
- A full web dashboard
- Linux/Windows schedulers (Phase 5)

## Always out of scope

- Replacing Jira or GitHub as systems of record
- Hosting your data on a Status Overlook cloud service

## Install (dev)

```bash
cd status-overlook
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
status-overlook --version
```

## Quick start

```bash
status-overlook init          # probe gh/acli, write config.yaml
status-overlook doctor
status-overlook run
status-overlook show
status-overlook mark-read
```

### Mac scheduler (optional)

```bash
status-overlook install-scheduler --every 15m
status-overlook uninstall-scheduler
status-overlook uninstall --dry-run   # list what would be removed
status-overlook uninstall             # scheduler + Application Support/Caches/Logs
```

## CLI

```text
status-overlook init [--force] [--non-interactive]
status-overlook doctor [--skip-github] [--skip-jira]
status-overlook paths
status-overlook reconcile [--skip-github] [--skip-jira] [--dry-run]
status-overlook run [--skip-github] [--skip-jira] [--skip-reconcile]
status-overlook show [--store] [--since-read] [--section …]
status-overlook mark-read [--all] [ids…]
status-overlook install-scheduler [--every 15m]
status-overlook uninstall-scheduler [--dry-run]
status-overlook uninstall [--dry-run] [-y]
```

## Where files live (Mac defaults)

| Kind | Path |
|------|------|
| Config + track store | `~/Library/Application Support/status-overlook/` |
| Digests | `~/Library/Caches/status-overlook/` |
| Logs | `~/Library/Logs/status-overlook/` |
| LaunchAgent | `~/Library/LaunchAgents/dev.statusoverlook.sync.plist` |

`status-overlook paths` prints the resolved locations on your machine.

## License

Apache-2.0 — see `LICENSE` and `NOTICE`.
