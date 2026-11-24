"""Track store load/save and reconcile merge logic (no network)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from status_overlook.fsutil import ensure_private_dir, write_private_text
from status_overlook.paths import data_dir, track_store_path
import status_overlook.state as state_mod

STORE_SCHEMA_VERSION = 1
SourceName = Literal["jira", "github_pr", "github_issue"]
LifecycleName = Literal["active", "done"]


def normalize_source_name(source: str) -> SourceName:
    """Map legacy `github` → `github_pr`."""
    s = (source or "").casefold()
    if s in ("github", "github_pr"):
        return "github_pr"
    if s == "github_issue":
        return "github_issue"
    return "jira"


def normalize_item_id(item_id: str) -> str:
    """Map legacy `github:…` → `github-pr:…`."""
    if item_id.startswith(("github-pr:", "github-issue:", "jira:")):
        return item_id
    if item_id.startswith("github:"):
        return "github-pr:" + item_id[len("github:") :]
    return item_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


@dataclass
class TrackedItem:
    id: str
    source: SourceName
    key: str
    url: str = ""
    summary: str = ""
    remote_status: str = ""
    lifecycle: LifecycleName = "active"
    pinned: bool = False
    first_seen_at: str = ""
    last_seen_at: str = ""
    finished_at: str | None = None
    last_read_at: str | None = None
    # Phase 3 classification
    action: str = ""  # actionable|pending|blocked|done|ignore
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)
    # Jira issuetype name (e.g. Epic, Story); empty for GitHub / unknown
    issue_type: str = ""
    # Jira Git Pull Request field URL, or best linked PR URL for a GitHub Issue
    pr_link: str = ""
    # GitHub PR → linked issue store ids (github-issue:owner/repo#n)
    linked_issue_ids: list[str] = field(default_factory=list)
    state_changed_at: str = ""
    state_fingerprint: str = ""
    remote_updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedItem:
        raw_id = str(data["id"])
        source = normalize_source_name(str(data.get("source") or ""))
        item_id = normalize_item_id(raw_id)
        # If source migrated but id did not (or vice versa), prefer consistent pair.
        if source == "github_pr" and item_id.startswith("github:"):
            item_id = normalize_item_id(item_id)
        if source == "github_issue" and not item_id.startswith("github-issue:"):
            key = str(data.get("key") or "")
            item_id = f"github-issue:{key}" if key else item_id
        item = cls(
            id=item_id,
            source=source,
            key=str(data["key"]),
            url=str(data.get("url") or ""),
            summary=str(data.get("summary") or ""),
            remote_status=str(data.get("remote_status") or ""),
            lifecycle=data.get("lifecycle") or "active",
            pinned=bool(data.get("pinned")),
            first_seen_at=str(data.get("first_seen_at") or ""),
            last_seen_at=str(data.get("last_seen_at") or ""),
            finished_at=data.get("finished_at"),
            last_read_at=data.get("last_read_at"),
            action=str(data.get("action") or ""),
            blocked=bool(data.get("blocked")),
            reasons=list(data.get("reasons") or []),
            issue_type=str(data.get("issue_type") or ""),
            pr_link=str(data.get("pr_link") or ""),
            linked_issue_ids=[str(x) for x in (data.get("linked_issue_ids") or [])],
            state_changed_at=str(data.get("state_changed_at") or ""),
            state_fingerprint=str(data.get("state_fingerprint") or ""),
            remote_updated_at=str(data.get("remote_updated_at") or ""),
        )
        # Migrate the legacy reason-inclusive fingerprint before reconcile can
        # replace remote_status with the discovery-only value. Preserve the
        # existing timestamp so loading/migrating the store never restarts age.
        if item.state_changed_at and not state_mod.is_current_state_fingerprint(
            item.state_fingerprint
        ):
            item.state_fingerprint = state_mod.state_fingerprint(
                action=item.action,
                lifecycle=item.lifecycle,
                remote_status=item.remote_status,
                blocked=item.blocked,
                reasons=item.reasons,
            )
        return item


def _record_visible_state(item: TrackedItem, now_s: str) -> None:
    fingerprint = state_mod.state_fingerprint(
        action=item.action,
        lifecycle=item.lifecycle,
        remote_status=item.remote_status,
        blocked=item.blocked,
        reasons=item.reasons,
    )
    if fingerprint != item.state_fingerprint or not item.state_changed_at:
        item.state_changed_at = now_s
        item.state_fingerprint = fingerprint


@dataclass
class Candidate:
    """Open/assigned work discovered from providers."""

    source: SourceName
    key: str
    url: str = ""
    summary: str = ""
    remote_status: str = ""

    @property
    def id(self) -> str:
        if self.source == "jira":
            return f"jira:{self.key}"
        if self.source == "github_issue":
            return f"github-issue:{self.key}"
        return f"github-pr:{self.key}"


@dataclass
class TrackStore:
    schema_version: int = STORE_SCHEMA_VERSION
    updated_at: str = ""
    items: dict[str, TrackedItem] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
            "items": {k: v.to_dict() for k, v in sorted(self.items.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackStore:
        items_raw = data.get("items") or {}
        items: dict[str, TrackedItem] = {}
        for _k, v in items_raw.items():
            item = TrackedItem.from_dict(v)
            items[item.id] = item
        return cls(
            schema_version=int(data.get("schema_version") or STORE_SCHEMA_VERSION),
            updated_at=str(data.get("updated_at") or ""),
            items=items,
        )


@dataclass
class ReconcileStats:
    added: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    pinned_kept: list[str] = field(default_factory=list)


def load_store(path: Path | None = None) -> TrackStore:
    path = path or track_store_path()
    if not path.is_file():
        return TrackStore()
    data = json.loads(path.read_text(encoding="utf-8"))
    return TrackStore.from_dict(data)


def save_store(store: TrackStore, path: Path | None = None) -> Path:
    path = path or track_store_path()
    ensure_private_dir(path.parent)
    ensure_private_dir(data_dir())
    write_private_text(
        path, json.dumps(store.to_dict(), indent=2, sort_keys=True) + "\n"
    )
    return path


def reconcile(
    store: TrackStore,
    candidates: list[Candidate],
    *,
    pin_ids: set[str] | None = None,
    now: datetime | None = None,
    retention_days: int = 7,
    defer_lifecycle: bool = False,
) -> tuple[TrackStore, ReconcileStats]:
    """Merge provider candidates into the track store.

    - New candidates → active
    - Existing candidates → refresh last_seen / summary
    - Existing done candidates → active unless lifecycle changes are deferred
    - Active items missing from candidates (and not pinned) → done unless
      lifecycle changes are deferred
    - Done items older than retention_days → pruned
    - Pins stay active even if absent from candidates
    """
    now = now or _utcnow()
    now_s = _iso(now)
    pin_ids = pin_ids or set()
    stats = ReconcileStats()

    by_id = {c.id: c for c in candidates}
    # Mark pins
    for item in store.items.values():
        if item.id in pin_ids:
            item.pinned = True

    for cid, cand in by_id.items():
        existing = store.items.get(cid)
        if existing is None:
            store.items[cid] = TrackedItem(
                id=cid,
                source=cand.source,
                key=cand.key,
                url=cand.url,
                summary=cand.summary,
                remote_status=cand.remote_status,
                lifecycle="active",
                pinned=cid in pin_ids,
                first_seen_at=now_s,
                last_seen_at=now_s,
            )
            stats.added.append(cid)
            continue

        existing.summary = cand.summary or existing.summary
        existing.url = cand.url or existing.url
        existing.last_seen_at = now_s
        existing.pinned = existing.pinned or cid in pin_ids
        # IGNORE items stay done while still in discovery (e.g. not assignee)
        if existing.lifecycle == "done" and existing.action == "ignore" and not existing.pinned:
            stats.refreshed.append(cid)
            continue
        if existing.lifecycle == "done" and not defer_lifecycle:
            existing.lifecycle = "active"
            existing.finished_at = None
            _record_visible_state(existing, now_s)
        # Keep the last enriched visible state until enrichment confirms the
        # candidate's current status and classification. Discovery may provide
        # only a provisional status (GitHub PR search, for example, says open).
        stats.refreshed.append(cid)

    if not defer_lifecycle:
        for iid, item in list(store.items.items()):
            if item.lifecycle != "active":
                continue
            if iid in by_id:
                continue
            if item.pinned or iid in pin_ids:
                item.pinned = True
                stats.pinned_kept.append(iid)
                continue
            item.lifecycle = "done"
            item.finished_at = now_s
            item.last_seen_at = now_s
            _record_visible_state(item, now_s)
            stats.finished.append(iid)

    cutoff = now - timedelta(days=retention_days)
    for iid, item in list(store.items.items()):
        if item.lifecycle != "done":
            continue
        if (
            defer_lifecycle
            and iid in by_id
            and (item.action != "ignore" or item.pinned)
        ):
            # A staged full refresh must let enrichment decide whether a
            # rediscovered item is active before retention can remove it.
            continue
        finished = parse_iso(item.finished_at)
        if finished is not None and finished < cutoff:
            del store.items[iid]
            stats.pruned.append(iid)

    store.updated_at = now_s
    store.schema_version = STORE_SCHEMA_VERSION
    return store, stats
