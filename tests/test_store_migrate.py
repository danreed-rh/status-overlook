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
