---
name: status-overlook
description: >-
  Read Status Overlook local digests (digest.md / digest.json) for actionable,
  pending, blocked, and done Jira/GitHub work. Use when the user asks about
  their work status, morning triage, what's actionable, or Status Overlook
  output. Prefer local files or `status-overlook show --plain` — never assume
  a remote or cluster UI. Do not use for creating Jira or sending Slack.
---

# Status Overlook (local digests)

Personal CLI digests of Jira + GitHub work. **Agent contract = local files** (or the CLI). There is no team/cluster UI in scope.

**Implementing this tool?** You are likely in the wrong skill — use [docs/AGENT_CONTEXT.md](../../docs/AGENT_CONTEXT.md) or `.cursor/skills/status-overlook-dev/` in the status-overlook repo.

## When to use

- What is actionable / pending / blocked for me?
- Morning or status triage that should use cached Status Overlook output
- Before live `acli` / `gh` scans for the same personal queue

## When not to use

- Creating or transitioning Jira issues
- Slack / email send
- Team-wide boards or ROSA-hosted views (deferred; not available)

## Locate digests

Run (or ask the user to run):

```bash
status-overlook paths
```

Typical locations:

| OS | Digests |
|----|---------|
| macOS | `~/Library/Caches/status-overlook/digest.md` and `digest.json` |
| Linux | `~/.cache/status-overlook/digest.md` (or `$XDG_CACHE_HOME/...`) |
| Windows | `%LOCALAPPDATA%\status-overlook\Cache\digest.md` |

Prefer **`digest.json`** for structured reads; **`digest.md`** for human-oriented sections.

There is an optional local browser UI (`status-overlook serve`) for humans. **Do not** use it as the agent data path — keep reading files / `show --plain`.

## Commands

```bash
status-overlook run              # refresh store + digests (needs gh/acli)
status-overlook show --plain     # markdown to stdout (same shape as digest.md)
status-overlook show --since-read
status-overlook show --section actionable
status-overlook mark-read --all
```

If digests are stale and network is allowed, run `status-overlook run` then re-read files. Do not invent ticket state.

## Interpreting output

- Sections: Actionable, Pending, Blocked, Recently done
- Linked Jira+PR pairs appear **once**; primary key is the actionable side; secondary as `↔ …`
- `●` / `unread` means `state_changed_at` after last `mark-read`
- `state_changed_at` is the last successfully observed visible-state change, not the exact Jira/GitHub transition time. It also drives the rendered “in status for” age; reason-only changes do not reset it.
- Linked Jira/PR items have independent `state_changed_at` values. Use the timestamp in `digest.json` for machine-readable status age; rendered durations are snapshots.
- Epics may show `[Epic]` and sort lower in a section
- `cue` on `digest.json` items (`id` / `label` / `kind`) is the next-action or blocked reason; `reasons` remains the machine audit trail. Prefer `cue.id` when summarizing what to do.

## Install skill

Copy or symlink this folder into your Cursor skills path (e.g. `~/.agents/skills/status-overlook` or a project `.cursor/skills/`).
