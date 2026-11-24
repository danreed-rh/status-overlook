"""Local, independently persisted team roster and observed review queue."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from status_overlook.fsutil import ensure_private_dir
from status_overlook.paths import team_members_path, team_queue_path

_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_MAX_MEMBERS = 50


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_login(value: str) -> bool:
    """Accept a GitHub user login, not CLI flags or a URL."""
    return bool(_LOGIN_RE.fullmatch(value or "")) and "--" not in value


def _write_json(path: Path, data: dict) -> None:
    """Atomically replace a private JSON file for UI/scheduler concurrency."""
    ensure_private_dir(path.parent)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def load_members(path: Path | None = None) -> list[str]:
    path = path or team_members_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid team roster: {path}")
    members = data.get("members")
    if not isinstance(members, list) or any(
        not isinstance(x, str) or not valid_login(x) for x in members
    ):
        raise ValueError(f"Invalid team roster: {path}")
    if len(members) > _MAX_MEMBERS or len({x.casefold() for x in members}) != len(members):
        raise ValueError(f"Duplicate or oversized team roster: {path}")
    return members


def save_members(members: list[str], path: Path | None = None) -> None:
    path = path or team_members_path()
    if len(members) > _MAX_MEMBERS or len({x.casefold() for x in members}) != len(members):
        raise ValueError("Duplicate or oversized team roster")
    if any(not valid_login(x) for x in members):
        raise ValueError("Invalid GitHub username")
    _write_json(path, {"schema_version": 1, "members": members})


def update_member(
    login: str, action: str, *, self_login: str = "", path: Path | None = None
) -> list[str]:
    login = (login or "").strip()
    if not valid_login(login):
        raise ValueError("Enter a GitHub username (letters, digits, and single hyphens)")
    if action not in {"add", "remove"}:
        raise ValueError("Choose add or remove")
    if action == "add" and login.casefold() == self_login.casefold():
        raise ValueError("Your own PRs are tracked on My Work")
    members = load_members(path)
    if action == "add" and login.casefold() not in {m.casefold() for m in members}:
        members.append(login)
    if action == "remove":
        members = [m for m in members if m.casefold() != login.casefold()]
    save_members(members, path)
    return members


@dataclass
class TeamPr:
    repo: str
    number: int
    title: str
    url: str
    author: str
    queue: str  # unassigned | lgtm
    unassigned: bool
    updated_at: str = ""
    entered_at: str = ""

    @property
    def id(self) -> str:
        return f"{self.repo}#{self.number}"

    @classmethod
    def from_dict(cls, data: dict) -> TeamPr:
        return cls(
            repo=str(data["repo"]),
            number=int(data["number"]),
            title=str(data.get("title") or ""),
            url=str(data.get("url") or ""),
            author=str(data["author"]),
            queue=str(data["queue"]),
            unassigned=bool(data.get("unassigned")),
            updated_at=str(data.get("updated_at") or ""),
            entered_at=str(data.get("entered_at") or ""),
        )


@dataclass
class TeamQueue:
    updated_at: str = ""
    last_attempt_at: str = ""
    last_error: str = ""
    items: list[TeamPr] = field(default_factory=list)


def load_team_queue(path: Path | None = None) -> TeamQueue:
    path = path or team_queue_path()
    if not path.is_file():
        return TeamQueue()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid team queue: {path}")
    rows = data.get("items") or []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid team queue items: {path}")
    return TeamQueue(
        updated_at=str(data.get("updated_at") or ""),
        last_attempt_at=str(data.get("last_attempt_at") or ""),
        last_error=str(data.get("last_error") or ""),
        items=[TeamPr.from_dict(row) for row in rows],
    )


def save_team_queue(queue: TeamQueue, path: Path | None = None) -> None:
    _write_json(
        path or team_queue_path(),
        {
            "schema_version": 1,
            "updated_at": queue.updated_at,
            "last_attempt_at": queue.last_attempt_at,
            "last_error": queue.last_error,
            "items": [asdict(item) for item in queue.items],
        },
    )


def team_payload() -> dict:
    members = load_members()
    queue = load_team_queue()
    allowed = {member.casefold() for member in members}
    return {
        "members": members,
        "updated_at": queue.updated_at,
        "last_attempt_at": queue.last_attempt_at,
        "last_error": queue.last_error,
        "items": [asdict(item) for item in queue.items if item.author.casefold() in allowed],
    }


def refresh_team_queue(*, limit: int = 50, self_login: str = "") -> TeamQueue:
    """Keep the last successful snapshot if any GitHub query fails."""
    from status_overlook.providers.team_github import fetch_team_prs

    members = load_members()
    old = load_team_queue()
    now = utc_now()
    if not members:
        queue = TeamQueue(updated_at=now, last_attempt_at=now)
        save_team_queue(queue)
        return queue
    try:
        items = fetch_team_prs(members, limit=limit, self_login=self_login)
    except (RuntimeError, ValueError, OSError) as exc:
        old.last_attempt_at = now
        old.last_error = str(exc)
        save_team_queue(old)
        return old

    # The roster may have changed in the UI while the network calls ran.
    allowed = {member.casefold() for member in load_members()}
    previous = {(item.id, item.queue): item for item in old.items}
    for item in items:
        earlier = previous.get((item.id, item.queue))
        item.entered_at = earlier.entered_at if earlier and earlier.entered_at else now
    queue = TeamQueue(
        updated_at=now,
        last_attempt_at=now,
        items=[item for item in items if item.author.casefold() in allowed],
    )
    save_team_queue(queue)
    return queue
