# Team review page — UX and software design

## Short version

`/team` is a distinct, localhost-only view of PRs authored by a saved list of GitHub teammates. It shows **unassigned PRs requiring review** and **LGTM PRs still requiring review on repositories you maintain**. It never requests reviews or approves a PR. The existing My Work digest and classifier remain separate.

## Evidence and decisions

- Razzmatazz Kanban is Jira board `11803`; `acli jira board search --filter 119995 --json` confirms its saved filter. Matching board ticket keys to GitHub PR authors established the seven owner-approved initial usernames. This was a one-time roster discovery; Jira assignees alone cannot prove GitHub team membership.
- `gh search prs --review=required` locates candidate PRs, and `gh pr view --json reviewDecision,assignees,isDraft,labels,author,state` verifies each. GitHub reports `REVIEW_REQUIRED` when a required review is outstanding. It does **not** establish which role must approve.
- `gh api repos/OWNER/REPO --jq .permissions` reports the signed-in account’s `maintain`/`admin` role. Only the LGTM queue requires that access; the unassigned queue covers all visible repositories. Draft PRs are excluded.
- An LGTM PR that is also unassigned appears once in the LGTM queue with an Unassigned badge. The age on each card is local time observed in its current queue; no GitHub history is fetched.

## UX design

- **Navigation and coherence:** `src/status_overlook/web/header.html` is included in the initial HTML response for both routes, giving My Work and `/team` the same fixed-layout brand, page tabs, Refresh button and status line without a JavaScript-insertion layout shift. `web/header.js` owns the shared Refresh behavior. Both pages use shared violet/teal tokens, surfaces, typography and card spacing in `web/style.css`. Page toolbars hold each page’s heading and details; My Work’s View/Source/Unread/Auto-refresh filters live below the global header. The Team page keeps violet/teal queue accents and two distinct columns so its identity remains apparent after scrolling past navigation.
- **Queues:** “Unassigned” explains `REVIEW_REQUIRED` and no GitHub assignee. “LGTM · required review” explains the current user's repo Maintain/Admin role. Cards identify the author, repo/PR number, linked title, review signal, optional Unassigned badge and queue age (`<1d`, `1d`, …). Narrow screens stack the columns.
- **Roster:** an inline Edit roster panel adds/removes validated GitHub usernames immediately. New members appear after the next full Refresh or scheduled run. Removing a member hides their cached PRs immediately. With no members, the page offers setup instructions.
- **Freshness:** the page shows last successful check and a warning if the latest team fetch failed. It polls only the local `/api/team` cache each minute; the shared global Refresh action uses the same pipeline on either page. My Work retains its view/source filters in its subheader.

## Software design and actions

1. **Persist separately:** `src/status_overlook/team.py` stores the manually edited roster in `team_members.json` and the PR snapshot in `team_queue.json` under `paths.data_dir()`. Both files are private and atomically replaced. The latter stores `entered_at` per PR/category, last successful update and last error. `GET /api/team` filters cached rows against the current roster.
2. **Select PRs:** `src/status_overlook/providers/team_github.py` searches required-review PRs by validated author, then checks each PR's current state, draft flag, author, assignees, labels and review decision. For LGTM, it checks Maintain/Admin on the base repo once per repo per refresh. Invalid or truncated searches fail closed and preserve the prior snapshot.
3. **Refresh independently:** `src/status_overlook/run.py` attempts team PR discovery after the personal pipeline, even if the personal Jira work fails. It skips team queries with `--skip-github` or an empty roster. Team errors do not fail a completed personal refresh, and personal errors do not prevent a GitHub-only team update. The Team page reports the two outcomes separately.
4. **Expose locally:** `src/status_overlook/serve.py` serves `/team`, `GET /api/team`, and `POST /api/team/members` (`{action: "add"|"remove", login`), and includes the shared header fragment in both initial page responses. `src/status_overlook/web/header.js` owns shared Refresh polling and announces completion to each page. All rendering escapes GitHub text; the server remains localhost-only.

## Check

- `.venv/bin/pytest tests/ -q` covers provider selection, category precedence, permission checks, roster edits, age preservation/reset, stale-cache behavior and API routes with mocked GitHub responses.
- `node --check src/status_overlook/web/team.js` and `git diff --check` pass.
- After the seven-member roster is seeded, load `/team` at desktop and mobile sizes, review candidate cards, try roster add/remove and Refresh, and confirm My Work still shows the original personal data.
