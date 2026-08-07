from status_overlook.digest import build_digest_markdown, is_unread, mark_read
from status_overlook.enrich import state_fingerprint
from status_overlook.store import TrackStore, TrackedItem


def test_fingerprint_stable():
    a = state_fingerprint(
        action="pending",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_waiting",),
    )
    b = state_fingerprint(
        action="pending",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_waiting",),
    )
    assert a == b


def test_fingerprint_changes_on_action():
    a = state_fingerprint(
        action="pending", lifecycle="active", remote_status="open", blocked=False, reasons=()
    )
    b = state_fingerprint(
        action="actionable", lifecycle="active", remote_status="open", blocked=False, reasons=()
    )
    assert a != b


def test_unread_and_mark_read():
    store = TrackStore(
        items={
            "jira:X-1": TrackedItem(
                id="jira:X-1",
                source="jira",
                key="X-1",
                lifecycle="active",
                action="pending",
                state_changed_at="2026-08-07T12:00:00Z",
            )
        }
    )
    item = store.items["jira:X-1"]
    assert is_unread(item)
    mark_read(store, all_items=True)
    assert item.last_read_at
    assert not is_unread(item)


def test_digest_sections():
    store = TrackStore(
        items={
            "jira:A-1": TrackedItem(
                id="jira:A-1",
                source="jira",
                key="A-1",
                lifecycle="active",
                action="actionable",
                summary="do it",
                remote_status="In Progress",
            ),
            "jira:B-1": TrackedItem(
                id="jira:B-1",
                source="jira",
                key="B-1",
                lifecycle="active",
                action="blocked",
                blocked=True,
                summary="stuck",
                remote_status="In Progress",
            ),
        }
    )
    md = build_digest_markdown(store)
    assert "## Actionable" in md
    assert "A-1" in md
    assert "## Blocked" in md
    assert "B-1" in md
