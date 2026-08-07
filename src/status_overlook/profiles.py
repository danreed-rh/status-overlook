"""Example classification profiles (field IDs / status names). Not loaded automatically."""

from __future__ import annotations

from status_overlook.models import ClassifyConfig

# Portable defaults used when config is empty
DEFAULT = ClassifyConfig()

# Example only — consumers copy field IDs into their config; not hard-wired at runtime
RHOAIENG_EXAMPLE = {
    "qa_contact_field": "customfield_10470",
    "pr_link_field": "customfield_10875",
    "status_active": ["New", "In Progress"],
    "status_review": ["Review"],
    "status_testing": ["Testing"],
    "status_done": ["Resolved", "Closed", "Done"],
    "status_blocked": ["Blocked"],
    "blocked_labels": ["blocked"],
    # Providers: flagged = Flagged impediment is not empty
    "actionable_labels": ["lgtm"],
}
