"""Pure GitHub Issue classification rules."""

from __future__ import annotations

from status_overlook.models import (
    ActionState,
    ClassificationResult,
    ClassifyConfig,
    GitHubIssueSnapshot,
    Lifecycle,
)


def classify_github_issue(
    issue: GitHubIssueSnapshot,
    cfg: ClassifyConfig | None = None,
) -> ClassificationResult:
    """Classify a GitHub Issue for track lifecycle and action state.

    - closed → done
    - blocked label or linked Jira blocked → blocked
    - open + linked PR still open → pending (Review analog)
    - open + linked PR merged (none open) → actionable
    - open + assignee, no open linked PR → actionable
    - open but not assignee → ignore
    """
    cfg = cfg or ClassifyConfig()

    if issue.state.casefold() != "open":
        return ClassificationResult(
            lifecycle=Lifecycle.DONE,
            action=ActionState.DONE,
            reasons=("github_issue_closed",),
        )

    if issue.linked_jira_blocked:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.BLOCKED,
            reasons=("github_issue_jira_blocked",),
            blocked=True,
        )

    if cfg.label_in(issue.labels, cfg.blocked_labels):
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.BLOCKED,
            reasons=("github_issue_blocked",),
            blocked=True,
        )

    if not issue.assignee_is_user:
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("github_issue_not_assignee",),
        )

    if issue.linked_pr_open:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=("github_issue_pr_open",),
        )

    if issue.linked_pr_merged is True:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.ACTIONABLE,
            reasons=("github_issue_pr_merged",),
        )

    return ClassificationResult(
        lifecycle=Lifecycle.ACTIVE,
        action=ActionState.ACTIONABLE,
        reasons=("github_issue_open",),
    )
