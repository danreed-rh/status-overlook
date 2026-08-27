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
    assert "jira:OLD-1" in stats.finished


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
