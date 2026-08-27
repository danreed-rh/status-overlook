from status_overlook.classify_github_issue import classify_github_issue
from status_overlook.models import (
    ActionState,
    ClassifyConfig,
    GitHubIssueSnapshot,
    Lifecycle,
)


def _issue(**kwargs) -> GitHubIssueSnapshot:
    base = dict(
        repo="org/repo",
        number=1,
        state="open",
        assignee_is_user=True,
        labels=(),
        linked_pr_open=False,
        linked_pr_merged=None,
        linked_jira_blocked=False,
    )
    base.update(kwargs)
    return GitHubIssueSnapshot(**base)


def test_closed_done():
    r = classify_github_issue(_issue(state="closed"))
    assert r.lifecycle == Lifecycle.DONE
    assert r.action == ActionState.DONE
    assert "github_issue_closed" in r.reasons


def test_open_assignee_actionable():
    r = classify_github_issue(_issue())
    assert r.action == ActionState.ACTIONABLE
    assert "github_issue_open" in r.reasons


def test_open_with_open_pr_pending():
    r = classify_github_issue(_issue(linked_pr_open=True))
    assert r.action == ActionState.PENDING
    assert "github_issue_pr_open" in r.reasons


def test_open_with_merged_pr_actionable():
    r = classify_github_issue(_issue(linked_pr_merged=True, linked_pr_open=False))
    assert r.action == ActionState.ACTIONABLE
    assert "github_issue_pr_merged" in r.reasons


def test_blocked_label():
    r = classify_github_issue(_issue(labels=("blocked",)))
    assert r.action == ActionState.BLOCKED
    assert r.blocked
    assert "github_issue_blocked" in r.reasons


def test_jira_blocked():
    r = classify_github_issue(_issue(linked_jira_blocked=True))
    assert r.action == ActionState.BLOCKED
    assert "github_issue_jira_blocked" in r.reasons


def test_not_assignee_ignore():
    r = classify_github_issue(_issue(assignee_is_user=False))
    assert r.action == ActionState.IGNORE
    assert r.lifecycle == Lifecycle.UNTRACKED
    assert "github_issue_not_assignee" in r.reasons


def test_blocked_label_case_insensitive():
    cfg = ClassifyConfig(blocked_labels=("Blocked",))
    r = classify_github_issue(_issue(labels=("BLOCKED",)), cfg)
    assert r.action == ActionState.BLOCKED
