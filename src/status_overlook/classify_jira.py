"""Pure Jira classification rules."""

from __future__ import annotations

from status_overlook.models import (
    ActionState,
    ClassificationResult,
    ClassifyConfig,
    JiraIssueSnapshot,
    Lifecycle,
)


def is_jira_blocked(issue: JiraIssueSnapshot, cfg: ClassifyConfig | None = None) -> bool:
    """Blocked if status, label, Flagged, or unresolved is-blocked-by link (any one)."""
    cfg = cfg or ClassifyConfig()
    if issue.flagged:
        return True
    if issue.blocked_by_unresolved:
        return True
    if cfg.status_in(issue.status, cfg.status_blocked):
        return True
    if cfg.label_in(issue.labels, cfg.blocked_labels):
        return True
    return False


def _is_epic(issue: JiraIssueSnapshot) -> bool:
    return issue.issue_type.casefold() == "epic"


def classify_jira(
    issue: JiraIssueSnapshot,
    cfg: ClassifyConfig | None = None,
) -> ClassificationResult:
    """Classify a Jira issue for track lifecycle and action state.

    - Done statuses → done
    - Blocked (status / label / Flagged / unresolved is-blocked-by) → blocked
    - Epic + assignee: pending until all children are done; then actionable
    - Testing + QA contact → actionable
    - Testing + assignee only → untracked (not actionable, not pending)
    - Review + assignee + linked PR merged → actionable (move to Testing / resolve)
    - Review + assignee (otherwise) → pending
    - Active + assignee → actionable
    """
    cfg = cfg or ClassifyConfig()
    blocked = is_jira_blocked(issue, cfg)
    reasons: list[str] = []

    if cfg.status_in(issue.status, cfg.status_done):
        return ClassificationResult(
            lifecycle=Lifecycle.DONE,
            action=ActionState.DONE,
            reasons=("jira_status_done",),
            blocked=blocked,
        )

    # Blocked overrides action/pending for any remaining status
    if blocked and (issue.assignee_is_user or issue.qa_contact_is_user):
        if issue.flagged:
            reasons.append("jira_flagged")
        if issue.blocked_by_unresolved:
            reasons.append("jira_blocked_by_unresolved")
        if cfg.status_in(issue.status, cfg.status_blocked):
            reasons.append("jira_status_blocked")
        if cfg.label_in(issue.labels, cfg.blocked_labels):
            reasons.append("jira_label_blocked")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.BLOCKED,
            reasons=tuple(reasons) or ("jira_blocked",),
            blocked=True,
        )

    # Epics: roll up child lifecycle instead of normal active/review rules
    if _is_epic(issue) and issue.assignee_is_user:
        if issue.epic_children_all_done is True:
            return ClassificationResult(
                lifecycle=Lifecycle.ACTIVE,
                action=ActionState.ACTIONABLE,
                reasons=("jira_epic_children_done",),
                blocked=False,
            )
        reason = (
            "jira_epic_children_open"
            if issue.epic_children_all_done is False
            else "jira_epic_children_unknown"
        )
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=(reason,),
            blocked=False,
        )

    in_testing = cfg.status_in(issue.status, cfg.status_testing)
    in_review = cfg.status_in(issue.status, cfg.status_review)
    in_active = cfg.status_in(issue.status, cfg.status_active)

    if in_testing:
        if issue.qa_contact_is_user:
            reasons.append("jira_testing_qa_contact")
            return ClassificationResult(
                lifecycle=Lifecycle.ACTIVE,
                action=ActionState.ACTIONABLE,
                reasons=tuple(reasons),
                blocked=False,
            )
        # Assignee-only in Testing: not actionable, not pending
        if issue.assignee_is_user:
            return ClassificationResult(
                lifecycle=Lifecycle.UNTRACKED,
                action=ActionState.IGNORE,
                reasons=("jira_testing_assignee_only",),
                blocked=False,
            )
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("jira_testing_not_involved",),
            blocked=False,
        )

    if not issue.assignee_is_user:
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("jira_not_assignee",),
            blocked=False,
        )

    if in_review:
        if issue.linked_pr_merged is True:
            return ClassificationResult(
                lifecycle=Lifecycle.ACTIVE,
                action=ActionState.ACTIONABLE,
                reasons=("jira_review_pr_merged",),
                blocked=False,
            )
        reasons.append("jira_in_review")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=tuple(reasons),
            blocked=False,
        )

    if in_active:
        reasons.append("jira_active_assignee")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.ACTIONABLE,
            reasons=tuple(reasons),
            blocked=False,
        )

    reasons.append("jira_unknown_status_assignee")
    return ClassificationResult(
        lifecycle=Lifecycle.ACTIVE,
        action=ActionState.PENDING,
        reasons=tuple(reasons),
        blocked=False,
    )
