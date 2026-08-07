"""Pure GitHub PR classification rules."""

from __future__ import annotations

from status_overlook.models import (
    ActionState,
    ClassificationResult,
    ClassifyConfig,
    GitHubPrSnapshot,
    Lifecycle,
)


def _label_hit(labels: tuple[str, ...], wanted: tuple[str, ...], insensitive: bool) -> bool:
    if insensitive:
        have = {x.casefold() for x in labels}
        return any(w.casefold() in have for w in wanted)
    return any(w in labels for w in wanted)


def classify_github(
    pr: GitHubPrSnapshot,
    cfg: ClassifyConfig | None = None,
) -> ClassificationResult:
    """Classify a GitHub PR for track lifecycle and action state.

    Defaults (Gate 1 draft):
    - merged/closed → done
    - linked Jira blocked → pending (overrides LGTM / other actionable)
    - actionable if: assignee + not draft; or author + draft; or actionable label on open PR
    - else open author + not draft → pending
    - else ignore
    """
    cfg = cfg or ClassifyConfig()
    reasons: list[str] = []

    if pr.merged or pr.state.casefold() == "closed":
        return ClassificationResult(
            lifecycle=Lifecycle.DONE,
            action=ActionState.DONE,
            reasons=("github_pr_closed_or_merged",),
        )

    if pr.state.casefold() != "open":
        return ClassificationResult(
            lifecycle=Lifecycle.DONE,
            action=ActionState.IGNORE,
            reasons=("github_pr_not_open",),
        )

    # Highest priority override
    if pr.linked_jira_blocked:
        reasons.append("github_linked_jira_blocked")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=tuple(reasons),
            blocked=True,
        )

    has_action_label = _label_hit(
        pr.labels, cfg.actionable_labels, cfg.label_match_case_insensitive
    )

    actionable = False
    if pr.assignee_is_user and not pr.draft:
        actionable = True
        reasons.append("github_assignee_not_draft")
    if pr.author_is_user and pr.draft:
        actionable = True
        reasons.append("github_author_draft")
    if has_action_label:
        actionable = True
        reasons.append("github_actionable_label")

    if actionable:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.ACTIONABLE,
            reasons=tuple(reasons),
        )

    if pr.author_is_user and not pr.draft:
        reasons.append("github_author_waiting")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=tuple(reasons),
        )

    if pr.assignee_is_user and pr.draft:
        # Assigned draft: treat as pending (not in the explicit actionable draft=author rule)
        reasons.append("github_assignee_draft")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=tuple(reasons),
        )

    return ClassificationResult(
        lifecycle=Lifecycle.UNTRACKED,
        action=ActionState.IGNORE,
        reasons=("github_not_involved",),
    )
