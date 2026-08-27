# Status Overlook

One **local** view of your Jira and GitHub work: what is tracked, what needs you, and what changed since you last looked.

Uses the `gh` and `acli` CLIs (prompts to install or log in when needed). Writes digests that **humans and coding agents** can both read from disk.

## What it can do

- Track assigned Jira issues, GitHub PRs, and assigned GitHub Issues
- Classify items as actionable, pending, blocked, or done
- Group linked Jira + PR + Issue sets into one digest row
- Emit `digest.md` and `digest.json` under your user cache directory
- Optional OS user scheduler: macOS LaunchAgent, Linux systemd user timer, Windows Task Scheduler
- Terminal `show` and markdown digests for agents (`show --plain`)
- Optional **local** web UI (`status-overlook serve` — localhost only)

## Out of scope for this release

- Slack, email, or chat integrations
- Writing back to Jira or GitHub (read and classify only)
- Team multi-user boards or shared cluster hosting (deferred)
- Binding the UI off localhost / remote hosting
- Replacing your Mac/Linux/Windows user-domain paths with system-wide installs

## Always out of scope

- Replacing Jira or GitHub as systems of record
- Hosting your work data on a Status Overlook cloud service
- Requiring a remote server for personal digests (agent contract stays **local files**)

## Install

Requires Python 3.10+, plus [`gh`](https://cli.github.com/) and [`acli`](https://developer.atlassian.com/cloud/acli/) on your `PATH`.

### pipx (recommended)

```bash
pipx install git+https://github.com/danreed-rh/status-overlook.git
status-overlook --version
```

### uv

```bash
uv tool install git+https://github.com/danreed-rh/status-overlook.git
```

### Dev checkout

```bash
git clone https://github.com/danreed-rh/status-overlook.git
cd status-overlook
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
status-overlook --version
```

Upgrade later: `pipx upgrade status-overlook` or `uv tool upgrade status-overlook` (or reinstall from git).

## Quick start

```bash
status-overlook init          # probe gh/acli, write config.yaml
status-overlook doctor
status-overlook run
status-overlook show
status-overlook mark-read
status-overlook serve --open   # optional local UI
```

### Optional scheduler

```bash
status-overlook install-scheduler --every 15m
status-overlook uninstall-scheduler
status-overlook uninstall --dry-run
status-overlook uninstall             # scheduler + app data dirs
```

Uninstall does **not** remove the pipx/uv binary — use `pipx uninstall status-overlook` or `uv tool uninstall status-overlook`.

## CLI

```text
status-overlook init [--force] [--non-interactive]
status-overlook doctor [--skip-github] [--skip-jira]
status-overlook paths
status-overlook reconcile [--skip-github] [--skip-jira] [--dry-run]
status-overlook run [--skip-github] [--skip-jira] [--skip-reconcile]
status-overlook show [--store] [--since-read] [--section …] [--plain] [-v]
status-overlook mark-read [--all] [ids…]
status-overlook install-scheduler [--every 15m]
status-overlook uninstall-scheduler [--dry-run]
status-overlook uninstall [--dry-run] [-y]
status-overlook serve [--host 127.0.0.1] [--port 8765] [--open]
```

### Local UI vs CLI vs scheduler

| Tool | Use when |
|------|----------|
| `show` / digest files | Terminal or **agents** (always prefer files for agents) |
| `serve` | Browser: Actionable / All active / Everything, source filters; auto-refresh reloads the list after each run |
| `install-scheduler` | Background refresh without keeping the UI open |

## Where files live

`status-overlook paths` prints resolved locations. Defaults:

| OS | Config / store | Digests | Logs | Scheduler |
|----|----------------|---------|------|-----------|
| macOS | `~/Library/Application Support/status-overlook/` | `~/Library/Caches/status-overlook/` | `~/Library/Logs/status-overlook/` | LaunchAgent `dev.statusoverlook.sync` |
| Linux | `~/.config/` + `~/.local/share/` | `~/.cache/status-overlook/` | `~/.local/state/.../log/` | systemd user timer `status-overlook.sync.timer` |
| Windows | `%LOCALAPPDATA%\status-overlook\` | `...\Cache\` | `...\Logs\` | Task `StatusOverlook\Sync` |

`XDG_*` env vars override Linux/macOS-style paths when set.

## Agents

Coding agents should read **local** digest files (or run `status-overlook show --plain`), not a remote UI. See [`skills/status-overlook/SKILL.md`](skills/status-overlook/SKILL.md).

**Implementing or extending this tool in Cursor:** start with [`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md) (architecture, decisions, phased history, pitfalls).

More detail: [`docs/CONFIG.md`](docs/CONFIG.md).

## License

Apache-2.0 — see `LICENSE` and `NOTICE`.
