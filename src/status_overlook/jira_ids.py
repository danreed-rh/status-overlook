"""Small Jira id/JQL hygiene helpers (no network)."""

from __future__ import annotations

import re

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_CUSTOMFIELD_RE = re.compile(r"^customfield_\d+$")


def is_jira_key(key: str) -> bool:
    return bool(_JIRA_KEY_RE.match(key or ""))


def qa_field_to_jql(qa_contact_field: str) -> str | None:
    """Map config field id to JQL term, or None if not an allowed customfield_*."""
    cf = (qa_contact_field or "").strip()
    if not _CUSTOMFIELD_RE.match(cf):
        return None
    return f"cf[{cf.removeprefix('customfield_')}]"


def safe_jql_status(status: str) -> str | None:
    """Reject status names that would break out of a double-quoted JQL string."""
    s = status or ""
    if not s or any(c in s for c in '"\\\n\r'):
        return None
    return s
