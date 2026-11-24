# Decision log (internal)

## Locked

| ID | Decision | Date |
|----|----------|------|
| D0–D5 | Name, repo, gh+acli, Apache-2.0, Mac paths, uninstall | 2026-08-07 |
| D1b | GitHub remote: https://github.com/danreed-rh/status-overlook | 2026-08-07 |

## Observed status age

- Reuse `state_changed_at` as the start of the latest **visible** state observed by a successful refresh. Do not add a separate age timer or query remote history.
- Reset on lifecycle, action, remote-status, or displayed cue changes. Ignore reason-only changes when the displayed state remains the same.
- This is an observation timestamp, not the exact transition time from Jira or GitHub. Changes that occur and revert between refreshes are not observable and do not reset it.
- Derive duration at render time. For linked Jira/PR items, retain independent timestamps; terminal and Markdown display each member’s age.
- My Work alone shows linked keys on the same line and a single status age. While a grouped PR is open (including draft), the displayed status and age come from that PR even if Jira is the action-ranked primary. Otherwise use the primary’s status and age. Keep each item’s timestamp in the store and API; terminal and Markdown continue to show independent ages.

## Local Team review

- The user approved the Razzmatazz Kanban board (11803, saved filter 119995) solely to seed an initial roster of seven verified GitHub usernames. Future refreshes use the saved local roster; they do not query Jira for membership.
- Track open, non-draft, `REVIEW_REQUIRED` PRs by saved author across all repositories visible to this GitHub account. Unassigned means **no GitHub assignees**. LGTM requires the `lgtm` label, outstanding required review, and current user Maintain/Admin access to the base repo. An overlapping PR appears once in LGTM, with an Unassigned badge.
- Keep the team queue separate from the personal store/digests. Show locally observed time in the current queue; changing queues resets the clock. Team fetch failure preserves the last successful queue, with a visible error.

## Phase 1 classification (updated Gate 1)

| Topic | Rule |
|-------|------|
| Action states | `actionable` \| `pending` \| `blocked` \| `done` \| `ignore` |
| Jira Testing + QA contact | actionable |
| Jira Testing + assignee only | **pending** (`jira_testing_assignee_only`) — waiting on QA; cue **Testing** |
| Jira blocked (any non-done status) | **blocked** |
| Jira Review + assignee | **pending** (waiting on code review) |
| Jira Review + assignee + linked PR **merged** | **actionable** (`jira_review_pr_merged`) — add testing notes / move to Testing, or resolve if no testing |
| Jira active + assignee | actionable |
| Jira **Epic** + assignee | **pending** until all children are terminal (status category `done`, or names in `status_done`); then **actionable**. Zero children ⇒ all done. |
| PR open + unresolved reviews or CI fail | actionable |
| PR open + unresolved **inline review threads** | **actionable** for author (`github_unresolved_reviews`) — not only when `reviewDecision=CHANGES_REQUESTED`; any open thread keeps the PR actionable until all are resolved |
| PR open + otherwise involved | pending |
| PR linked Jira blocked | **blocked** |
| PR `lgtm` label | **actionable** for **author** (ready to merge); not for assignee-only |
| PR assignee + user `/lgtm` comment or `lgtm` label | **pending** (`github_assignee_lgtm`) — signed off, waiting |
| PR assignee + unresolved own review threads | **pending** (`github_assignee_waiting_on_author`); probe failure → **pending** (`github_assignee_threads_unknown`); when resolved → **actionable** (`github_assignee_to_review`) |
| Jira key / QA field hygiene | Keys must match `PROJ-123`; QA field must be `customfield_<digits>`; unsafe status chars rejected |
| IGNORE vs reconcile | `action=ignore` stays `lifecycle=done` while still in discovery (no reactivate); omitted from Recently done |
| PR assignee (not author) otherwise | **actionable** — needs review / re-review |
| PR actionable labels | `lgtm` only (default) |
| Blocked detection | **Any of:** status in `status_blocked` (default `Blocked`), label in `blocked_labels` (default `blocked`), Jira **Flagged** impediment, or **is blocked by** link to an **unresolved** (non-terminal) issue |
| Show/digest Jira+PR grouping | Linked Jira+PR appear **once** in Actionable/Pending/Blocked. Pair via Jira `pr_link` or Jira key in PR title. Section = best action (`actionable` > `pending` > `blocked`). Primary = best-action member (open PR preferred over Jira when tied). Secondary shown as `↔ …`. Recently done ungrouped. |
| Next-action / blocked cues | Display-only labels derived at present time from `reasons` (not new `action` states; not stored). Closed ids: `fix_ci`, `address_review`, `merge`, `review`, `test`, `follow_up`, `develop`, `wait_author`, `signed_off`, `wait_pr`, `wait_children`, `wait_review`, `wait_test`, `waiting`, `blocked_by`, `flagged`, `jira_blocked`, `blocked_status`, `blocked_label`. First matching reason in priority order wins. Group cue = primary. Unknown / done / ignore → no cue. |
| GitHub Issues | Discover `gh search issues --assignee=@me … is:issue` only (not author). Store id `github-issue:owner/repo#n`, source `github_issue`. PRs use `github-pr:…` / `github_pr` (legacy `github:` / `github` migrate on load). Closed→done; blocked label/Jira→blocked; open linked PR→pending; merged linked PR→actionable; else assignee open→actionable. Grouping also pairs Issue↔PR↔Jira via `pr_link`, PR `linked_issue_ids`, title Jira keys. |

## Open

| ID | Question | Gate |
|----|----------|------|
| Q3 | Done retention | 2 | **Default 7 days** — confirm at Gate 2 |
| Q2 | Blocked detection | 1 | **Done:** status + `blocked` label + Flagged + unresolved is-blocked-by |
| Q4 | Cross-link strategy | 3 | **Done:** digest/show grouping via `pr_link` + title Jira keys |
| Q5 | Schedule interval | 4 | **Done:** default 15m; Linux/Windows schedulers in 0.1.0 |
| Q7 | Final docs cleanup | 5 | **Done:** README three buckets + P6/deferred notes |
| Q6 | Optional `ghd` provider | 5 | Deferred |
