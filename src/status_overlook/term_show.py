"""Compact colored terminal digest for `status-overlook show`."""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timezone

from status_overlook.cues import cue_for
from status_overlook.digest import (
    WorkGroup,
    _section_groups,
    is_jira_epic,
    is_unread,
    status_age_label,
)
from status_overlook.store import TrackStore, TrackedItem, parse_iso

# ANSI
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"

_SECTION_STYLE = {
    "actionable": (_BOLD + _YELLOW, "ACTIONABLE"),
    "blocked": (_BOLD + _MAGENTA, "BLOCKED"),
    "pending": (_BOLD + _CYAN, "PENDING"),
    "done": (_DIM + _GREEN, "RECENTLY DONE"),
}


def use_color(*, stream=None, force: bool | None = None) -> bool:
    """True when ANSI color should be used."""
    if force is not None:
        return force
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    stream = stream or sys.stdout
    return bool(getattr(stream, "isatty", lambda: False)())


def terminal_width(fallback: int = 72) -> int:
    try:
        return max(40, shutil.get_terminal_size(fallback=(fallback, 24)).columns)
    except OSError:
        return fallback


def short_key(item: TrackedItem) -> str:
    """Human-facing key: GitHub org/repo#n → #n; Jira key unchanged."""
    key = item.key or item.id
    if item.source in ("github_pr", "github_issue") and "#" in key:
        return "#" + key.rsplit("#", 1)[-1]
    return key


def truncate(text: str, width: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def relative_changed(iso: str, *, now: datetime | None = None) -> str:
    """Short relative time for verbose mode."""
    dt = parse_iso(iso)
    if dt is None:
        return iso or "—"
    now = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "in future"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    days = secs // 86400
    if days < 14:
        return f"{days}d ago"
    return dt.strftime("%Y-%m-%d")


def _paint(text: str, style: str, *, color: bool) -> str:
    if not color or not style:
        return text
    return f"{style}{text}{_RESET}"


def _format_item(
    item: TrackedItem,
    *,
    width: int,
    color: bool,
    verbose: bool,
    linked: list[TrackedItem] | None = None,
    unread: bool | None = None,
) -> list[str]:
    linked = linked or []
    if unread is None:
        unread = is_unread(item) or any(is_unread(m) for m in linked)
    epic = is_jira_epic(item)
    bullet = "●" if unread else " "
    key = short_key(item)
    status = item.remote_status or "—"
    age = status_age_label(item.state_changed_at)
    if age:
        status = f"{status} · {age}"
    cue = cue_for(item.action, item.reasons)
    cue_label = cue.label if cue else ""
    epic_tag = "[Epic]"
    link_bits = [f"↔ {short_key(peer)}" for peer in linked]
    link_note = "  ".join(link_bits)

    # Line 1: "● KEY  [Epic]  ↔ #n  status  Cue"
    parts = [f"{bullet} {key}"]
    if epic:
        parts.append(epic_tag)
    if link_note:
        parts.append(link_note)
    prefix = "  ".join(parts)
    suffix_bits = [status]
    if cue_label:
        suffix_bits.append(cue_label)
    suffix = "  ".join(suffix_bits)
    line1_plain = f"{prefix}  {suffix}"
    if len(line1_plain) > width:
        avail = max(8, width - len(prefix) - 2)
        suffix = truncate(suffix, avail)
        line1_plain = f"{prefix}  {suffix}"

    if color:
        b = _paint("●", _BOLD + _YELLOW, color=True) if unread else " "
        k = _paint(key, _BOLD, color=True)
        s = _paint(status, _DIM, color=True)
        chunks = [f"{b} {k}"]
        if epic:
            chunks.append(_paint(epic_tag, _BOLD + _BLUE, color=True))
        if link_note:
            chunks.append(_paint(link_note, _DIM, color=True))
        chunks.append(s)
        if cue_label:
            chunks.append(_paint(cue_label, _DIM, color=True))
        line1 = "  ".join(chunks)
    else:
        line1 = line1_plain

    lines = [line1]
    summary = truncate(item.summary or "", max(8, width - 2))
    lines.append(f"  {summary}" if summary else "  —")

    for peer in linked:
        peer_status = peer.remote_status or "—"
        peer_age = status_age_label(peer.state_changed_at)
        age_note = f" · {peer_age}" if peer_age else ""
        peer_line = f"  ↔ {short_key(peer)}  {peer_status}{age_note}"
        if verbose and peer.url:
            peer_line = f"{peer_line}  {peer.url}"
        lines.append(_paint(f"  {truncate(peer_line.strip(), max(8, width - 2))}", _DIM, color=color))

    if verbose:
        bits: list[str] = []
        if item.reasons:
            bits.append(", ".join(item.reasons))
        detail = " · ".join(bits) if bits else ""
        if detail:
            lines.append(_paint(f"  {truncate(detail, max(8, width - 2))}", _DIM, color=color))
        meta = item.key
        if item.url:
            meta = f"{meta}  {item.url}"
        lines.append(_paint(f"  {truncate(meta, max(8, width - 2))}", _DIM, color=color))
    return lines


def _format_group(
    group: WorkGroup,
    *,
    width: int,
    color: bool,
    verbose: bool,
) -> list[str]:
    return _format_item(
        group.primary,
        width=width,
        color=color,
        verbose=verbose,
        linked=group.linked,
        unread=group.is_unread(),
    )


def format_terminal_digest(
    store: TrackStore,
    *,
    width: int | None = None,
    color: bool | None = None,
    verbose: bool = False,
    since_read: bool = False,
    section: str | None = None,
    generated_at: str | None = None,
) -> str:
    """Render a narrow-friendly digest for the terminal."""
    width = width or terminal_width()
    if color is None:
        color = use_color()
    now_s = generated_at or datetime.now(timezone.utc).strftime("%H:%MZ")
    # Prefer clock if full ISO passed
    if generated_at and "T" in generated_at:
        now_s = generated_at.split("T", 1)[1][:5] + "Z"

    header = f"Status Overlook · {now_s} · ● = unread"
    out: list[str] = [_paint(header, _BOLD, color=color), ""]

    sections = (
        [("Actionable", "actionable"), ("Pending", "pending"), ("Blocked", "blocked"), ("Recently done", "done")]
        if not section
        else [(section.replace("_", " ").title(), section)]
    )

    any_section = False
    for _title, action in sections:
        groups = _section_groups(store, action)
        if since_read:
            groups = [g for g in groups if g.is_unread()]
        if not groups:
            continue
        any_section = True
        style, label = _SECTION_STYLE.get(action, (_BOLD, action.upper()))
        heading = f"{label} ({len(groups)})"
        rule = "─" * min(width, max(14, len(heading) + 2))
        out.append(_paint(heading, style, color=color))
        out.append(_paint(rule, _DIM, color=color))
        for i, group in enumerate(groups):
            if i:
                out.append("")
            out.extend(
                _format_group(group, width=width, color=color, verbose=verbose)
            )
        out.append("")

    if not any_section:
        out.append(_paint("(no items)", _DIM, color=color))
        out.append("")

    return "\n".join(out).rstrip() + "\n"
