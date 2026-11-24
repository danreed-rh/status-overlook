"""Emit human/agent digests from the track store."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from status_overlook.cues import cue_dict, cue_for
from status_overlook.enrich import parse_github_pr_url
from status_overlook.fsutil import ensure_private_dir, write_private_text
from status_overlook.paths import cache_dir, digest_json_path, digest_md_path
from status_overlook.store import TrackStore, TrackedItem, _iso, _utcnow, parse_iso

_JIRA_KEY_IN_TEXT_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_ACTIVE_ACTIONS = frozenset({"actionable", "pending", "blocked"})
_ACTION_RANK = {"actionable": 3, "pending": 2, "blocked": 1}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def status_age_label(
    state_changed_at: str | None, *, now: datetime | None = None
) -> str:
    """Return whole days since the last observed visible-state change."""
    try:
        changed = parse_iso(state_changed_at)
    except (TypeError, ValueError):
        return ""
    if changed is None:
        return ""
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - changed).total_seconds()))
    if seconds < 86400:
        return "<1d"
    return f"{seconds // 86400}d"


def is_unread(item: TrackedItem) -> bool:
    if not item.state_changed_at:
        return False
    if not item.last_read_at:
        return True
    changed = parse_iso(item.state_changed_at)
    read = parse_iso(item.last_read_at)
    if changed is None:
        return False
    if read is None:
        return True
    return changed > read


def is_jira_epic(item: TrackedItem) -> bool:
    """True when the tracked item is a Jira Epic."""
    return item.source == "jira" and (item.issue_type or "").casefold() == "epic"


def _recency_sort_key(item: TrackedItem) -> tuple[str, str]:
    return (item.state_changed_at or "", item.id)


def _action_rank(action: str) -> int:
    return _ACTION_RANK.get(action, 0)


def _is_open_github(item: TrackedItem) -> bool:
    if item.source != "github_pr":
        return False
    status = (item.remote_status or "").casefold().split("+", 1)[0]
    return status in {"open", "draft"}


def _primary_sort_key(item: TrackedItem) -> tuple[int, int, str]:
    """Higher tuple wins as group primary."""
    open_gh = 2 if _is_open_github(item) else 0
    jira_fallback = 1 if item.source == "jira" else 0
    return (_action_rank(item.action), open_gh + jira_fallback, item.id)


def _best_action(members: list[TrackedItem]) -> str:
    return max((m.action for m in members), key=_action_rank, default="")


@dataclass
class WorkGroup:
    """One digest/show entry; may collapse a linked Jira + PR pair."""

    primary: TrackedItem
    linked: list[TrackedItem] = field(default_factory=list)
    action: str = ""

    @property
    def members(self) -> list[TrackedItem]:
        return [self.primary, *self.linked]

    def is_unread(self) -> bool:
        return any(is_unread(m) for m in self.members)

    @property
    def state_changed_at(self) -> str:
        return max((m.state_changed_at or "" for m in self.members), default="")


def _github_pr_store_id(repo: str, number: int) -> str:
    return f"github-pr:{repo}#{number}"


def _pair_edges(active: dict[str, TrackedItem]) -> list[tuple[str, str]]:
    """Return (id_a, id_b) edges between linked Jira, PR, and Issue items."""
    edges: list[tuple[str, str]] = []
    jira_by_key = {
        i.key: i.id for i in active.values() if i.source == "jira"
    }

    for item in active.values():
        # Jira or Issue with pr_link → PR
        if item.source in ("jira", "github_issue") and item.pr_link:
            parsed = parse_github_pr_url(item.pr_link)
            if parsed:
                repo, number = parsed
                gid = _github_pr_store_id(repo, number)
                if gid in active:
                    edges.append((item.id, gid))

        # PR → linked Issues
        if item.source == "github_pr":
            for iid in item.linked_issue_ids or []:
                if iid in active:
                    edges.append((item.id, iid))
            for key in _JIRA_KEY_IN_TEXT_RE.findall(item.summary or ""):
                jid = jira_by_key.get(key) or f"jira:{key}"
                if jid in active:
                    edges.append((item.id, jid))

        # Issue title → Jira keys
        if item.source == "github_issue":
            for key in _JIRA_KEY_IN_TEXT_RE.findall(item.summary or ""):
                jid = jira_by_key.get(key) or f"jira:{key}"
                if jid in active:
                    edges.append((item.id, jid))
    return edges


def build_work_groups(store: TrackStore) -> list[WorkGroup]:
    """Collapse linked Jira+PR pairs among active actionable/pending/blocked items."""
    active = {
        i.id: i
        for i in store.items.values()
        if i.lifecycle == "active" and i.action in _ACTIVE_ACTIONS
    }
    if not active:
        return []

    parent = {iid: iid for iid in active}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in _pair_edges(active):
        union(a, b)

    clusters: dict[str, list[TrackedItem]] = {}
    for iid, item in active.items():
        clusters.setdefault(find(iid), []).append(item)

    groups: list[WorkGroup] = []
    for members in clusters.values():
        primary = max(members, key=_primary_sort_key)
        linked = sorted(
            (m for m in members if m.id != primary.id),
            key=lambda m: m.id,
        )
        groups.append(
            WorkGroup(
                primary=primary,
                linked=linked,
                action=_best_action(members),
            )
        )
    return groups


def _section_groups(store: TrackStore, action: str) -> list[WorkGroup]:
    if action == "done":
        items = [i for i in store.items.values() if i.action == "done"]
        items.sort(key=_recency_sort_key, reverse=True)
        return [WorkGroup(primary=i, linked=[], action="done") for i in items]

    groups = [g for g in build_work_groups(store) if g.action == action]
    non_epics = sorted(
        (g for g in groups if not is_jira_epic(g.primary)),
        key=lambda g: (g.state_changed_at, g.primary.id),
        reverse=True,
    )
    epics = sorted(
        (g for g in groups if is_jira_epic(g.primary)),
        key=lambda g: (g.state_changed_at, g.primary.id),
        reverse=True,
    )
    return non_epics + epics


def _section_items(store: TrackStore, action: str) -> list[TrackedItem]:
    """Primaries only for a section (compat / tests). Prefer `_section_groups`."""
    return [g.primary for g in _section_groups(store, action)]


def _short_key(item: TrackedItem) -> str:
    key = item.key or item.id
    if item.source in ("github_pr", "github_issue") and "#" in key:
        return "#" + key.rsplit("#", 1)[-1]
    return key


_PR_STATUS_BASE = {
    "open": "Open",
    "draft": "Draft",
    "closed": "Closed",
    "merged": "Merged",
}
_PR_STATUS_FLAGS = {
    "ci_fail": "CI failing",
    "unresolved_threads": "Unresolved review threads",
    "awaiting_author": "Awaiting author",
}


def ui_status_label(item: TrackedItem) -> str:
    """Readable UI label; keep remote_status unchanged for storage and agents."""
    raw = item.remote_status or ""
    if item.source != "github_pr" or not raw:
        return raw or "—"
    base, *flags = raw.split("+")
    if base not in _PR_STATUS_BASE or any(flag not in _PR_STATUS_FLAGS for flag in flags):
        return raw
    return " · ".join([_PR_STATUS_BASE[base], *(_PR_STATUS_FLAGS[flag] for flag in flags)])


def _linked_note(linked: list[TrackedItem]) -> str:
    if not linked:
        return ""
    parts = []
    for item in linked:
        age = status_age_label(item.state_changed_at)
        status = item.remote_status or "—"
        suffix = f" · {age}" if age else ""
        parts.append(f"↔ {_short_key(item)} [{status}{suffix}]")
    return " " + " ".join(parts)


def _format_line(item: TrackedItem, linked: list[TrackedItem] | None = None) -> str:
    linked = linked or []
    unread = " ●" if (is_unread(item) or any(is_unread(m) for m in linked)) else ""
    epic = " [Epic]" if is_jira_epic(item) else ""
    link_note = _linked_note(linked)
    cue = cue_for(item.action, item.reasons)
    cue_note = f" ({cue.label})" if cue else ""
    link = f" — {item.url}" if item.url else ""
    changed = item.state_changed_at or "—"
    age = status_age_label(item.state_changed_at)
    status = item.remote_status or "—"
    if age:
        status = f"{status} · {age}"
    return (
        f"- [{item.action or '?'}]{unread} **{item.key}**{epic}{link_note} "
        f"[{status}] {item.summary}{cue_note}  \n"
        f"  state_changed: {changed}{link}"
    )


def _format_group_line(group: WorkGroup) -> str:
    return _format_line(group.primary, group.linked)


def _item_ui_dict(item: TrackedItem) -> dict:
    return {
        "id": item.id,
        "source": item.source,
        "key": item.key,
        "short_key": _short_key(item),
        "url": item.url,
        "summary": item.summary,
        "remote_status": item.remote_status,
        "display_status": ui_status_label(item),
        "action": item.action,
        "issue_type": item.issue_type,
        "epic": is_jira_epic(item),
        "cue": cue_dict(item.action, item.reasons),
        "reasons": list(item.reasons),
        "unread": is_unread(item),
        "state_changed_at": item.state_changed_at,
    }


def _group_ui_dict(group: WorkGroup) -> dict:
    primary = _item_ui_dict(group.primary)
    status_item = next((m for m in group.members if _is_open_github(m)), group.primary)
    return {
        "action": group.action,
        "unread": group.is_unread(),
        "state_changed_at": group.state_changed_at,
        "cue": primary.get("cue"),
        "status_item_id": status_item.id,
        "primary": primary,
        "linked": [_item_ui_dict(m) for m in group.linked],
    }


def _group_matches_source(group: WorkGroup, source: str) -> bool:
    if source in ("", "both", "all"):
        return True
    want = source.casefold()
    # "github" = PRs + Issues; github_pr / github_issue are fine-grained
    if want == "github":
        return any(
            (m.source or "").casefold() in ("github_pr", "github_issue")
            for m in group.members
        )
    return any((m.source or "").casefold() == want for m in group.members)


def build_ui_digest(
    store: TrackStore,
    *,
    view: str = "all",
    source: str = "both",
    since_read: bool = False,
    generated_at: str | None = None,
) -> dict:
    """JSON payload for the local web UI.

    view: actionable | all | everything | pending | blocked | done
    source: both | github | jira
    """
    generated_at = generated_at or _iso_now()
    view = (view or "all").casefold()
    source = (source or "both").casefold()

    if view == "actionable":
        section_keys = [("Actionable", "actionable")]
    elif view == "pending":
        section_keys = [("Pending", "pending")]
    elif view == "blocked":
        section_keys = [("Blocked", "blocked")]
    elif view == "done":
        section_keys = [("Recently done", "done")]
    elif view == "everything":
        section_keys = [
            ("Actionable", "actionable"),
            ("Pending", "pending"),
            ("Blocked", "blocked"),
            ("Recently done", "done"),
        ]
    else:
        # all = active sections (not recently done)
        section_keys = [
            ("Actionable", "actionable"),
            ("Pending", "pending"),
            ("Blocked", "blocked"),
        ]

    sections = []
    for title, action in section_keys:
        groups = _section_groups(store, action)
        groups = [g for g in groups if _group_matches_source(g, source)]
        if since_read:
            groups = [g for g in groups if g.is_unread()]
        sections.append(
            {
                "id": action,
                "title": title,
                "count": len(groups),
                "groups": [_group_ui_dict(g) for g in groups],
            }
        )

    return {
        "generated_at": generated_at,
        "store_updated_at": store.updated_at,
        "view": view,
        "source": source,
        "since_read": since_read,
        "sections": sections,
    }


def build_digest_markdown(store: TrackStore, *, generated_at: str | None = None) -> str:
    generated_at = generated_at or _iso_now()
    lines = [
        "# Status Overlook",
        "",
        f"Generated: {generated_at}",
        f"Store updated: {store.updated_at or '—'}",
        "",
        "_● = changed since last mark-read_",
        "",
    ]
    for title, action in (
        ("Actionable", "actionable"),
        ("Pending", "pending"),
        ("Blocked", "blocked"),
        ("Recently done", "done"),
    ):
        groups = _section_groups(store, action)
        lines.append(f"## {title}")
        lines.append("")
        if not groups:
            lines.append("_None_")
        else:
            for group in groups:
                lines.append(_format_group_line(group))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_digest_json(store: TrackStore, *, generated_at: str | None = None) -> dict:
    generated_at = generated_at or _iso_now()
    # Map member id -> primary id for active groups
    primary_of: dict[str, str] = {}
    linked_of: dict[str, list[str]] = {}
    for group in build_work_groups(store):
        primary_of[group.primary.id] = group.primary.id
        linked_of[group.primary.id] = [m.id for m in group.linked]
        for m in group.linked:
            primary_of[m.id] = group.primary.id

    items = []
    for item in sorted(store.items.values(), key=lambda i: i.id):
        group_primary_id = primary_of.get(item.id)
        row = {
            "id": item.id,
            "source": item.source,
            "key": item.key,
            "url": item.url,
            "summary": item.summary,
            "remote_status": item.remote_status,
            "lifecycle": item.lifecycle,
            "action": item.action,
            "blocked": item.blocked,
            "issue_type": item.issue_type,
            "pr_link": item.pr_link,
            "cue": cue_dict(item.action, item.reasons),
            "reasons": item.reasons,
            "state_changed_at": item.state_changed_at,
            "last_read_at": item.last_read_at,
            "unread": is_unread(item),
            "pinned": item.pinned,
            "group_primary_id": group_primary_id,
            "linked_ids": linked_of.get(item.id, []),
        }
        items.append(row)
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "store_updated_at": store.updated_at,
        "items": items,
    }


def write_digests(store: TrackStore) -> tuple[Path, Path]:
    ensure_private_dir(cache_dir())
    generated_at = _iso_now()
    md_path = digest_md_path()
    json_path = digest_json_path()
    write_private_text(md_path, build_digest_markdown(store, generated_at=generated_at))
    write_private_text(
        json_path,
        json.dumps(build_digest_json(store, generated_at=generated_at), indent=2) + "\n",
    )
    return md_path, json_path


def mark_read(
    store: TrackStore,
    *,
    ids: list[str] | None = None,
    all_items: bool = False,
) -> int:
    """Set last_read_at. Default: all active items. Return count updated."""
    now = _iso(_utcnow())
    if all_items:
        chosen = list(store.items.values())
    elif ids:
        chosen = [store.items[i] for i in ids if i in store.items]
    else:
        chosen = [i for i in store.items.values() if i.lifecycle == "active"]
    for item in chosen:
        item.last_read_at = now
    return len(chosen)
