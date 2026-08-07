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
        has_unresolved_reviews=False,
        ci_failed=False,
    )
    base.update(kwargs)
    return GitHubPrSnapshot(**base)


def test_merged_done():
    r = classify_github(_pr(merged=True, state="closed", author_is_user=True))
    assert r.lifecycle == Lifecycle.DONE
    assert r.action == ActionState.DONE


def test_author_open_clean_pending():
    r = classify_github(_pr(author_is_user=True))
    assert r.action == ActionState.PENDING


def test_ci_failed_actionable():
    r = classify_github(_pr(author_is_user=True, ci_failed=True))
    assert r.action == ActionState.ACTIONABLE
    assert "github_ci_failed" in r.reasons


def test_unresolved_reviews_actionable():
    r = classify_github(_pr(author_is_user=True, has_unresolved_reviews=True))
    assert r.action == ActionState.ACTIONABLE
    assert "github_unresolved_reviews" in r.reasons


def test_author_draft_actionable():
    r = classify_github(_pr(author_is_user=True, draft=True))
    assert r.action == ActionState.ACTIONABLE


def test_lgtm_label_actionable_for_author():
    r = classify_github(_pr(author_is_user=True, labels=("lgtm",)))
    assert r.action == ActionState.ACTIONABLE
    assert "github_actionable_label" in r.reasons


def test_assignee_lgtm_pending():
    r = classify_github(
        _pr(assignee_is_user=True, labels=("lgtm",), user_gave_lgtm=True)
    )
    assert r.action == ActionState.PENDING
    assert "github_assignee_lgtm" in r.reasons


def test_assignee_lgtm_overrides_ci_fail():
    r = classify_github(
        _pr(
            assignee_is_user=True,
            user_gave_lgtm=True,
            ci_failed=True,
            labels=("lgtm",),
        )
    )
    assert r.action == ActionState.PENDING


def test_author_still_actionable_with_lgtm_even_if_also_assignee():
    r = classify_github(
        _pr(
            author_is_user=True,
            assignee_is_user=True,
            user_gave_lgtm=True,
            labels=("lgtm",),
        )
    )
    assert r.action == ActionState.ACTIONABLE


def test_slash_lgtm_not_default():
    r = classify_github(_pr(author_is_user=True, labels=("/lgtm",)))
    assert r.action == ActionState.PENDING


def test_blocked_jira_overrides_lgtm():
    r = classify_github(
        _pr(author_is_user=True, labels=("lgtm",), linked_jira_blocked=True)
    )
    assert r.action == ActionState.BLOCKED
    assert r.blocked


def test_uninvolved_ignored():
    r = classify_github(_pr(ci_failed=True))
    assert r.action == ActionState.IGNORE
    assert not r.should_track


def test_custom_actionable_label():
    r = classify_github(
        _pr(author_is_user=True, labels=("/lgtm",)),
        ClassifyConfig(actionable_labels=("/lgtm",)),
    )
    assert r.action == ActionState.ACTIONABLE
