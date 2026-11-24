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
- Separate local **Team review** page for review-required PRs from a saved GitHub roster

## Out of scope for this release

- Slack, email, or chat integrations
- Writing back to Jira or GitHub (read and classify only)
- Shared multi-user boards or cluster hosting (deferred)
- Binding the UI off localhost / remote hosting
- Replacing your Mac/Linux/Windows user-domain paths with system-wide installs

## Always out of scope

- Replacing Jira or GitHub as systems of record
- Hosting your work data on a Status Overlook cloud service
- Requiring a remote server for personal digests (agent contract stays **local files**)

## Install

Requires **Python 3.10+**, plus [`gh`](https://cli.github.com/) and [`acli`](https://developer.atlassian.com/cloud/acli/) on your `PATH`.

### 1. GitHub CLI (`gh`)

| OS | Typical install |
|----|-----------------|
| macOS | `brew install gh` |
| Debian / Ubuntu | `sudo apt install gh` (or the [GitHub apt repo](https://github.com/cli/cli/blob/trunk/docs/install_linux.md)) |
| Fedora / RHEL | `sudo dnf install gh` |
| Windows | `winget install GitHub.cli` |

Then: `gh auth login`.

### 2. Atlassian CLI (`acli`)

Install from the [acli install guide](https://developer.atlassian.com/cloud/acli/guides/install-acli/). Put the binary on `PATH` (`~/.local/bin` on Linux; user PATH on Windows). Authenticate in your browser:

```bash
acli jira auth login --web
acli jira auth status
```

For API-token authentication instead, create a token at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens), save it to a private file, and run `acli jira auth login --site YOUR.atlassian.net --email YOU@example.com --token < token.txt`. `--token` reads standard input; `--site` belongs to `auth login`, not `auth status`.

### 3. Status Overlook

**pipx (recommended)**

```bash
pipx install git+https://github.com/danreed-rh/status-overlook.git
status-overlook --version
```

Windows PowerShell if `pipx` is missing:

```powershell
py -3 -m pip install --user pipx
py -3 -m pipx ensurepath
# Reopen the terminal, then:
pipx install git+https://github.com/danreed-rh/status-overlook.git
```

**uv**

```bash
uv tool install git+https://github.com/danreed-rh/status-overlook.git
```

**Dev checkout**

```bash
git clone https://github.com/danreed-rh/status-overlook.git
cd status-overlook
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
status-overlook --version
```

Upgrade later: `pipx upgrade status-overlook` or `uv tool upgrade status-overlook` (or reinstall from git). There is no PyPI package yet.

## Quick start

```bash
status-overlook init          # probe gh/acli, write config.yaml
status-overlook doctor
status-overlook run --force   # first sync (works outside quiet hours)
status-overlook show
status-overlook mark-read
status-overlook serve --open   # optional local UI (Chrome/Firefox/Edge/Safari)
```

`init` asks whether to enable weekday quiet hours (Mon–Fri 08:00–18:00 local). New non-interactive configs enable them. Off-hours, `run` no-ops unless `--force`, and `serve` needs `--ignore-working-hours`.

`show` uses color in a real terminal. Set `NO_COLOR=1` to disable. Prefer Windows Terminal over classic `cmd.exe`.

Open the UI at **`http://127.0.0.1:8765/`**. On Windows, `http://localhost:8765/` can hit IPv6 (`::1`) and miss a server bound to IPv4.

The **Team review** tab at `/team` shows two read-only GitHub queues for saved teammates: open, non-draft, review-required PRs with no GitHub assignee, and LGTM-labeled PRs still requiring review in repositories where your account has Maintain/Admin permission. The second queue does not claim GitHub requires a particular maintainer to approve. Add/remove GitHub usernames in its roster editor; the seven verified initial members are seeded locally on the owner machine. Regular `run`/UI Refresh updates this separate cache, even if the personal Jira work fails. Team fetch failures leave the personal digest and previous team results intact. See [team review design](docs/TEAM_REVIEW.md).

### Optional scheduler

```bash
status-overlook install-scheduler --every 15m
status-overlook uninstall-scheduler
status-overlook uninstall --dry-run
status-overlook uninstall             # scheduler + app data dirs
```

- **Linux:** `systemd --user` timers run while you are logged in. To keep syncing after logout: `loginctl enable-linger "$USER"`. Distros without systemd (some WSL, Alpine) can still use `run` / `serve`; skip the scheduler.
- **Windows:** the task uses InteractiveToken (runs while you are logged in). If it fails to start, set Command to the full path from `where status-overlook`.
- **macOS:** LaunchAgent (runs in your GUI session).

Uninstall does **not** remove the pipx/uv binary — use `pipx uninstall status-overlook` or `uv tool uninstall status-overlook`.

## CLI

```text
status-overlook init [--force] [--non-interactive]
status-overlook doctor [--skip-github] [--skip-jira]
status-overlook paths
status-overlook reconcile [--skip-github] [--skip-jira] [--dry-run]
status-overlook run [--skip-github] [--skip-jira] [--skip-reconcile] [--force]
status-overlook show [--store] [--since-read] [--section …] [--plain] [-v]
status-overlook mark-read [--all] [ids…]
status-overlook install-scheduler [--every 15m]
status-overlook uninstall-scheduler [--dry-run]
status-overlook uninstall [--dry-run] [-y]
status-overlook serve [--host 127.0.0.1] [--port 8765] [--open] [--ignore-working-hours]
```

### Local UI vs CLI vs scheduler

| Tool | Use when |
|------|----------|
| `show` / digest files | Terminal or **agents** (always prefer files for agents) |
| `serve` | Browser at `http://127.0.0.1:8765/` (same store as CLI). Needs a current Chrome, Firefox, Edge, or Safari. Follows the OS light/dark preference. |
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

Rendered items show elapsed time in their latest observed visible state. This age is derived from `state_changed_at`, resets when lifecycle, Jira/GitHub status, or Status Overlook’s displayed action/cue changes, and does not query remote history. `digest.json` exposes the timestamp for machine-readable use.

The browser shows readable PR status labels and right-aligned status ages. Raw `remote_status` tokens remain available in `digest.json` and the store.

**Implementing or extending this tool in Cursor:** start with [`docs/AGENT_CONTEXT.md`](docs/AGENT_CONTEXT.md) (architecture, decisions, phased history, pitfalls).

More detail: [`docs/CONFIG.md`](docs/CONFIG.md).

## License

Apache-2.0 — see `LICENSE` and `NOTICE`.
