"""Visible-state fingerprints shared by store migration and enrichment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from status_overlook.cues import cue_for

_FINGERPRINT_PREFIX = "visible-v2:"


def state_fingerprint(
    *,
    action: str,
    lifecycle: str,
    remote_status: str,
    blocked: bool = False,
    reasons: Sequence[str] = (),
) -> str:
    """Fingerprint what the user sees, excluding internal reason-only changes.

    ``blocked`` remains accepted for compatibility, but its visible effect is
    already represented by ``action`` and the cue derived from ``reasons``.
    """
    del blocked
    cue = cue_for(action, reasons)
    payload = json.dumps(
        [lifecycle, action, remote_status, cue.id if cue else ""],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{_FINGERPRINT_PREFIX}{digest}"


def is_current_state_fingerprint(value: str) -> bool:
    fingerprint = value or ""
    if not fingerprint.startswith(_FINGERPRINT_PREFIX):
        return False
    digest = fingerprint[len(_FINGERPRINT_PREFIX) :]
    return len(digest) == 16 and all(char in "0123456789abcdef" for char in digest)
