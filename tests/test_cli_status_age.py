from status_overlook import cli
from status_overlook.store import TrackStore, TrackedItem


def _store() -> TrackStore:
    return TrackStore(
        items={
            "jira:AGE-1": TrackedItem(
                id="jira:AGE-1",
                source="jira",
                key="AGE-1",
                lifecycle="active",
                action="actionable",
                summary="Aged ticket",
                remote_status="In Progress",
                state_changed_at="2020-01-01T00:00:00Z",
                reasons=["jira_active_assignee"],
            )
        }
    )


def test_show_plain_renders_current_age_from_store(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_store", _store)
    assert cli.main(["show", "--plain"]) == 0
    output = capsys.readouterr().out
    assert "**AGE-1**" in output
    assert "[In Progress · " in output
    assert "state_changed: 2020-01-01T00:00:00Z" in output


def test_show_store_includes_status_age(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_store", _store)
    assert cli.main(["show", "--store"]) == 0
    output = capsys.readouterr().out
    assert "[In Progress · " in output
