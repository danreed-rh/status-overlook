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
    assert "jira_active_assignee" in r.reasons


def test_active_blocked_pending():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1", status="In Progress", assignee_is_user=True, blocked=True
        )
    )
    assert r.action == ActionState.PENDING
    assert r.blocked


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


def test_testing_assignee_only_actionable():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Testing", assignee_is_user=True)
    )
    assert r.action == ActionState.ACTIONABLE
    assert "jira_testing_assignee" in r.reasons


def test_testing_qa_only_not_assignee_actionable():
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


def test_testing_uninvolved_ignored():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Testing", assignee_is_user=False)
    )
    assert r.action == ActionState.IGNORE
    assert not r.should_track


def test_not_assignee_ignored():
    r = classify_jira(JiraIssueSnapshot(key="X-1", status="In Progress", assignee_is_user=False))
    assert r.action == ActionState.IGNORE
