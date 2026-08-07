"""Track store load/save and reconcile merge logic (no network)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from status_overlook.paths import data_dir, track_store_path

STORE_SCHEMA_VERSION = 1
SourceName = Literal["jira", "github"]
LifecycleName = Literal["active", "done"]


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
    state_changed_at: str = ""
    state_fingerprint: str = ""
    remote_updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedItem:
        return cls(
            id=str(data["id"]),
            source=data["source"],
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
            state_changed_at=str(data.get("state_changed_at") or ""),
            state_fingerprint=str(data.get("state_fingerprint") or ""),
            remote_updated_at=str(data.get("remote_updated_at") or ""),
        )


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
        return f"github:{self.key}"


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
        items = {k: TrackedItem.from_dict(v) for k, v in items_raw.items()}
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
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure data_dir exists even if store path overridden oddly
    data_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def reconcile(
    store: TrackStore,
    candidates: list[Candidate],
    *,
    pin_ids: set[str] | None = None,
    now: datetime | None = None,
    retention_days: int = 7,
) -> tuple[TrackStore, ReconcileStats]:
    """Merge provider candidates into the track store.

    - New candidates → active
    - Existing candidates → refresh last_seen / summary
    - Active items missing from candidates (and not pinned) → done
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
        existing.remote_status = cand.remote_status or existing.remote_status
        existing.last_seen_at = now_s
        existing.pinned = existing.pinned or cid in pin_ids
        # IGNORE items stay done while still in discovery (e.g. Testing assignee-only)
        if existing.lifecycle == "done" and existing.action == "ignore" and not existing.pinned:
            stats.refreshed.append(cid)
            continue
        if existing.lifecycle == "done":
            existing.lifecycle = "active"
            existing.finished_at = None
        stats.refreshed.append(cid)

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
        stats.finished.append(iid)

    cutoff = now - timedelta(days=retention_days)
    for iid, item in list(store.items.items()):
        if item.lifecycle != "done":
            continue
        finished = parse_iso(item.finished_at)
        if finished is not None and finished < cutoff:
            del store.items[iid]
            stats.pruned.append(iid)

    store.updated_at = now_s
    store.schema_version = STORE_SCHEMA_VERSION
    return store, stats
