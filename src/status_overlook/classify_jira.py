"""Pure Jira classification rules."""

from __future__ import annotations

from status_overlook.models import (
    ActionState,
    ClassificationResult,
    ClassifyConfig,
    JiraIssueSnapshot,
    Lifecycle,
)


def _is_blocked(issue: JiraIssueSnapshot, cfg: ClassifyConfig) -> bool:
    if issue.blocked:
        return True
    return cfg.status_in(issue.status, cfg.status_blocked)


def classify_jira(
    issue: JiraIssueSnapshot,
    cfg: ClassifyConfig | None = None,
) -> ClassificationResult:
    """Classify a Jira issue for track lifecycle and action state.

    Defaults (Gate 1 draft):
    - Done statuses → lifecycle done
    - Testing + QA contact → actionable (even if also assignee)
    - Testing + assignee (not QA) → actionable
    - Testing + neither → ignore (do not actively track for action)
    - Review + assignee → pending
    - Active status + assignee + not blocked → actionable
    - Active/Review + assignee + blocked → pending
    - Otherwise ignore
    """
    cfg = cfg or ClassifyConfig()
    blocked = _is_blocked(issue, cfg)
    reasons: list[str] = []

    if cfg.status_in(issue.status, cfg.status_done):
        return ClassificationResult(
            lifecycle=Lifecycle.DONE,
            action=ActionState.DONE,
            reasons=("jira_status_done",),
            blocked=blocked,
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
                blocked=blocked,
            )
        if issue.assignee_is_user:
            reasons.append("jira_testing_assignee")
            return ClassificationResult(
                lifecycle=Lifecycle.ACTIVE,
                action=ActionState.ACTIONABLE,
                reasons=tuple(reasons),
                blocked=blocked,
            )
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("jira_testing_not_involved",),
            blocked=blocked,
        )

    if not issue.assignee_is_user:
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("jira_not_assignee",),
            blocked=blocked,
        )

    # Assignee from here
    if blocked:
        reasons.append("jira_blocked")
        if in_review or in_active:
            return ClassificationResult(
                lifecycle=Lifecycle.ACTIVE,
                action=ActionState.PENDING,
                reasons=tuple(reasons),
                blocked=True,
            )

    if in_review:
        reasons.append("jira_in_review")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=tuple(reasons),
            blocked=blocked,
        )

    if in_active:
        reasons.append("jira_active_assignee")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.ACTIONABLE,
            reasons=tuple(reasons),
            blocked=blocked,
        )

    # Unknown status but assigned — track as pending so it is not lost
    reasons.append("jira_unknown_status_assignee")
    return ClassificationResult(
        lifecycle=Lifecycle.ACTIVE,
        action=ActionState.PENDING,
        reasons=tuple(reasons),
        blocked=blocked,
    )
