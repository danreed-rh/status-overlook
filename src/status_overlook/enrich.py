"""Enrich tracked items from gh/acli, classify, update fingerprints."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass

from status_overlook.classify_github import classify_github
from status_overlook.classify_github_issue import classify_github_issue
from status_overlook.classify_jira import classify_jira, is_jira_blocked
from status_overlook.config import AppConfig
from status_overlook.jira_ids import is_jira_key
from status_overlook.models import (
    ActionState,
    ClassifyConfig,
    GitHubIssueSnapshot,
    GitHubPrSnapshot,
    JiraIssueSnapshot,
)
from status_overlook.store import TrackStore, TrackedItem, _iso, _utcnow

_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
# Prow/ODH style approval comment; not the label name alone
_LGTM_COMMENT_RE = re.compile(r"(?m)(?:^|\s)/lgtm\b", re.IGNORECASE)
_FIXES_ISSUE_RE = re.compile(
    r"(?i)\b(?:fixes|closes|resolves)\s+(?:[a-z0-9_.-]+/[a-z0-9_.-]+)?#(\d+)\b"
)


def _body_has_slash_lgtm(body: str) -> bool:
    return bool(_LGTM_COMMENT_RE.search(body or ""))


def _user_gave_lgtm(
    data: dict,
    *,
    me: str,
    assignee_is_user: bool,
    labels: tuple[str, ...],
    actionable_labels: tuple[str, ...],
    label_insensitive: bool,
) -> bool:
    """True if this user posted /lgtm or (as assignee) the PR has an lgtm-style label."""
    for comment in data.get("comments") or []:
        author = ((comment.get("author") or {}).get("login") or "").casefold()
        if author == me and _body_has_slash_lgtm(str(comment.get("body") or "")):
            return True
    for review in data.get("reviews") or []:
        author = ((review.get("author") or {}).get("login") or "").casefold()
        if author == me and _body_has_slash_lgtm(str(review.get("body") or "")):
            return True
    if assignee_is_user:
        if label_insensitive:
            have = {x.casefold() for x in labels}
            if any(w.casefold() in have for w in actionable_labels):
                return True
        elif any(w in labels for w in actionable_labels):
            return True
    return False


@dataclass
class Identity:
    github_login: str
    jira_account_id: str = ""


def _run_json(cmd: list[str]) -> object:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    return json.loads(proc.stdout or "null")


def resolve_identity(cfg: AppConfig) -> Identity:
    login = cfg.github_login.strip()
    if not login:
        proc = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "gh api user failed").strip())
        login = (proc.stdout or "").strip().strip('"')
    account_id = cfg.jira_account_id.strip()
    if not account_id:
        try:
            rows = _run_json(
                [
                    "acli",
                    "jira",
                    "workitem",
                    "search",
                    "--jql",
                    "assignee = currentUser() AND resolution = EMPTY",
                    "--fields",
                    "assignee",
                    "--limit",
                    "1",
                    "--json",
                ]
            )
            if isinstance(rows, list) and rows:
                assignee = (rows[0].get("fields") or {}).get("assignee") or {}
                account_id = str(assignee.get("accountId") or "")
        except RuntimeError:
            account_id = ""
    return Identity(github_login=login, jira_account_id=account_id)


def state_fingerprint(
    *,
    action: str,
    lifecycle: str,
    remote_status: str,
    blocked: bool,
    reasons: list[str] | tuple[str, ...],
) -> str:
    payload = "|".join(
        [
            action,
            lifecycle,
            remote_status,
            "1" if blocked else "0",
            ",".join(sorted(reasons)),
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _ci_failed(rollup: list[dict] | None) -> bool:
    if not rollup:
        return False
    bad = {"FAILURE", "ERROR", "TIMED_OUT", "STARTUP_FAILURE", "CANCELLED"}
    for item in rollup:
        conclusion = (item.get("conclusion") or "").upper()
        state = (item.get("state") or "").upper()
        if conclusion in bad or state in {"FAILURE", "ERROR"}:
            return True
    return False


def normalize_github_pr_state(raw_state: str, merged_at: object) -> tuple[str, bool]:
    """Map gh PR state to (snap_state open|closed, merged).

    ``gh`` returns OPEN | CLOSED | MERGED. MERGED must not be treated as open.
    """
    state = (raw_state or "open").casefold()
    merged = bool(merged_at) or state == "merged"
    if merged or state == "closed":
        return "closed", merged
    return "open", False


def github_remote_status(snap: GitHubPrSnapshot) -> str:
    """Human-facing remote status for digests / fingerprints."""
    if snap.merged:
        return "merged"
    status = "draft" if snap.draft else snap.state
    if snap.ci_failed:
        status = f"{status}+ci_fail"
    if snap.has_unresolved_reviews:
        status = f"{status}+unresolved_threads"
    if snap.assignee_unresolved_threads is True:
        status = f"{status}+awaiting_author"
    return status


def probe_pr_review_threads(
    repo: str, number: int, me: str
) -> tuple[bool | None, bool | None]:
    """Return ``(any_unresolved, my_started_unresolved)``.

    Each flag is True/False on success, or None if the GraphQL probe failed.
    ``my_started_unresolved`` is True when ``me`` authored the first comment on
    at least one unresolved thread (assignee-waiting-on-author signal).
    """
    if "/" not in repo:
        return False, False
    owner, name = repo.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){"
        "pullRequest(number:$number){"
        "reviewThreads(first:100){"
        "nodes{isResolved comments(first:1){nodes{author{login}}}}"
        "}}}}"
    )
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-f",
            f"owner={owner}",
            "-f",
            f"name={name}",
            "-F",
            f"number={number}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None, None
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None, None
    if payload.get("errors"):
        return None, None
    pr = ((payload.get("data") or {}).get("repository") or {}).get("pullRequest")
    if pr is None:
        return None, None
    nodes = (pr.get("reviewThreads") or {}).get("nodes") or []
    me_cf = me.casefold()
    any_unresolved = False
    mine = False
    for thread in nodes:
        if thread.get("isResolved"):
            continue
        any_unresolved = True
        comments = ((thread.get("comments") or {}).get("nodes")) or []
        if not comments:
            continue
        author = ((comments[0].get("author") or {}).get("login") or "").casefold()
        if author == me_cf:
            mine = True
    return any_unresolved, mine


def assignee_has_unresolved_review_threads(
    repo: str, number: int, me: str
) -> bool | None:
    """True if ``me`` started unresolved threads; False if none; None if probe failed."""
    _any, mine = probe_pr_review_threads(repo, number, me)
    if _any is None:
        return None
    return mine


def enrich_github_pr(
    item: TrackedItem,
    identity: Identity,
    cfg: AppConfig | None = None,
) -> tuple[GitHubPrSnapshot, str, str, list[str]]:
    # key is org/repo#n
    if "#" not in item.key:
        raise ValueError(f"bad github key: {item.key}")
    classify_cfg = (cfg.classify_config() if cfg else ClassifyConfig())
    repo, num_s = item.key.rsplit("#", 1)
    json_fields = (
        "number,state,isDraft,mergedAt,author,assignees,labels,reviewDecision,"
        "statusCheckRollup,title,url,body,comments,reviews,closingIssuesReferences"
    )
    try:
        data = _run_json(
            [
                "gh",
                "pr",
                "view",
                num_s,
                "--repo",
                repo,
                "--json",
                json_fields,
            ]
        )
    except RuntimeError:
        # Older gh may lack closingIssuesReferences
        data = _run_json(
            [
                "gh",
                "pr",
                "view",
                num_s,
                "--repo",
                repo,
                "--json",
                "number,state,isDraft,mergedAt,author,assignees,labels,reviewDecision,"
                "statusCheckRollup,title,url,body,comments,reviews",
            ]
        )
    if not isinstance(data, dict):
        raise RuntimeError(f"gh pr view returned non-object JSON for {item.key}")
    author = ((data.get("author") or {}).get("login") or "").casefold()
    assignees = {
        (a.get("login") or "").casefold() for a in (data.get("assignees") or [])
    }
    me = identity.github_login.casefold()
    labels = tuple(x.get("name") or "" for x in (data.get("labels") or []))
    review = (data.get("reviewDecision") or "").upper()
    snap_state, merged = normalize_github_pr_state(
        str(data.get("state") or "open"), data.get("mergedAt")
    )
    assignee_is_user = me in assignees
    any_unresolved, my_unresolved = probe_pr_review_threads(
        repo, int(data.get("number") or num_s), me
    )
    unresolved_threads: bool | None = False
    if assignee_is_user and author != me:
        unresolved_threads = my_unresolved if any_unresolved is not None else None
    # Author (and anyone) needs action while inline review threads remain open.
    # reviewDecision alone misses REVIEW_REQUIRED with unresolved comments.
    has_unresolved_reviews = (
        review == "CHANGES_REQUESTED" or any_unresolved is True
    )
    linked_issue_ids = _pr_linked_issue_ids(repo, data)
    return GitHubPrSnapshot(
        repo=repo,
        number=int(data.get("number") or num_s),
        state=snap_state,
        merged=merged,
        draft=bool(data.get("isDraft")),
        author_is_user=author == me,
        assignee_is_user=assignee_is_user,
        labels=labels,
        has_unresolved_reviews=has_unresolved_reviews,
        ci_failed=_ci_failed(data.get("statusCheckRollup")),
        linked_jira_blocked=False,  # filled after jira map known
        user_gave_lgtm=_user_gave_lgtm(
            data,
            me=me,
            assignee_is_user=assignee_is_user,
            labels=labels,
            actionable_labels=classify_cfg.actionable_labels,
            label_insensitive=classify_cfg.label_match_case_insensitive,
        ),
        assignee_unresolved_threads=unresolved_threads,
    ), str(data.get("title") or item.summary), str(data.get("url") or item.url), linked_issue_ids


def _pr_linked_issue_ids(repo: str, data: dict) -> list[str]:
    """Store ids for issues this PR closes/links."""
    ids: list[str] = []
    seen: set[str] = set()
    for ref in data.get("closingIssuesReferences") or []:
        number = ref.get("number")
        if number is None:
            continue
        iid = f"github-issue:{repo}#{int(number)}"
        if iid not in seen:
            seen.add(iid)
            ids.append(iid)
    body = str(data.get("body") or "")
    for match in _FIXES_ISSUE_RE.finditer(body):
        iid = f"github-issue:{repo}#{int(match.group(1))}"
        if iid not in seen:
            seen.add(iid)
            ids.append(iid)
    return ids


def _issue_linked_prs(repo: str, number: int) -> list[dict] | None:
    """Best-effort linked PRs via GraphQL. None = probe failed; [] = none found."""
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    query = """
    query($owner:String!,$name:String!,$number:Int!) {
      repository(owner:$owner, name:$name) {
        issue(number:$number) {
          timelineItems(last: 40, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT]) {
            nodes {
              __typename
              ... on CrossReferencedEvent {
                source {
                  ... on PullRequest {
                    number
                    url
                    state
                    merged
                  }
                }
              }
              ... on ConnectedEvent {
                subject {
                  ... on PullRequest {
                    number
                    url
                    state
                    merged
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    proc = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if payload.get("errors"):
        return None
    issue = ((payload.get("data") or {}).get("repository") or {}).get("issue")
    if issue is None:
        return None
    nodes = ((issue.get("timelineItems") or {}).get("nodes")) or []
    prs: dict[int, dict] = {}
    for node in nodes:
        pr = None
        if node.get("__typename") == "CrossReferencedEvent":
            pr = node.get("source")
        elif node.get("__typename") == "ConnectedEvent":
            pr = node.get("subject")
        if not isinstance(pr, dict) or pr.get("number") is None:
            continue
        n = int(pr["number"])
        prs[n] = {
            "number": n,
            "url": str(pr.get("url") or f"https://github.com/{repo}/pull/{n}"),
            "state": str(pr.get("state") or "").upper(),
            "merged": bool(pr.get("merged")),
        }
    return list(prs.values())


def enrich_github_issue(
    item: TrackedItem,
    identity: Identity,
) -> tuple[GitHubIssueSnapshot, str, str]:
    """Enrich a GitHub Issue. key is org/repo#n."""
    if "#" not in item.key:
        raise ValueError(f"bad github_issue key: {item.key}")
    repo, num_s = item.key.rsplit("#", 1)
    number = int(num_s)
    data = _run_json(
        [
            "gh",
            "issue",
            "view",
            num_s,
            "--repo",
            repo,
            "--json",
            "number,state,title,url,assignees,labels",
        ]
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"gh issue view returned non-object JSON for {item.key}")
    me = identity.github_login.casefold()
    assignees = {
        (a.get("login") or "").casefold() for a in (data.get("assignees") or [])
    }
    labels = tuple(x.get("name") or "" for x in (data.get("labels") or []))
    state = str(data.get("state") or "OPEN").casefold()
    if state == "open":
        snap_state = "open"
    else:
        snap_state = "closed"

    linked = _issue_linked_prs(repo, number)
    linked_pr_open = False
    linked_pr_merged: bool | None = None
    pr_link: str | None = None
    if linked is None:
        linked_pr_merged = None
    elif linked:
        open_prs = [
            p
            for p in linked
            if str(p.get("state") or "").upper() == "OPEN" and not p.get("merged")
        ]
        merged_prs = [p for p in linked if p.get("merged")]
        linked_pr_open = bool(open_prs)
        linked_pr_merged = bool(merged_prs) and not open_prs
        if open_prs:
            pr_link = str(open_prs[0].get("url") or "") or None
        elif merged_prs:
            pr_link = str(merged_prs[0].get("url") or "") or None
    else:
        linked_pr_merged = False

    return GitHubIssueSnapshot(
        repo=repo,
        number=int(data.get("number") or number),
        state=snap_state,
        assignee_is_user=me in assignees,
        labels=labels,
        linked_pr_open=linked_pr_open,
        linked_pr_merged=linked_pr_merged,
        linked_jira_blocked=False,
        pr_link=pr_link,
    ), str(data.get("title") or item.summary), str(data.get("url") or item.url)


_ACLI_FIELD_NOT_ALLOWED_RE = re.compile(
    r"field '([^']+)' is not allowed", re.IGNORECASE
)


def _jira_search_fields() -> str:
    # acli search rejects `issuelinks` and `customfield_*`; those load via view.
    return "key,summary,status,assignee,labels,issuetype,flagged"


def _parse_acli_disallowed_field(err: str) -> str | None:
    m = _ACLI_FIELD_NOT_ALLOWED_RE.search(err or "")
    return m.group(1) if m else None


def _acli_workitem_search(*, jql: str, fields: str, limit: int) -> list:
    """Search with --fields; drop any field acli rejects and retry."""
    remaining = [part.strip() for part in fields.split(",") if part.strip()]
    last_err = "acli failed"
    while remaining:
        cmd = [
            "acli",
            "jira",
            "workitem",
            "search",
            "--jql",
            jql,
            "--fields",
            ",".join(remaining),
            "--limit",
            str(limit),
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            rows = json.loads(proc.stdout or "[]")
            if not isinstance(rows, list):
                raise RuntimeError(f"unexpected acli JSON: {type(rows)}")
            return rows
        last_err = (proc.stderr or proc.stdout or "acli failed").strip()
        bad = _parse_acli_disallowed_field(last_err)
        if not bad:
            raise RuntimeError(last_err)
        nxt = [f for f in remaining if f.casefold() != bad.casefold()]
        if len(nxt) == len(remaining):
            raise RuntimeError(last_err)
        print(f"Warning: acli search rejected {bad!r}; retrying without it")
        remaining = nxt
    raise RuntimeError(last_err)


def _jira_view_field_names(cfg: AppConfig) -> list[str]:
    names = ["issuelinks"]
    if cfg.jira_qa_contact_field:
        names.append(cfg.jira_qa_contact_field)
    if cfg.jira_pr_link_field:
        names.append(cfg.jira_pr_link_field)
    return names


def _qa_contact_is_user(value: object, account_id: str) -> bool:
    if not account_id:
        return False
    if isinstance(value, dict):
        qa_id = str(value.get("accountId") or "")
        return bool(qa_id) and qa_id == account_id
    if isinstance(value, list) and value and isinstance(value[0], dict):
        qa_id = str(value[0].get("accountId") or "")
        return bool(qa_id) and qa_id == account_id
    return False


def _status_is_terminal(status_obj: object, cfg: ClassifyConfig) -> bool:
    """True if child is at end of lifecycle (category done, or name in status_done)."""
    if not isinstance(status_obj, dict):
        return cfg.status_in(str(status_obj or ""), cfg.status_done)
    category = status_obj.get("statusCategory") or {}
    if isinstance(category, dict) and str(category.get("key") or "").casefold() == "done":
        return True
    name = str(status_obj.get("name") or "")
    return cfg.status_in(name, cfg.status_done)


def epic_children_all_done(epic_key: str, cfg: ClassifyConfig) -> bool | None:
    """True when all children terminal; False if any open; None if unknown/truncated.

    Zero children counts as all done. If the search returns exactly the page
    limit, treat as unknown (fail closed) instead of assuming all done.
    """
    if not is_jira_key(epic_key):
        raise ValueError(f"invalid jira key: {epic_key}")
    limit = 100
    jql = f'parent = {epic_key} OR "Epic Link" = {epic_key}'
    cmd = [
        "acli",
        "jira",
        "workitem",
        "search",
        "--jql",
        jql,
        "--fields",
        "key,status",
        "--limit",
        str(limit),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "acli epic children failed").strip())
    rows = json.loads(proc.stdout or "[]")
    if not isinstance(rows, list):
        return None
    if len(rows) >= limit:
        return None
    for row in rows:
        fields = row.get("fields") or {}
        if not _status_is_terminal(fields.get("status"), cfg):
            return False
    return True


def _extract_pr_link(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        m = re.search(r"https://github\.com/[^\"\s]+/pull/\d+", text)
        return m.group(0) if m else text
    # ADF-ish: dig for urls
    text = json.dumps(value)
    m = re.search(r"https://github\.com/[^\"\s]+/pull/\d+", text)
    return m.group(0) if m else None


_GH_PR_URL_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([^/]+/[^/]+)/pull/(\d+)",
    re.IGNORECASE,
)


def parse_github_pr_url(url: str) -> tuple[str, int] | None:
    """Return (owner/repo, number) from a GitHub PR URL, else None."""
    m = _GH_PR_URL_RE.search(url or "")
    if not m:
        return None
    return m.group(1), int(m.group(2))


def fetch_github_pr_merged(pr_url: str) -> bool | None:
    """True if PR merged; False if open/closed-unmerged; None if probe failed."""
    parsed = parse_github_pr_url(pr_url)
    if not parsed:
        return None
    repo, number = parsed
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "state,mergedAt",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("mergedAt"):
        return True
    return str(data.get("state") or "").upper() == "MERGED"


def _flagged_from_fields(fields: dict) -> bool:
    # Direct flagged / Flagged
    for key in ("flagged", "Flagged"):
        val = fields.get(key)
        if val:
            return True
    # Some sites expose impediment checkbox custom fields as list
    for key, val in fields.items():
        if not key.startswith("customfield_"):
            continue
        if isinstance(val, list) and val:
            # impediment option often present
            for entry in val:
                if isinstance(entry, dict):
                    name = str(entry.get("value") or entry.get("name") or "").casefold()
                    if "impediment" in name or name == "blocked":
                        return True
                elif str(entry).casefold() in {"impediment", "blocked"}:
                    return True
    return False


def _is_blocked_by_link(link: dict) -> bool:
    """True when this issue is the inward side of a Blocks / is-blocked-by link."""
    if not isinstance(link, dict) or "inwardIssue" not in link:
        return False
    link_type = link.get("type") or {}
    if not isinstance(link_type, dict):
        return False
    inward = str(link_type.get("inward") or "").casefold()
    name = str(link_type.get("name") or "").casefold()
    return inward == "is blocked by" or name == "blocks"


def blocked_by_unresolved_from_fields(fields: dict, cfg: ClassifyConfig) -> bool:
    """True if any 'is blocked by' linked issue is not terminal (or status missing)."""
    links = fields.get("issuelinks") or fields.get("issueLinks") or []
    if not isinstance(links, list):
        return False
    for link in links:
        if not isinstance(link, dict) or not _is_blocked_by_link(link):
            continue
        blocker = link.get("inwardIssue") or {}
        if not isinstance(blocker, dict):
            continue
        blocker_fields = blocker.get("fields") or {}
        if not isinstance(blocker_fields, dict):
            # Nested status missing — fail closed (treat as still blocking)
            return True
        status = blocker_fields.get("status")
        if status is None:
            return True
        if not _status_is_terminal(status, cfg):
            return True
    return False


def fetch_jira_view_fields(key: str, fields: str) -> dict:
    """Load fields via acli view (search forbids issuelinks and customfield_*)."""
    if not is_jira_key(key):
        raise ValueError(f"invalid jira key: {key}")
    cmd = [
        "acli",
        "jira",
        "workitem",
        "view",
        key,
        "--fields",
        fields,
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "acli view failed").strip())
    data = json.loads(proc.stdout or "{}")
    if not isinstance(data, dict):
        return {}
    parsed = data.get("fields") or {}
    return parsed if isinstance(parsed, dict) else {}


def fetch_jira_issuelinks(key: str) -> list:
    """Load issuelinks via acli view (search forbids the field)."""
    fields = fetch_jira_view_fields(key, "issuelinks")
    links = fields.get("issuelinks") or fields.get("issueLinks") or []
    return links if isinstance(links, list) else []


def enrich_jira_issues(
    keys: list[str],
    *,
    cfg: AppConfig,
    identity: Identity,
) -> dict[str, tuple[JiraIssueSnapshot, str, str]]:
    """Return key -> (snapshot, summary, url)."""
    valid_keys = [k for k in keys if is_jira_key(k)]
    skipped = sorted(set(keys) - set(valid_keys))
    for bad in skipped:
        print(f"Skipping invalid Jira key in store: {bad}")
    if not valid_keys:
        return {}
    # Batch in chunks of 40
    out: dict[str, tuple[JiraIssueSnapshot, str, str]] = {}
    fields = _jira_search_fields()
    classify_cfg = cfg.classify_config()
    for i in range(0, len(valid_keys), 40):
        chunk = valid_keys[i : i + 40]
        jql = "key in (" + ", ".join(chunk) + ")"
        rows = _acli_workitem_search(jql=jql, fields=fields, limit=len(chunk))
        for row in rows:
            key = str(row.get("key") or "")
            if not is_jira_key(key):
                continue
            f = row.get("fields") or {}
            status = ((f.get("status") or {}).get("name") or "")
            summary = str(f.get("summary") or "")
            labels = tuple(f.get("labels") or [])
            assignee = f.get("assignee") or {}
            assignee_id = str(assignee.get("accountId") or "")
            assignee_is_user = bool(
                identity.jira_account_id and assignee_id == identity.jira_account_id
            )
            issue_type = ((f.get("issuetype") or {}).get("name") or "")
            site = cfg.jira_site.strip()
            if site:
                url = f"https://{site}/browse/{key}"
            else:
                url = ""
            snap = JiraIssueSnapshot(
                key=key,
                status=status,
                assignee_is_user=assignee_is_user,
                qa_contact_is_user=False,
                flagged=_flagged_from_fields(f),
                labels=labels,
                pr_link=None,
                issue_type=issue_type,
            )
            out[key] = (snap, summary, url)

    # Issuelinks + QA/PR custom fields: acli search rejects those; one view per issue
    view_fields = ",".join(_jira_view_field_names(cfg))
    for key, (snap, summary, url) in list(out.items()):
        try:
            vf = fetch_jira_view_fields(key, view_fields)
        except (RuntimeError, json.JSONDecodeError, ValueError) as exc:
            print(f"Warning: view for {key}: {exc}")
            vf = {}
            try:
                vf = fetch_jira_view_fields(key, "issuelinks")
            except (RuntimeError, json.JSONDecodeError, ValueError) as exc2:
                print(f"Warning: issuelinks for {key}: {exc2}")
            for extra in _jira_view_field_names(cfg):
                if extra == "issuelinks":
                    continue
                try:
                    vf.update(fetch_jira_view_fields(key, extra))
                except (RuntimeError, json.JSONDecodeError, ValueError) as exc3:
                    print(f"Warning: field {extra} for {key}: {exc3}")
        links = vf.get("issuelinks") or vf.get("issueLinks") or []
        if not isinstance(links, list):
            links = []
        snap.blocked_by_unresolved = blocked_by_unresolved_from_fields(
            {"issuelinks": links}, classify_cfg
        )
        if cfg.jira_qa_contact_field and identity.jira_account_id:
            snap.qa_contact_is_user = _qa_contact_is_user(
                vf.get(cfg.jira_qa_contact_field), identity.jira_account_id
            )
        if cfg.jira_pr_link_field:
            snap.pr_link = _extract_pr_link(vf.get(cfg.jira_pr_link_field))
        out[key] = (snap, summary, url)

    # Review + Git PR field: probe whether linked PR is merged (gh)
    for key, (snap, summary, url) in list(out.items()):
        if not classify_cfg.status_in(snap.status, classify_cfg.status_review):
            continue
        if not snap.pr_link or not parse_github_pr_url(snap.pr_link):
            continue
        try:
            snap.linked_pr_merged = fetch_github_pr_merged(snap.pr_link)
        except (RuntimeError, ValueError) as exc:
            print(f"Warning: PR merge probe for {key}: {exc}")
            snap.linked_pr_merged = None
        out[key] = (snap, summary, url)

    # Fill epic child rollups (one search per epic)
    for key, (snap, summary, url) in list(out.items()):
        if snap.issue_type.casefold() != "epic":
            continue
        try:
            all_done = epic_children_all_done(key, classify_cfg)
        except RuntimeError:
            all_done = None
        snap.epic_children_all_done = all_done
        out[key] = (snap, summary, url)
    return out


def apply_classification_to_item(
    item: TrackedItem,
    *,
    action: ActionState,
    lifecycle: str,
    remote_status: str,
    blocked: bool,
    reasons: tuple[str, ...],
    summary: str = "",
    url: str = "",
    issue_type: str | None = None,
    pr_link: str | None = None,
    linked_issue_ids: list[str] | None = None,
    now_s: str | None = None,
) -> bool:
    """Update item; return True if state fingerprint changed."""
    now_s = now_s or _iso(_utcnow())
    if summary:
        item.summary = summary
    if url:
        item.url = url
    if issue_type is not None:
        item.issue_type = issue_type
    if pr_link is not None:
        item.pr_link = pr_link
    if linked_issue_ids is not None:
        item.linked_issue_ids = list(linked_issue_ids)
    item.remote_status = remote_status
    item.action = action.value
    item.blocked = blocked
    item.reasons = list(reasons)
    if lifecycle == "done":
        item.lifecycle = "done"
        if not item.finished_at:
            item.finished_at = now_s
    elif lifecycle == "active":
        item.lifecycle = "active"
        item.finished_at = None

    fp = state_fingerprint(
        action=item.action,
        lifecycle=item.lifecycle,
        remote_status=item.remote_status,
        blocked=item.blocked,
        reasons=item.reasons,
    )
    changed = fp != item.state_fingerprint
    if changed or not item.state_changed_at:
        item.state_changed_at = now_s
        item.state_fingerprint = fp
    item.last_seen_at = now_s
    return changed


def enrich_and_classify_store(store: TrackStore, cfg: AppConfig) -> tuple[int, int]:
    """Enrich active (+ recently done) items. Returns (classified, state_changes)."""
    identity = resolve_identity(cfg)
    now_s = _iso(_utcnow())
    classify_cfg = cfg.classify_config()

    jira_items = [i for i in store.items.values() if i.source == "jira"]
    gh_pr_items = [i for i in store.items.values() if i.source == "github_pr"]
    gh_issue_items = [i for i in store.items.values() if i.source == "github_issue"]

    jira_map = enrich_jira_issues(
        [i.key for i in jira_items],
        cfg=cfg,
        identity=identity,
    )

    # Build blocked jira key set for PR linkage
    blocked_jira_keys: set[str] = set()
    for key, (snap, _, _) in jira_map.items():
        if is_jira_blocked(snap, classify_cfg):
            blocked_jira_keys.add(key)

    classified = 0
    changes = 0

    for item in jira_items:
        classified += 1
        if item.key not in jira_map:
            # unreachable remotely — leave as-is
            continue
        snap, summary, url = jira_map[item.key]
        result = classify_jira(snap, classify_cfg)
        lifecycle = (
            "done"
            if result.action == ActionState.DONE
            else ("active" if result.should_track or item.pinned else "done")
        )
        # ignore => keep in store but mark done/untracked as finished for digest
        if result.action == ActionState.IGNORE and not item.pinned:
            lifecycle = "done"
        if result.action == ActionState.DONE:
            lifecycle = "done"
        if result.should_track:
            lifecycle = "active"
        changed = apply_classification_to_item(
            item,
            action=result.action,
            lifecycle=lifecycle,
            remote_status=snap.status,
            blocked=result.blocked,
            reasons=result.reasons,
            summary=summary,
            url=url,
            issue_type=snap.issue_type,
            pr_link=snap.pr_link or "",
            now_s=now_s,
        )
        if changed:
            changes += 1

    for item in gh_pr_items:
        try:
            snap, title, url, linked_issue_ids = enrich_github_pr(item, identity, cfg)
        except RuntimeError as exc:
            print(f"Skipping GitHub PR enrich for {item.key}: {exc}")
            continue
        classified += 1
        keys_in_title = set(_JIRA_KEY_RE.findall(title))
        linked_blocked = bool(keys_in_title & blocked_jira_keys)
        for key, (jsnap, _, _) in jira_map.items():
            if jsnap.pr_link and re.search(
                rf"{re.escape(snap.repo)}/pull/{snap.number}\b", jsnap.pr_link
            ):
                if key in blocked_jira_keys:
                    linked_blocked = True
        snap.linked_jira_blocked = linked_blocked
        result = classify_github(snap, classify_cfg)
        if result.action == ActionState.DONE or (
            result.action == ActionState.IGNORE and not item.pinned
        ):
            lifecycle = "done"
        elif result.should_track:
            lifecycle = "active"
        else:
            lifecycle = item.lifecycle
        remote_status = github_remote_status(snap)
        changed = apply_classification_to_item(
            item,
            action=result.action,
            lifecycle=lifecycle,
            remote_status=remote_status,
            blocked=result.blocked,
            reasons=result.reasons,
            summary=title,
            url=url,
            linked_issue_ids=linked_issue_ids,
            now_s=now_s,
        )
        if changed:
            changes += 1

    for item in gh_issue_items:
        try:
            snap, title, url = enrich_github_issue(item, identity)
        except RuntimeError as exc:
            print(f"Skipping GitHub Issue enrich for {item.key}: {exc}")
            continue
        classified += 1
        keys_in_title = set(_JIRA_KEY_RE.findall(title))
        snap.linked_jira_blocked = bool(keys_in_title & blocked_jira_keys)
        result = classify_github_issue(snap, classify_cfg)
        if result.action == ActionState.DONE or (
            result.action == ActionState.IGNORE and not item.pinned
        ):
            lifecycle = "done"
        elif result.should_track:
            lifecycle = "active"
        else:
            lifecycle = item.lifecycle
        remote_status = snap.state
        changed = apply_classification_to_item(
            item,
            action=result.action,
            lifecycle=lifecycle,
            remote_status=remote_status,
            blocked=result.blocked,
            reasons=result.reasons,
            summary=title,
            url=url,
            pr_link=snap.pr_link or "",
            now_s=now_s,
        )
        if changed:
            changes += 1

    store.updated_at = now_s
    return classified, changes
