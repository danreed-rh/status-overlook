"""Present-time next-action / blocked-reason cues (pure, no I/O).

Cue ids are a closed vocabulary derived from classification `reasons`.
They are not action states and are not persisted on the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Cue:
    id: str
    label: str
    kind: str  # actionable | pending | blocked


_CUES: dict[str, Cue] = {
    "fix_ci": Cue("fix_ci", "Fix CI", "actionable"),
    "address_review": Cue("address_review", "Address review", "actionable"),
    "merge": Cue("merge", "Ready to merge", "actionable"),
    "review": Cue("review", "Review", "actionable"),
    "test": Cue("test", "Test", "actionable"),
    "follow_up": Cue("follow_up", "Follow up", "actionable"),
    "develop": Cue("develop", "Develop", "actionable"),
    "wait_author": Cue("wait_author", "Waiting on author", "pending"),
    "signed_off": Cue("signed_off", "Signed off", "pending"),
    "wait_pr": Cue("wait_pr", "Waiting on PR", "pending"),
    "wait_children": Cue("wait_children", "Waiting on children", "pending"),
    "wait_review": Cue("wait_review", "Waiting for review", "pending"),
    "wait_test": Cue("wait_test", "Testing", "pending"),
    "waiting": Cue("waiting", "Waiting", "pending"),
    "blocked_by": Cue("blocked_by", "Blocked by issue", "blocked"),
    "flagged": Cue("flagged", "Flagged", "blocked"),
    "jira_blocked": Cue("jira_blocked", "Linked Jira blocked", "blocked"),
    "blocked_status": Cue("blocked_status", "Status blocked", "blocked"),
    "blocked_label": Cue("blocked_label", "Blocked label", "blocked"),
}

# First matching reason in this order wins for that action kind.
_PRIORITY: dict[str, tuple[tuple[str, str], ...]] = {
    "actionable": (
        ("github_ci_failed", "fix_ci"),
        ("github_unresolved_reviews", "address_review"),
        ("github_actionable_label", "merge"),
        ("github_assignee_to_review", "review"),
        ("jira_testing_qa_contact", "test"),
        ("jira_review_pr_merged", "follow_up"),
        ("github_issue_pr_merged", "follow_up"),
        ("jira_epic_children_done", "follow_up"),
        ("jira_active_assignee", "develop"),
        ("github_issue_open", "develop"),
        ("github_author_draft", "develop"),
    ),
    "pending": (
        ("github_assignee_waiting_on_author", "wait_author"),
        ("github_assignee_threads_unknown", "wait_author"),
        ("github_assignee_lgtm", "signed_off"),
        ("github_issue_pr_open", "wait_pr"),
        ("jira_epic_children_open", "wait_children"),
        ("jira_epic_children_unknown", "wait_children"),
        ("jira_in_review", "wait_review"),
        ("jira_testing_assignee_only", "wait_test"),
        ("github_waiting", "wait_review"),
        ("jira_unknown_status_assignee", "waiting"),
    ),
    "blocked": (
        ("jira_blocked_by_unresolved", "blocked_by"),
        ("jira_flagged", "flagged"),
        ("github_linked_jira_blocked", "jira_blocked"),
        ("github_issue_jira_blocked", "jira_blocked"),
        ("jira_status_blocked", "blocked_status"),
        ("jira_label_blocked", "blocked_label"),
        ("github_issue_blocked", "blocked_label"),
    ),
}


def cue_for(action: str, reasons: Sequence[str] | None) -> Cue | None:
    """Map action + reason codes to a display cue. Unknown / done / ignore → None."""
    kind = (action or "").casefold()
    table = _PRIORITY.get(kind)
    if not table:
        return None
    have = set(reasons or ())
    if not have:
        return None
    for reason, cue_id in table:
        if reason in have:
            return _CUES[cue_id]
    return None


def cue_dict(action: str, reasons: Sequence[str] | None) -> dict[str, str] | None:
    cue = cue_for(action, reasons)
    if cue is None:
        return None
    return {"id": cue.id, "label": cue.label, "kind": cue.kind}
