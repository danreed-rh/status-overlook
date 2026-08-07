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


def _user_involved(pr: GitHubPrSnapshot) -> bool:
    return pr.author_is_user or pr.assignee_is_user


def classify_github(
    pr: GitHubPrSnapshot,
    cfg: ClassifyConfig | None = None,
) -> ClassificationResult:
    """Classify a GitHub PR for track lifecycle and action state.

    - merged/closed → done
    - linked Jira blocked → blocked (overrides other states)
    - open + assignee who gave /lgtm or lgtm label (and is not author) → pending
    - open + involved:
        - unresolved reviews or CI failures → actionable
        - author + actionable label (default: lgtm) → actionable (ready to merge)
        - author draft → actionable
        - otherwise → pending
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
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("github_pr_not_open",),
        )

    if pr.linked_jira_blocked:
        reasons.append("github_linked_jira_blocked")
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.BLOCKED,
            reasons=tuple(reasons),
            blocked=True,
        )

    if not _user_involved(pr):
        return ClassificationResult(
            lifecycle=Lifecycle.UNTRACKED,
            action=ActionState.IGNORE,
            reasons=("github_not_involved",),
        )

    # Assignee already signed off — waiting on author/merge, not more review work
    if pr.assignee_is_user and not pr.author_is_user and pr.user_gave_lgtm:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.PENDING,
            reasons=("github_assignee_lgtm",),
        )

    has_actionable_label = _label_hit(
        pr.labels, cfg.actionable_labels, cfg.label_match_case_insensitive
    )
    # lgtm-style labels mean "ready to merge" for the author, not for assignees
    author_ready_label = pr.author_is_user and has_actionable_label

    if pr.has_unresolved_reviews:
        reasons.append("github_unresolved_reviews")
    if pr.ci_failed:
        reasons.append("github_ci_failed")
    if author_ready_label:
        reasons.append("github_actionable_label")
    if pr.author_is_user and pr.draft:
        reasons.append("github_author_draft")

    needs_action = bool(
        pr.has_unresolved_reviews
        or pr.ci_failed
        or author_ready_label
        or (pr.author_is_user and pr.draft)
    )

    if needs_action:
        return ClassificationResult(
            lifecycle=Lifecycle.ACTIVE,
            action=ActionState.ACTIONABLE,
            reasons=tuple(reasons),
        )

    reasons.append("github_waiting")
    return ClassificationResult(
        lifecycle=Lifecycle.ACTIVE,
        action=ActionState.PENDING,
        reasons=tuple(reasons),
    )
