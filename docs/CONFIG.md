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
| Logs | `~/.local/state/status-overlook/log/` |
| Optional scheduler | `~/.config/systemd/user/status-overlook.sync.{service,timer}` |

`XDG_*` env vars override when set. `status-overlook paths` prints the resolved list.

### Windows

| Kind | Path |
|------|------|
| Config / store | `%LOCALAPPDATA%\status-overlook\` |
| Digests | `%LOCALAPPDATA%\status-overlook\Cache\` |
| Logs | `%LOCALAPPDATA%\status-overlook\Logs\` |
| Optional scheduler | Task Scheduler `StatusOverlook\Sync` (+ XML under `...\scheduler\`) |

## Schedulers

`status-overlook install-scheduler --every 15m` installs a **user** job that runs `status-overlook run`:

- macOS — LaunchAgent (your GUI session)
- Linux — systemd user timer. Timers run **while you are logged in**. To keep them after logout or at boot without a session: `loginctl enable-linger "$USER"`. No systemd (some WSL, Alpine) → use `run` / `serve` only.
- Windows — Task Scheduler with `InteractiveToken` (runs **while you are logged in**). If the task cannot find the binary, set Command to the full path from `where status-overlook`.

Example unit/plist/XML templates also live under [`contrib/`](../contrib/) (placeholders only — prefer the CLI). Off-hours behavior (below) applies to scheduler-triggered `run` as well as UI auto-refresh.

Second-machine checklist: [`SMOKE.md`](SMOKE.md).

## Working hours (quiet mode)

Optional `working_hours` in `config.yaml` limits when `status-overlook run` calls `gh` / `acli`, and when `serve` stays up.

**Defaults** (when the block is present or written by `init` for a **new** config):

| Field | Default |
|-------|---------|
| `enabled` | `true` (init asks in interactive mode; non-interactive new configs enable it) |
| `days` | Monday–Friday |
| `start` / `end` | `08:00` / `18:00` (end exclusive — 18:00 is off-hours) |
| `timezone` | System local (optional **IANA** name, e.g. `America/New_York` — not Windows `Eastern Standard Time`) |

**Existing installs** without a `working_hours` key stay disabled. Re-running `init --force` on those configs does **not** turn quiet hours on unless you opt in (interactive) — non-interactive overwrite keeps them off.

Invalid timezone or clock values fail **open** (`run` / `serve` still work) so a typo cannot lock you out.

```yaml
working_hours:
  enabled: true
  days: [mon, tue, wed, thu, fri]
  start: "08:00"
  end: "18:00"
```

| Command | Off-hours behavior |
|---------|-------------------|
| `status-overlook run` | Exits 0 immediately (no gh/acli) |
| `status-overlook run --force` | Runs anyway |
| `status-overlook serve` | Refuses to start |
| `status-overlook serve --ignore-working-hours` | Starts and stays up |
| `serve` (while running) | Shuts down at end of window / on weekends |

Reading digests (`show`, `/api/digest`) is always local — not gated.

## CLIs

| Tool | Role |
|------|------|
| `gh` | GitHub |
| `acli` | Jira |

If Refresh reports `Jira authentication failed`, run `acli jira auth status` and follow the login command in the UI. Some acli versions report an expired session as `failed to parse JQL` during search; the doctor checks authentication before attributing that error to a QA field.

## Timestamps (digest)

| Field | Meaning |
|-------|---------|
| `remote_updated_at` | Upstream updated time |
| `state_changed_at` | Last observed change in visible lifecycle, action, remote status, or displayed cue. Reason-only changes and no-op runs do not bump it. Renderers derive elapsed status age from this timestamp; it is not a remote history timestamp. |
| `last_read_at` | Last mark-read by you or an agent |

## Jira blocked detection

An issue is **blocked** if **any** of these is true:

1. **Status** name is in `status_blocked` (default: `Blocked`)
2. **Label** is in `blocked_labels` (default: `blocked`, case-insensitive)
3. **Flagged** impediment is set (Jira Software flag; providers map this to `flagged: true`)
4. **Issue link** *is blocked by* points at an issue that is **not** terminal (status category `done`, or status name in `status_done`). Resolved/Closed blockers do not keep the issue blocked. Outward *blocks* links are ignored (those mean *this* issue blocks someone else).

   Providers load links with `acli jira workitem view … --fields issuelinks` (acli **search** rejects `issuelinks`). The same view call loads `qa_contact_field` and `pr_link_field` — search also rejects `customfield_*`.

## Jira QA contact (Testing)

`jira.qa_contact_field` (e.g. `customfield_10470`) is required to discover tickets where you are **QA contact** but not assignee.

Each `run` asks Jira two questions:

1. Assignee — `assignee = currentUser()` and unresolved.
2. QA in Testing — QA field = you **and** status in `status_testing` (default: `Testing`). Skipped when `qa_contact_field` is empty.

Classification: Testing + QA contact → **actionable**. Testing + assignee only → **pending** (cue **Testing**).

## Jira Review + merged PR

When status is in `status_review` (default: `Review`, …), the assignee is you, and the **Git Pull Request** field (`pr_link_field`) points at a **merged** GitHub PR, classification is **actionable** (`jira_review_pr_merged`) instead of pending.

Meaning: code is in; you still need to add testing instructions and move to Testing, or resolve if testing is not required.

Probe uses `gh pr view` only for Review issues that have a parseable GitHub PR URL. Missing/unmerged/unknown PR → stay **pending**.

## Epics in digests / show

Jira items with issue type **Epic** show an `[Epic]` tag and sort to the **bottom** of Actionable / Pending / Blocked (still newest-first within the epic group). Recently done is unchanged. Requires a sync/enrich so `issue_type` is stored.

## Jira + PR grouping (show / digest)

Active Actionable / Pending / Blocked entries **collapse** linked Jira + GitHub PR pairs into one row:

1. **Pair** if Jira `pr_link` matches a tracked PR, or the PR summary contains a tracked Jira key.
2. **Section** = best action among members: `actionable` > `pending` > `blocked`.
3. **Primary** (key/url shown) = member with best action; tie-break prefers an **open** GitHub PR, else Jira.
4. **Secondary** appears as `↔ #8787` or `↔ RHOAIENG-76231`.

Recently done is not grouped. JSON digest keeps all items and adds `group_primary_id` / `linked_ids`.

## Roadmap (not in this release)

- **Deferred:** shared team multi-user board, ROSA/cluster hosting

## Local UI (`serve`)

`status-overlook serve [--port 8765] [--open]` starts a **localhost-only** page. Same store and digests as the CLI. Works on macOS, Linux, and Windows: it is HTML/CSS/JS over `http.server`, not a native app.

- **URL:** `http://127.0.0.1:8765/` — prefer this over `http://localhost:8765/` on Windows (IPv6 `localhost` can miss an IPv4 bind). `--host localhost` is rewritten to `127.0.0.1`.
- **Browsers:** current Chrome, Firefox, Edge, or Safari. The page follows the OS light/dark setting (`prefers-color-scheme`). Internet Explorer is not supported.
- **`--open`:** uses the OS default browser. If nothing opens (WSL without `wslview`, headless Linux), paste the printed URL.
- Views: Actionable, All active, **Everything** (active + recently done), Pending, Blocked, Recently done
- Source filter: Jira + GitHub / GitHub (PRs + Issues) / PRs / Issues / Jira
- **Refresh now** runs the full pipeline even outside working hours (`force`). Auto-refresh ticks **skip** off-hours and say so instead of pretending the store updated.
- OS scheduler updates digests on disk but does not refresh an open tab by itself.
- Mark all read
- Cue pills (next-step labels). Section headers name the bucket (Actionable / Pending / …).
- PR status labels in the UI translate raw tokens (for example, `open+ci_fail` → `Open · CI failing`). My Work shows linked keys together and one status age: the open PR’s current observed status age when present, otherwise the group primary’s. Each member retains its own `state_changed_at` in the UI payload and `digest.json`.
- The **Team review** tab (`/team`) is a separate, read-only view of team PRs with its own locally editable roster and cached results. It polls the local cache every minute to pick up scheduler updates. See [TEAM_REVIEW.md](TEAM_REVIEW.md).

Restart `serve` after Python or static-file changes. If the port is in use, the CLI prints that and suggests `--port`.

### GitHub Issues

Discovery uses `gh search issues --assignee=@me --state=open -- is:issue` (assignee only; not author). Pins: `pins.github_issues` → `github-issue:owner/repo#n`. PR pins stay under `pins.github` → `github-pr:…`. `skip_github` skips both PRs and Issues.

Agents should still use digest files / `show --plain`, not the browser UI.
