from status_overlook.enrich import apply_classification_to_item
from status_overlook.models import ActionState
from status_overlook.state import state_fingerprint
from status_overlook.store import TrackStore, TrackedItem, normalize_item_id, normalize_source_name


def test_normalize_legacy_github_source():
    assert normalize_source_name("github") == "github_pr"
    assert normalize_source_name("github_pr") == "github_pr"
    assert normalize_source_name("github_issue") == "github_issue"


def test_normalize_legacy_github_id():
    assert normalize_item_id("github:org/repo#1") == "github-pr:org/repo#1"
    assert normalize_item_id("github-pr:org/repo#1") == "github-pr:org/repo#1"
    assert normalize_item_id("github-issue:org/repo#1") == "github-issue:org/repo#1"


def test_store_load_migrates_legacy_github_pr():
    store = TrackStore.from_dict(
        {
            "schema_version": 1,
            "updated_at": "",
            "items": {
                "github:org/repo#9": {
                    "id": "github:org/repo#9",
                    "source": "github",
                    "key": "org/repo#9",
                    "lifecycle": "active",
                    "action": "pending",
                }
            },
        }
    )
    assert "github-pr:org/repo#9" in store.items
    assert "github:org/repo#9" not in store.items
    item = store.items["github-pr:org/repo#9"]
    assert item.source == "github_pr"
    assert item.id == "github-pr:org/repo#9"


def test_store_load_migrates_legacy_fingerprint_without_resetting_timestamp():
    timestamp = "2026-08-10T12:00:00Z"
    store = TrackStore.from_dict(
        {
            "schema_version": 1,
            "items": {
                "jira:X-1": {
                    "id": "jira:X-1",
                    "source": "jira",
                    "key": "X-1",
                    "lifecycle": "active",
                    "action": "actionable",
                    "remote_status": "In Progress",
                    "reasons": ["jira_active_assignee"],
                    "state_changed_at": timestamp,
                    "state_fingerprint": "0123456789abcdef",
                }
            },
        }
    )
    item = store.items["jira:X-1"]
    assert item.state_changed_at == timestamp
    assert item.state_fingerprint == state_fingerprint(
        action="actionable",
        lifecycle="active",
        remote_status="In Progress",
        blocked=False,
        reasons=("jira_active_assignee",),
    )
    changed = apply_classification_to_item(
        item,
        action=ActionState.ACTIONABLE,
        lifecycle="active",
        remote_status="In Progress",
        blocked=False,
        reasons=("github_issue_open",),
        now_s="2026-08-11T12:00:00Z",
    )
    assert not changed
    assert item.state_changed_at == timestamp


def test_store_load_leaves_unobserved_item_uninitialized():
    store = TrackStore.from_dict(
        {
            "items": {
                "jira:X-2": {
                    "id": "jira:X-2",
                    "source": "jira",
                    "key": "X-2",
                    "lifecycle": "active",
                    "action": "",
                }
            }
        }
    )
    item = store.items["jira:X-2"]
    assert item.state_changed_at == ""
    assert item.state_fingerprint == ""
