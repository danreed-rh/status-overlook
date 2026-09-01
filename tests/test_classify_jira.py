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


def test_blocked_via_unresolved_blocked_by_link():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="New",
            assignee_is_user=True,
            blocked_by_unresolved=True,
        )
    )
    assert r.action == ActionState.BLOCKED
    assert "jira_blocked_by_unresolved" in r.reasons


def test_resolved_blocked_by_does_not_block():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="In Progress",
            assignee_is_user=True,
            blocked_by_unresolved=False,
        )
    )
    assert r.action == ActionState.ACTIONABLE


def test_is_jira_blocked_helpers():
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="New", flagged=True))
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="Blocked"))
    assert is_jira_blocked(JiraIssueSnapshot(key="X", status="New", labels=("Blocked",)))
    assert is_jira_blocked(
        JiraIssueSnapshot(key="X", status="New", blocked_by_unresolved=True)
    )
    assert not is_jira_blocked(JiraIssueSnapshot(key="X", status="In Progress"))


def test_review_assignee_pending():
    r = classify_jira(JiraIssueSnapshot(key="X-1", status="Review", assignee_is_user=True))
    assert r.action == ActionState.PENDING
    assert "jira_in_review" in r.reasons


def test_review_assignee_merged_pr_actionable():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Review",
            assignee_is_user=True,
            linked_pr_merged=True,
            pr_link="https://github.com/org/repo/pull/1",
        )
    )
    assert r.action == ActionState.ACTIONABLE
    assert "jira_review_pr_merged" in r.reasons


def test_review_assignee_unmerged_pr_still_pending():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Review",
            assignee_is_user=True,
            linked_pr_merged=False,
            pr_link="https://github.com/org/repo/pull/1",
        )
    )
    assert r.action == ActionState.PENDING
    assert "jira_in_review" in r.reasons


def test_review_assignee_unknown_pr_merge_pending():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Review",
            assignee_is_user=True,
            linked_pr_merged=None,
        )
    )
    assert r.action == ActionState.PENDING
    assert "jira_in_review" in r.reasons


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


def test_testing_assignee_only_pending():
    r = classify_jira(
        JiraIssueSnapshot(key="X-1", status="Testing", assignee_is_user=True)
    )
    assert r.action == ActionState.PENDING
    assert r.should_track
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


def test_epic_pending_while_children_open():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="In Progress",
            assignee_is_user=True,
            issue_type="Epic",
            epic_children_all_done=False,
        )
    )
    assert r.action == ActionState.PENDING
    assert "jira_epic_children_open" in r.reasons


def test_epic_actionable_when_children_done():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="In Progress",
            assignee_is_user=True,
            issue_type="Epic",
            epic_children_all_done=True,
        )
    )
    assert r.action == ActionState.ACTIONABLE
    assert "jira_epic_children_done" in r.reasons


def test_epic_unknown_children_pending():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="In Progress",
            assignee_is_user=True,
            issue_type="Epic",
            epic_children_all_done=None,
        )
    )
    assert r.action == ActionState.PENDING
    assert "jira_epic_children_unknown" in r.reasons


def test_epic_done_status_still_done():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="Closed",
            assignee_is_user=True,
            issue_type="Epic",
            epic_children_all_done=True,
        )
    )
    assert r.action == ActionState.DONE


def test_story_not_affected_by_epic_fields():
    r = classify_jira(
        JiraIssueSnapshot(
            key="X-1",
            status="In Progress",
            assignee_is_user=True,
            issue_type="Story",
            epic_children_all_done=False,
        )
    )
    assert r.action == ActionState.ACTIONABLE
    assert "jira_active_assignee" in r.reasons

