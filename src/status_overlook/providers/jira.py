"""Jira discovery via `acli` CLI."""

from __future__ import annotations

import json
import subprocess

from status_overlook.jira_ids import qa_field_to_jql, safe_jql_status
from status_overlook.store import Candidate


class ProviderError(RuntimeError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def _acli_search(jql: str, *, fields: str, limit: int) -> list[dict]:
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
        str(limit),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "acli failed").strip()
        hint = ""
        if any(x in err.lower() for x in ("auth", "unauthorized", "401", "login")):
            hint = (
                "Run: acli jira auth login --site <site>.atlassian.net "
                "--email <you@example.com> --token"
            )
        raise ProviderError(err, hint=hint)
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise ProviderError(f"unexpected acli JSON: {type(data)}")
    return data


def _issue_candidate(row: dict, *, site: str) -> Candidate:
    key = str(row.get("key") or "")
    fields = row.get("fields") or {}
    status_obj = fields.get("status") or {}
    status = status_obj.get("name") if isinstance(status_obj, dict) else str(status_obj or "")
    summary = str(fields.get("summary") or "")
    if site:
        url = f"https://{site}/browse/{key}"
    elif key:
        url = f"https://redhat.atlassian.net/browse/{key}"
    else:
        url = str(row.get("self") or "")
    return Candidate(
        source="jira",
        key=key,
        url=url,
        summary=summary,
        remote_status=status,
    )


def fetch_assigned_and_qa_issues(
    *,
    site: str = "",
    qa_contact_field: str = "",
    testing_statuses: tuple[str, ...] = ("Testing",),
    limit: int = 50,
) -> list[Candidate]:
    """Issues assigned to currentUser (unresolved) plus QA-contact in Testing."""
    fields = "key,summary,status,labels"
    jql_assignee = "assignee = currentUser() AND resolution = EMPTY"
    rows = _acli_search(jql_assignee, fields=fields, limit=limit)

    if qa_contact_field:
        jql_cf = qa_field_to_jql(qa_contact_field)
        if jql_cf is None:
            print(
                f"Skipping QA discovery: jira.qa_contact_field must be "
                f"customfield_<digits> (got {qa_contact_field!r})"
            )
        else:
            safe_statuses = []
            for s in testing_statuses:
                cleaned = safe_jql_status(s)
                if cleaned is None:
                    print(f"Skipping unsafe testing status in JQL: {s!r}")
                else:
                    safe_statuses.append(cleaned)
            if safe_statuses:
                status_list = ", ".join(f'"{s}"' for s in safe_statuses)
                jql_qa = (
                    f"{jql_cf} = currentUser() AND status in ({status_list}) "
                    "AND resolution = EMPTY"
                )
                try:
                    rows.extend(_acli_search(jql_qa, fields=fields, limit=limit))
                except ProviderError as exc:
                    # Unknown field on some sites — warn; Phase 4 doctor can harden
                    print(f"QA discovery skipped: {exc}")

    by_id: dict[str, Candidate] = {}
    for row in rows:
        cand = _issue_candidate(row, site=site)
        if cand.key:
            by_id[cand.id] = cand
    return list(by_id.values())
