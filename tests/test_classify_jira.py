from status_overlook.classify_jira import classify_jira, is_jira_blocked
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


def test_blocked_via_flagged():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1", status="In Progress", assignee_is_user=True, flagged=True
        )
    )
    assert r.action == ActionState.BLOCKED
    assert "jira_flagged" in r.reasons


def test_blocked_via_status_name():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Blocked", assignee_is_user=True)
    )
    assert r.action == ActionState.BLOCKED
    assert "jira_status_blocked" in r.reasons


def test_blocked_via_label():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Review",
            assignee_is_user=True,
            labels=("blocked", "other"),
        )
    )
    assert r.action == ActionState.BLOCKED
    assert "jira_label_blocked" in r.reasons


def test_blocked_any_workflow_status_when_flagged():
    for status in ("In Progress", "Review", "Testing", "New"):
        r = classify_jira(
            JiraIssueSnapshot(
                key="X-1", status=status, assignee_is_user=True, flagged=True
            )
        )
        assert r.action == ActionState.BLOCKED, status


def test_is_jira_blocked_helpers():
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="New", flagged=True))
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="Blocked"))
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="New", labels=("Blocked",)))
    assert not is_jira_blocked(JiraIssueSnapshot(key="X", status="In Progress"))


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


def test_testing_assignee_only_not_actionable_or_pending():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Testing", assignee_is_user=True)
    )
    assert r.action == ActionState.IGNORE
    assert not r.should_track


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
