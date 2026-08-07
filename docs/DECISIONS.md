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
| PR open + unresolved reviews or CI fail | actionable |
| PR open + otherwise involved | pending |
| PR linked Jira blocked | **blocked** |
| PR actionable labels | `lgtm` only (default) |
| Blocked detection (Razzmatazz) | **Awaiting confirm** — evidence points to Jira **Flagged** (impediment); see Gate 1 prompt |

## Open

| ID | Question | Gate |
|----|----------|------|
| Q2 | Confirm blocked = Flagged (impediment) for Razzmatazz board 11803 | 1 |
| Q3 | Done retention | 2 |
| Q4 | Cross-link strategy | 3 |
| Q5 | Schedule interval | 4 |
| Q7 | Final docs cleanup | 5 |
