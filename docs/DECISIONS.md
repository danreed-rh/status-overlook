# Decision log (internal)

## Locked

| ID | Decision | Date |
|----|----------|------|
| D0 | Name: Status Overlook / `status-overlook` | 2026-08-07 |
| D1 | Repo: https://github.com/danreed-rh/status-overlook | 2026-08-07 |
| D2 | POC: `gh` + `acli` | 2026-08-07 |
| D3 | License: Apache-2.0 (+ NOTICE) | 2026-08-07 |
| D4 | Mac paths under `~/Library/...`; Linux XDG | 2026-08-07 |
| D5 | User-level only; `paths` + uninstall planned | 2026-08-07 |

## Phase 1 draft defaults (awaiting Gate 1)

| Topic | Default |
|-------|---------|
| Testing + QA contact | actionable + track |
| Testing + assignee only | actionable + track |
| Testing + neither | untracked |
| Review + assignee | pending |
| Active + assignee + not blocked | actionable |
| Active/Review + blocked | pending |
| PR `/lgtm` or `lgtm` | actionable |
| Linked Jira blocked | pending (overrides LGTM) |
| Author draft PR | actionable |
| Author open non-draft | pending |
| Assignee open non-draft | actionable |

## Open

| ID | Question | Gate |
|----|----------|------|
| Q1 | Confirm Testing / QA rules above | 1 |
| Q1b | Confirm `actionable_labels`: `lgtm`, `/lgtm` (case-insensitive) | 1 |
| Q2 | How to set `blocked` from Jira (status vs Flagged vs label) — Phase 2 | 1–2 |
| Q3 | Done retention | 2 |
| Q4 | Cross-link strategy | 3 |
| Q5 | Schedule interval | 4 |
| Q6 | Optional `ghd` | 5 |
| Q7 | Final docs cleanup | 5 |
