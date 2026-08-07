"""Emit human/agent digests from the track store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from status_overlook.paths import cache_dir, digest_json_path, digest_md_path
from status_overlook.store import TrackStore, TrackedItem, _iso, _utcnow, parse_iso


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _section_items(store: TrackStore, action: str) -> list[TrackedItem]:
    if action == "done":
        items = [
            i
            for i in store.items.values()
            if i.lifecycle == "done" or i.action == "done"
        ]
    else:
        items = [
            i
            for i in store.items.values()
            if i.lifecycle == "active" and i.action == action
        ]
    items.sort(key=lambda i: (i.state_changed_at or "", i.id), reverse=True)
    return items


def _format_line(item: TrackedItem) -> str:
    unread = " ●" if is_unread(item) else ""
    reasons = f" ({', '.join(item.reasons)})" if item.reasons else ""
    link = f" — {item.url}" if item.url else ""
    changed = item.state_changed_at or "—"
    return (
        f"- [{item.action or '?'}]{unread} **{item.key}** [{item.remote_status}] "
        f"{item.summary}{reasons}  \n"
        f"  state_changed: {changed}{link}"
    )


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
        ("Blocked", "blocked"),
        ("Pending", "pending"),
        ("Recently done", "done"),
    ):
        items = _section_items(store, action)
        lines.append(f"## {title}")
        lines.append("")
        if not items:
            lines.append("_None_")
        else:
            for item in items:
                lines.append(_format_line(item))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_digest_json(store: TrackStore, *, generated_at: str | None = None) -> dict:
    generated_at = generated_at or _iso_now()
    items = []
    for item in sorted(store.items.values(), key=lambda i: i.id):
        items.append(
            {
                "id": item.id,
                "source": item.source,
                "key": item.key,
                "url": item.url,
                "summary": item.summary,
                "remote_status": item.remote_status,
                "lifecycle": item.lifecycle,
                "action": item.action,
                "blocked": item.blocked,
                "reasons": item.reasons,
                "state_changed_at": item.state_changed_at,
                "last_read_at": item.last_read_at,
                "unread": is_unread(item),
                "pinned": item.pinned,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "store_updated_at": store.updated_at,
        "items": items,
    }


def write_digests(store: TrackStore) -> tuple[Path, Path]:
    cache_dir().mkdir(parents=True, exist_ok=True)
    generated_at = _iso_now()
    md_path = digest_md_path()
    json_path = digest_json_path()
    md_path.write_text(build_digest_markdown(store, generated_at=generated_at), encoding="utf-8")
    json_path.write_text(
        json.dumps(build_digest_json(store, generated_at=generated_at), indent=2) + "\n",
        encoding="utf-8",
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
