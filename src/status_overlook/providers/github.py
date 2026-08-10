"""GitHub discovery via `gh` CLI."""

from __future__ import annotations

import json
import subprocess

from status_overlook.store import Candidate


class ProviderError(RuntimeError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


def _gh_json(args: list[str]) -> list[dict]:
    cmd = ["gh", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "gh failed").strip()
        hint = "Run: gh auth login" if "auth" in err.lower() else ""
        raise ProviderError(err, hint=hint)
    data = json.loads(proc.stdout or "[]")
    if not isinstance(data, list):
        raise ProviderError(f"unexpected gh JSON: {type(data)}")
    return data


def _pr_candidate(row: dict) -> Candidate:
    repo = (row.get("repository") or {}).get("nameWithOwner") or "unknown/unknown"
    number = int(row["number"])
    key = f"{repo}#{number}"
    return Candidate(
        source="github",
        key=key,
        url=str(row.get("url") or f"https://github.com/{repo}/pull/{number}"),
        summary=str(row.get("title") or ""),
        remote_status="open",
    )


def fetch_open_prs(*, limit: int = 50) -> list[Candidate]:
    """Open PRs authored by or assigned to the authenticated user."""
    fields = "number,url,title,repository,updatedAt"
    authored = _gh_json(
        [
            "search",
            "prs",
            "--author=@me",
            "--state=open",
            f"--limit={limit}",
            f"--json={fields}",
        ]
    )
    assigned = _gh_json(
        [
            "search",
            "prs",
            "--assignee=@me",
            "--state=open",
            f"--limit={limit}",
            f"--json={fields}",
        ]
    )
    by_id: dict[str, Candidate] = {}
    for row in authored + assigned:
        cand = _pr_candidate(row)
        by_id[cand.id] = cand
    if len(authored) >= limit or len(assigned) >= limit:
        print(
            f"Warning: GitHub PR search hit limit={limit}; "
            "raise search_limit in config or some PRs may look finished."
        )
    return list(by_id.values())
