from status_overlook.cues import cue_dict, cue_for


def test_unknown_reason_no_cue():
    assert cue_for("actionable", ["not_a_real_reason"]) is None
    assert cue_for("actionable", []) is None
    assert cue_for("done", ["jira_status_done"]) is None
    assert cue_for("ignore", ["jira_not_assignee"]) is None


def test_each_reason_maps():
    cases = [
        ("actionable", "github_ci_failed", "fix_ci", "Fix CI"),
        ("actionable", "github_unresolved_reviews", "address_review", "Address review"),
        ("actionable", "github_actionable_label", "merge", "Ready to merge"),
        ("actionable", "github_assignee_to_review", "review", "Review"),
        ("actionable", "jira_testing_qa_contact", "test", "Test"),
        ("actionable", "jira_review_pr_merged", "follow_up", "Follow up"),
        ("actionable", "github_issue_pr_merged", "follow_up", "Follow up"),
        ("actionable", "jira_epic_children_done", "follow_up", "Follow up"),
        ("actionable", "jira_active_assignee", "develop", "Develop"),
        ("actionable", "github_issue_open", "develop", "Develop"),
        ("actionable", "github_author_draft", "develop", "Develop"),
        ("pending", "github_assignee_waiting_on_author", "wait_author", "Waiting on author"),
        ("pending", "github_assignee_threads_unknown", "wait_author", "Waiting on author"),
        ("pending", "github_assignee_lgtm", "signed_off", "Signed off"),
        ("pending", "github_issue_pr_open", "wait_pr", "Waiting on PR"),
        ("pending", "jira_epic_children_open", "wait_children", "Waiting on children"),
        ("pending", "jira_epic_children_unknown", "wait_children", "Waiting on children"),
        ("pending", "jira_in_review", "wait_review", "Waiting for review"),
        ("pending", "jira_testing_assignee_only", "wait_test", "Testing"),
        ("pending", "github_waiting", "wait_review", "Waiting for review"),
        ("pending", "jira_unknown_status_assignee", "waiting", "Waiting"),
        ("blocked", "jira_blocked_by_unresolved", "blocked_by", "Blocked by issue"),
        ("blocked", "jira_flagged", "flagged", "Flagged"),
        ("blocked", "github_linked_jira_blocked", "jira_blocked", "Linked Jira blocked"),
        ("blocked", "github_issue_jira_blocked", "jira_blocked", "Linked Jira blocked"),
        ("blocked", "jira_status_blocked", "blocked_status", "Status blocked"),
        ("blocked", "jira_label_blocked", "blocked_label", "Blocked label"),
        ("blocked", "github_issue_blocked", "blocked_label", "Blocked label"),
    ]
    for action, reason, cue_id, label in cases:
        cue = cue_for(action, [reason])
        assert cue is not None, reason
        assert cue.id == cue_id
        assert cue.label == label
        assert cue.kind == action


def test_priority_ci_beats_threads_and_lgtm():
    cue = cue_for(
        "actionable",
        ["github_actionable_label", "github_unresolved_reviews", "github_ci_failed"],
    )
    assert cue is not None
    assert cue.id == "fix_ci"


def test_priority_threads_beat_lgtm():
    cue = cue_for(
        "actionable",
        ["github_actionable_label", "github_unresolved_reviews"],
    )
    assert cue is not None
    assert cue.id == "address_review"


def test_cue_dict_shape():
    d = cue_dict("pending", ["jira_in_review"])
    assert d == {
        "id": "wait_review",
        "label": "Waiting for review",
        "kind": "pending",
    }
    assert cue_dict("done", ["jira_status_done"]) is None
