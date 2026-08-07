# Decision log (internal)

## Locked

| ID | Decision | Date |
|----|----------|------|
| D0–D5 | Name, repo, gh+acli, Apache-2.0, Mac paths, uninstall | 2026-08-07 |
| D1b | GitHub remote: https://github.com/danreed-rh/status-overlook | 2026-08-07 |

## Phase 1 classification (updated Gate 1)

| Topic | Rule |
|-------|------|
| Action states | `actionable` \| `pending` \| `blocked` \| `done` \| `ignore` |
| Jira Testing + QA contact | actionable |
| Jira Testing + assignee only | ignore (not actionable, not pending) |
| Jira blocked (any non-done status) | **blocked** |
| Jira Review + assignee | pending |
| Jira active + assignee | actionable |
| Jira **Epic** + assignee | **pending** until all children are terminal (status category `done`, or names in `status_done`); then **actionable**. Zero children ⇒ all done. |
| PR open + unresolved reviews or CI fail | actionable |
| PR open + otherwise involved | pending |
| PR linked Jira blocked | **blocked** |
| PR actionable labels | `lgtm` only (default) |
| Blocked detection | **Any of:** status in `status_blocked` (default `Blocked`), label in `blocked_labels` (default `blocked`), or Jira **Flagged** impediment |

## Open

| ID | Question | Gate |
|----|----------|------|
| Q3 | Done retention | 2 | **Default 7 days** — confirm at Gate 2 |
| Q2 | Blocked detection | 1 | **Done:** status + `blocked` label + Flagged |
| Q4 | Cross-link strategy | 3 |
| Q5 | Schedule interval | 4 |
| Q7 | Final docs cleanup | 5 |
