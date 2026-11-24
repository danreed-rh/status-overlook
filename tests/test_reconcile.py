from datetime import datetime, timezone

from status_overlook.store import Candidate, TrackStore, TrackedItem, reconcile


def test_reconcile_adds_and_finishes():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    store = TrackStore(
        items={
            "jira:OLD-1": TrackedItem(
                id="jira:OLD-1",
                source="jira",
                key="OLD-1",
                lifecycle="active",
                first_seen_at="2026-08-01T00:00:00Z",
                last_seen_at="2026-08-01T00:00:00Z",
            )
        }
    )
    candidates = [
        Candidate(source="jira", key="NEW-2", summary="hello", remote_status="In Progress"),
        Candidate(source="github_pr", key="org/repo#3", summary="pr", remote_status="open"),
    ]
    store, stats = reconcile(store, candidates, now=now, retention_days=7)
    assert "jira:NEW-2" in store.items
    assert "github-pr:org/repo#3" in store.items
    assert "jira:NEW-2" in stats.added
    assert store.items["jira:OLD-1"].lifecycle == "done"
    assert store.items["jira:OLD-1"].state_changed_at == "2026-08-07T12:00:00Z"
    assert "jira:OLD-1" in stats.finished


def test_reconcile_preserves_last_enriched_state_until_enrichment():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    item = TrackedItem(
        id="github-pr:org/repo#3",
        source="github_pr",
        key="org/repo#3",
        lifecycle="done",
        action="done",
        remote_status="merged",
        state_changed_at="2026-08-01T12:00:00Z",
        state_fingerprint="visible-v2:0123456789abcdef",
        finished_at="2026-08-01T12:00:00Z",
    )
    store = TrackStore(items={item.id: item})
    candidates = [
        Candidate(
            source="github_pr",
            key="org/repo#3",
            summary="pr",
            remote_status="open",
        )
    ]

    store, stats = reconcile(store, candidates, now=now, defer_lifecycle=True)

    refreshed = store.items[item.id]
    assert refreshed.lifecycle == "done"
    assert refreshed.action == "done"
    assert refreshed.remote_status == "merged"
    assert refreshed.state_changed_at == "2026-08-01T12:00:00Z"
    assert refreshed.finished_at == "2026-08-01T12:00:00Z"
    assert item.id in stats.refreshed


def test_reconcile_can_defer_finishing_missing_items_to_enrichment():
    item = TrackedItem(
        id="jira:KEEP-1",
        source="jira",
        key="KEEP-1",
        lifecycle="active",
        action="actionable",
        remote_status="In Progress",
        state_changed_at="2026-08-01T12:00:00Z",
    )
    store = TrackStore(items={item.id: item})

    store, stats = reconcile(store, [], defer_lifecycle=True)

    assert store.items[item.id].lifecycle == "active"
    assert store.items[item.id].state_changed_at == "2026-08-01T12:00:00Z"
    assert stats.finished == []


def test_reconcile_reactivates_done_item_when_lifecycle_is_not_deferred():
    item = TrackedItem(
        id="jira:RETURN-1",
        source="jira",
        key="RETURN-1",
        lifecycle="done",
        action="actionable",
        remote_status="In Progress",
        state_changed_at="2026-08-01T12:00:00Z",
    )
    store = TrackStore(items={item.id: item})

    store, _ = reconcile(
        store,
        [Candidate(source="jira", key="RETURN-1", remote_status="In Progress")],
        now=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )

    assert store.items[item.id].lifecycle == "active"
    assert store.items[item.id].finished_at is None
    assert store.items[item.id].state_changed_at == "2026-08-10T12:00:00Z"


def test_deferred_reconcile_does_not_prune_rediscovered_done_item():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    item = TrackedItem(
        id="jira:REOPEN-1",
        source="jira",
        key="REOPEN-1",
        lifecycle="done",
        action="done",
        finished_at="2026-08-01T00:00:00Z",
    )
    store = TrackStore(items={item.id: item})

    store, stats = reconcile(
        store,
        [Candidate(source="jira", key="REOPEN-1", remote_status="In Progress")],
        now=now,
        defer_lifecycle=True,
        retention_days=7,
    )

    assert item.id in store.items
    assert stats.pruned == []


def test_deferred_reconcile_still_prunes_old_ignored_items():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    item = TrackedItem(
        id="jira:IGNORE-1",
        source="jira",
        key="IGNORE-1",
        lifecycle="done",
        action="ignore",
        finished_at="2026-08-01T00:00:00Z",
    )
    store = TrackStore(items={item.id: item})

    store, stats = reconcile(
        store,
        [Candidate(source="jira", key="IGNORE-1")],
        now=now,
        defer_lifecycle=True,
        retention_days=7,
    )

    assert item.id not in store.items
    assert stats.pruned == [item.id]


def test_reconcile_keeps_pins():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    store = TrackStore(
        items={
            "jira:PIN-1": TrackedItem(
                id="jira:PIN-1",
                source="jira",
                key="PIN-1",
                lifecycle="active",
                pinned=True,
                first_seen_at="2026-08-01T00:00:00Z",
                last_seen_at="2026-08-01T00:00:00Z",
            )
        }
    )
    store, stats = reconcile(store, [], pin_ids={"jira:PIN-1"}, now=now)
    assert store.items["jira:PIN-1"].lifecycle == "active"
    assert "jira:PIN-1" in stats.pinned_kept


def test_reconcile_prunes_old_done():
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    store = TrackStore(
        items={
            "jira:OLD-DONE": TrackedItem(
                id="jira:OLD-DONE",
                source="jira",
                key="OLD-DONE",
                lifecycle="done",
                finished_at="2026-08-01T00:00:00Z",
                first_seen_at="2026-07-01T00:00:00Z",
                last_seen_at="2026-08-01T00:00:00Z",
            )
        }
    )
    store, stats = reconcile(store, [], now=now, retention_days=7)
    assert "jira:OLD-DONE" not in store.items
    assert "jira:OLD-DONE" in stats.pruned


def test_reconcile_does_not_reactivate_ignore():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    store = TrackStore(
        items={
            "jira:T-1": TrackedItem(
                id="jira:T-1",
                source="jira",
                key="T-1",
                lifecycle="done",
                action="ignore",
                finished_at="2026-08-07T10:00:00Z",
                first_seen_at="2026-08-01T00:00:00Z",
                last_seen_at="2026-08-07T10:00:00Z",
            )
        }
    )
    candidates = [
        Candidate(source="jira", key="T-1", summary="testing only", remote_status="Testing"),
    ]
    store, stats = reconcile(store, candidates, now=now)
    assert store.items["jira:T-1"].lifecycle == "done"
    assert store.items["jira:T-1"].action == "ignore"
    assert store.items["jira:T-1"].finished_at is not None
    assert "jira:T-1" in stats.refreshed
