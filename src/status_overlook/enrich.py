"""Enrich tracked items from gh/acli, classify, update fingerprints."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass

from status_overlook.classify_github import classify_github
from status_overlook.classify_jira import classify_jira, is_jira_blocked
from status_overlook.config import AppConfig
from status_overlook.models import ActionState, GitHubPrSnapshot, JiraIssueSnapshot
from status_overlook.store import TrackStore, TrackedItem, _iso, _utcnow

_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


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
    # Discover Jira accountId from an assigned issue if possible
    account_id = ""
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


def enrich_github_pr(
    item: TrackedItem, identity: Identity
) -> tuple[GitHubPrSnapshot, str, str]:
    # key is org/repo#n
    if "#" not in item.key:
        raise ValueError(f"bad github key: {item.key}")
    repo, num_s = item.key.rsplit("#", 1)
    data = _run_json(
        [
            "gh",
            "pr",
            "view",
            num_s,
            "--repo",
            repo,
            "--json",
            "number,state,isDraft,mergedAt,author,assignees,labels,reviewDecision,statusCheckRollup,title,url",
        ]
    )
    assert isinstance(data, dict)
    author = ((data.get("author") or {}).get("login") or "").casefold()
    assignees = {
        (a.get("login") or "").casefold() for a in (data.get("assignees") or [])
    }
    me = identity.github_login.casefold()
    labels = tuple(x.get("name") or "" for x in (data.get("labels") or []))
    review = (data.get("reviewDecision") or "").upper()
    state = (data.get("state") or "open").lower()
    merged = bool(data.get("mergedAt"))
    return GitHubPrSnapshot(
        repo=repo,
        number=int(data.get("number") or num_s),
        state="closed" if state == "closed" else "open",
        merged=merged,
        draft=bool(data.get("isDraft")),
        author_is_user=author == me,
        assignee_is_user=me in assignees,
        labels=labels,
        has_unresolved_reviews=review == "CHANGES_REQUESTED",
        ci_failed=_ci_failed(data.get("statusCheckRollup")),
        linked_jira_blocked=False,  # filled after jira map known
    ), str(data.get("title") or item.summary), str(data.get("url") or item.url)


def _jira_fields_list(cfg: AppConfig) -> str:
    fields = ["key", "summary", "status", "assignee", "labels"]
    if cfg.jira_qa_contact_field:
        fields.append(cfg.jira_qa_contact_field)
    if cfg.jira_pr_link_field:
        fields.append(cfg.jira_pr_link_field)
    # Best-effort Flagged; ignore if acli rejects later
    fields.append("flagged")
    return ",".join(fields)


def _extract_pr_link(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    # ADF-ish: dig for urls
    text = json.dumps(value)
    m = re.search(r"https://github\.com/[^\"\s]+/pull/\d+", text)
    return m.group(0) if m else None


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


def enrich_jira_issues(
    keys: list[str],
    *,
    cfg: AppConfig,
    identity: Identity,
) -> dict[str, tuple[JiraIssueSnapshot, str, str]]:
    """Return key -> (snapshot, summary, url)."""
    if not keys:
        return {}
    # Batch in chunks of 40
    out: dict[str, tuple[JiraIssueSnapshot, str, str]] = {}
    fields = _jira_fields_list(cfg)
    for i in range(0, len(keys), 40):
        chunk = keys[i : i + 40]
        jql = "key in (" + ", ".join(chunk) + ")"
        cmd = [
            "acli",
            "jira",
            "workitem",
            "search",
            "--jql",
            jql,
            "--fields",
            fields,
            "--limit",
            str(len(chunk)),
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 and "flagged" in (proc.stderr or "").lower():
            # Retry without flagged field name
            fields_alt = ",".join(f for f in fields.split(",") if f.casefold() != "flagged")
            cmd[cmd.index("--fields") + 1] = fields_alt
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "acli failed").strip())
        rows = json.loads(proc.stdout or "[]")
        for row in rows:
            key = str(row.get("key") or "")
            f = row.get("fields") or {}
            status = ((f.get("status") or {}).get("name") or "")
            summary = str(f.get("summary") or "")
            labels = tuple(f.get("labels") or [])
            assignee = f.get("assignee") or {}
            assignee_id = str(assignee.get("accountId") or "")
            assignee_is_user = bool(
                identity.jira_account_id and assignee_id == identity.jira_account_id
            )
            qa_is_user = False
            if cfg.jira_qa_contact_field:
                qa = f.get(cfg.jira_qa_contact_field)
                if isinstance(qa, dict):
                    qa_is_user = str(qa.get("accountId") or "") == identity.jira_account_id
                elif isinstance(qa, list) and qa and isinstance(qa[0], dict):
                    qa_is_user = str(qa[0].get("accountId") or "") == identity.jira_account_id
            pr_link = None
            if cfg.jira_pr_link_field:
                pr_link = _extract_pr_link(f.get(cfg.jira_pr_link_field))
            site = cfg.jira_site or "redhat.atlassian.net"
            url = f"https://{site}/browse/{key}"
            snap = JiraIssueSnapshot(
                key=key,
                status=status,
                assignee_is_user=assignee_is_user,
                qa_contact_is_user=qa_is_user,
                flagged=_flagged_from_fields(f),
                labels=labels,
                pr_link=pr_link,
            )
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
    now_s: str | None = None,
) -> bool:
    """Update item; return True if state fingerprint changed."""
    now_s = now_s or _iso(_utcnow())
    if summary:
        item.summary = summary
    if url:
        item.url = url
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
    gh_items = [i for i in store.items.values() if i.source == "github"]

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
            now_s=now_s,
        )
        if changed:
            changes += 1

    for item in gh_items:
        classified += 1
        try:
            snap, title, url = enrich_github_pr(item, identity)
        except RuntimeError:
            continue
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
        remote_status = "draft" if snap.draft else snap.state
        if snap.ci_failed:
            remote_status = f"{remote_status}+ci_fail"
        if snap.has_unresolved_reviews:
            remote_status = f"{remote_status}+changes_requested"
        changed = apply_classification_to_item(
            item,
            action=result.action,
            lifecycle=lifecycle,
            remote_status=remote_status,
            blocked=result.blocked,
            reasons=result.reasons,
            summary=title,
            url=url,
            now_s=now_s,
        )
        if changed:
            changes += 1

    store.updated_at = now_s
    return classified, changes
