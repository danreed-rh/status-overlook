from status_overlook.classify_jira import classify_jira
from status_overlook.models import ActionState, JiraIssueSnapshot, Lifecycle


def test_done_status():
    r = classify_jira(JiraIssueSnapshot(key="X-1", status="Closed", assignee_is_user=True))
    assert r.lifecycle == Lifecycle.DONE
    assert r.action == ActionState.DONE


def test_active_assignee_actionable():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="In Progress", assignee_is_user=True)
    )
    assert r.should_track
    assert r.action == ActionState.ACTIONABLE


def test_blocked_any_status_is_blocked_not_pending():
    for status in ("In Progress", "Review", "Testing", "New"):
        r = classify_jira(
            JiraIssueSnapshot(
                key="X-1",
                status=status,
                assignee_is_user=True,
                blocked=True,
            )
        )
        assert r.action == ActionState.BLOCKED, status
        assert r.blocked
        assert r.should_track


def test_review_assignee_pending():
    r = classify_jira(JiraIssueSnapshot(key="X-1", status="Review", assignee_is_user=True))
    assert r.action == ActionState.PENDING


def test_testing_qa_contact_actionable():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Testing",
            assignee_is_user=True,
            qa_contact_is_user=True,
        )
    )
    assert r.action == ActionState.ACTIONABLE
    assert "jira_testing_qa_contact" in r.reasons


def test_testing_assignee_only_not_actionable_or_pending():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Testing", assignee_is_user=True)
    )
    assert r.action == ActionState.IGNORE
    assert not r.should_track
    assert "jira_testing_assignee_only" in r.reasons


def test_testing_qa_only_actionable():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Testing",
            assignee_is_user=False,
            qa_contact_is_user=True,
        )
    )
    assert r.should_track
    assert r.action == ActionState.ACTIONABLE


def test_not_assignee_ignored():
    r = classify_jira(JiraIssueSnapshot(key="X-1", status="In Progress", assignee_is_user=False))
    assert r.action == ActionState.IGNORE
