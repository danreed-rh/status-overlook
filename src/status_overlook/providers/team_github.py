"""Read-only GitHub CLI queries for the manually curated team PR queue."""

from __future__ import annotations

import json
import re
import subprocess

from status_overlook.team import TeamPr

_REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
_FIELDS = "number,title,url,author,repository,assignees,isDraft,labels,updatedAt"


class TeamProviderError(RuntimeError):
    pass


def _gh_json(args: list[str]) -> object:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise TeamProviderError((proc.stderr or proc.stdout or "GitHub CLI failed").strip())
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise TeamProviderError("GitHub CLI returned invalid JSON") from exc


def fetch_team_prs(
    members: list[str], *, limit: int, self_login: str = ""
) -> list[TeamPr]:
    """Only verified, open, non-draft PRs with required review outstanding."""
    if not 1 <= limit <= 1000:
        raise ValueError("team search_limit must be between 1 and 1000")
    permissions: dict[str, bool] = {}
    result: dict[str, TeamPr] = {}
    for login in members:
        if login.casefold() == self_login.casefold():
            continue
        rows = _gh_json(
            [
                "search", "prs", f"--author={login}", "--state=open",
                "--review=required", f"--limit={limit}", f"--json={_FIELDS}",
            ]
        )
        if not isinstance(rows, list):
            raise TeamProviderError(f"Unexpected search result for {login}")
        if len(rows) >= limit:
            raise TeamProviderError(
                f"Search for {login} reached limit={limit}; raise search_limit before refreshing team results"
            )
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("repository"), dict):
                raise TeamProviderError(f"Unexpected search row for {login}")
            repo = row["repository"].get("nameWithOwner") or ""
            number = row.get("number")
            if (
                not isinstance(repo, str)
                or not _REPO_RE.fullmatch(repo)
                or type(number) is not int
                or number < 1
            ):
                raise TeamProviderError("GitHub search returned an invalid repository or PR number")
            details = _gh_json([
                "pr", "view", str(number), "--repo", repo, "--json",
                "state,isDraft,reviewDecision,assignees,labels,author,title,url,updatedAt",
            ])
            if (
                not isinstance(details, dict)
                or not isinstance(details.get("author"), dict)
                or not isinstance(details.get("assignees"), list)
                or not isinstance(details.get("labels"), list)
                or any(not isinstance(label, dict) for label in details["labels"])
                or not isinstance(details.get("isDraft"), bool)
            ):
                raise TeamProviderError(f"Unexpected PR details for {repo}#{number}")
            if (
                str(details.get("state") or "").upper() != "OPEN"
                or details.get("isDraft")
                or details.get("reviewDecision") != "REVIEW_REQUIRED"
                or ((details.get("author") or {}).get("login") or "").casefold() != login.casefold()
            ):
                continue
            unassigned = not details.get("assignees")
            labels = {
                str(label.get("name") or "").casefold()
                for label in (details.get("labels") or [])
            }
            lgtm = "lgtm" in labels
            maintain = False
            if lgtm:
                if repo not in permissions:
                    perms = _gh_json(["api", f"repos/{repo}", "--jq", ".permissions"])
                    if not isinstance(perms, dict):
                        raise TeamProviderError(f"Could not verify maintainer role for {repo}")
                    permissions[repo] = perms.get("admin") is True or perms.get("maintain") is True
                maintain = permissions[repo]
            if not (lgtm and maintain) and not unassigned:
                continue
            item = TeamPr(
                repo=repo,
                number=number,
                title=str(details.get("title") or ""),
                url=str(details.get("url") or f"https://github.com/{repo}/pull/{number}"),
                author=login,
                queue="lgtm" if lgtm and maintain else "unassigned",
                unassigned=unassigned,
                updated_at=str(details.get("updatedAt") or ""),
            )
            result[item.id] = item
    return sorted(result.values(), key=lambda item: (item.queue, item.repo.casefold(), item.number))
