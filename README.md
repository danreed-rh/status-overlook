# Status Overlook

One local view of your **Jira** and **GitHub** work: what is tracked, what needs you, and what changed since you last looked.

Uses the `gh` and `acli` CLIs (prompts to install or log in when needed). Writes digests that humans and coding agents can both read.

## Capabilities (planned)

- Track assigned Jira issues and relevant GitHub PRs
- Classify items as actionable, pending, or done
- Emit `digest.md` + `digest.json`
- Optional scheduled refresh on Mac (Linux/Windows later)

## Out of scope for v1

- Slack, email, or chat integrations
- Writing back to Jira or GitHub (read and classify only)
- A full web dashboard

## Always out of scope

- Replacing Jira or GitHub as systems of record
- Hosting your data on a Status Overlook cloud service

## Status

Early skeleton (config shape and package layout). Sync and classify come next.

## Install (dev)

```bash
cd status-overlook
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
status-overlook --version
```

## Planned CLI

```text
status-overlook init
status-overlook doctor
status-overlook paths          # print where files live
status-overlook reconcile
status-overlook run
status-overlook show [--since-read]
status-overlook mark-read
status-overlook install-scheduler --every 15m
status-overlook uninstall-scheduler
status-overlook uninstall      # remove scheduler + app data (with confirm)
```

## Where files live (Mac defaults)

Per Apple’s guidance for user-level apps — nothing under `/Library` or system paths unless you choose that later:

| Kind | Path |
|------|------|
| Config + track store | `~/Library/Application Support/status-overlook/` |
| Digests / caches | `~/Library/Caches/status-overlook/` |
| Logs | `~/Library/Logs/status-overlook/` |
| Scheduler (optional) | `~/Library/LaunchAgents/dev.statusoverlook.sync.plist` |

Linux uses XDG (`~/.config`, `~/.local/share`, `~/.cache`). Override with `XDG_*` where applicable.

`status-overlook paths` and `uninstall` will list or remove these locations so the tool stays easy to find and remove.

## License

Apache License 2.0 — free to use and modify; redistributions must keep attribution (copyright / NOTICE).
