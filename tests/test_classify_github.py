from status_overlook.classify_github import classify_github
from status_overlook.models import ActionState, ClassifyConfig, GitHubPrSnapshot, Lifecycle


def _pr(**kwargs) -> GitHubPrSnapshot:
    base = dict(
        repo="org/repo",
        number=1,
        state="open",
        merged=False,
        draft=False,
        author_is_user=False,
        assignee_is_user=False,
        labels=(),
        linked_jira_blocked=False,
    )
    base.update(kwargs)
    return GitHubPrSnapshot(**base)


def test_merged_done():
    r = classify_github(_pr(merged=True, state="closed", author_is_user=True))
    assert r.lifecycle == Lifecycle.DONE
    assert r.action == ActionState.DONE


def test_author_open_pending():
    r = classify_github(_pr(author_is_user=True, draft=False))
    assert r.action == ActionState.PENDING


def test_author_draft_actionable():
    r = classify_github(_pr(author_is_user=True, draft=True))
    assert r.action == ActionState.ACTIONABLE
    assert "github_author_draft" in r.reasons


def test_assignee_not_draft_actionable():
    r = classify_github(_pr(assignee_is_user=True, draft=False))
    assert r.action == ActionState.ACTIONABLE


def test_lgtm_label_actionable():
    r = classify_github(_pr(author_is_user=True, labels=("/lgtm",)))
    assert r.action == ActionState.ACTIONABLE
    assert "github_actionable_label" in r.reasons


def test_lgtm_case_insensitive():
    r = classify_github(
        _pr(author_is_user=True, labels=("LGTM",)),
        ClassifyConfig(actionable_labels=("lgtm",)),
    )
    assert r.action == ActionState.ACTIONABLE


def test_blocked_jira_overrides_lgtm():
    r = classify_github(
        _pr(author_is_user=True, labels=("/lgtm",), linked_jira_blocked=True)
    )
    assert r.action == ActionState.PENDING
    assert r.blocked
    assert "github_linked_jira_blocked" in r.reasons


def test_uninvolved_ignored():
    r = classify_github(_pr())
    assert r.action == ActionState.IGNORE
    assert not r.should_track
