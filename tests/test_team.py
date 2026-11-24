"""Team queue behavior, persistence and provider selection (no network)."""

import json
import os

import pytest

from status_overlook import team
from status_overlook.providers import team_github


def _search_pr(number, *, author="gage", repo="org/repo", labels=(), assignees=(), draft=False):
    return {
        "number": number,
        "author": {"login": author},
        "repository": {"nameWithOwner": repo},
        "title": f"Work on #{number}",
        "url": f"https://github.com/{repo}/pull/{number}",
        "updatedAt": "2026-11-23T10:00:00Z",
        "labels": [{"name": name} for name in labels],
        "assignees": [{"login": name} for name in assignees],
        "isDraft": draft,
    }


def _details(row, *, decision="REVIEW_REQUIRED", state="OPEN"):
    return {**row, "state": state, "reviewDecision": decision}


def test_provider_only_includes_verified_review_required_prs_and_prioritizes_lgtm(monkeypatch):
    rows = [
        _search_pr(1),
        _search_pr(2, labels=("LGTM",), assignees=("reviewer",)),
        _search_pr(3, labels=("lgtm",)),
        _search_pr(4, draft=True),
        _search_pr(5, assignees=("reviewer",)),
        _search_pr(6),
    ]
    calls = []

    def gh_json(args):
        calls.append(args)
        if args[:2] == ["search", "prs"]:
            return rows
        if args[:2] == ["pr", "view"]:
            row = next(row for row in rows if str(row["number"]) == args[2])
            return _details(row, decision=None if row["number"] == 6 else "REVIEW_REQUIRED")
        if args[:2] == ["api", "repos/org/repo"]:
            return {"admin": False, "maintain": True, "push": True}
        raise AssertionError(args)

    monkeypatch.setattr(team_github, "_gh_json", gh_json)
    items = team_github.fetch_team_prs(["gage"], limit=50, self_login="myself")

    assert {item.number: item.queue for item in items} == {1: "unassigned", 2: "lgtm", 3: "lgtm"}
    assert next(item for item in items if item.number == 3).unassigned
    assert len([call for call in calls if call[:2] == ["api", "repos/org/repo"]]) == 1
    assert "--review=required" in calls[0]


def test_provider_requires_maintain_or_admin_for_lgtm_but_keeps_unassigned(monkeypatch):
    rows = [
        _search_pr(1, labels=("lgtm",), assignees=("reviewer",)),
        _search_pr(2, labels=("lgtm",)),
    ]

    def gh_json(args):
        if args[:2] == ["search", "prs"]:
            return rows
        if args[:2] == ["pr", "view"]:
            return _details(next(row for row in rows if str(row["number"]) == args[2]))
        if args[:2] == ["api", "repos/org/repo"]:
            return {"admin": False, "maintain": False, "push": True}
        raise AssertionError(args)

    monkeypatch.setattr(team_github, "_gh_json", gh_json)
    items = team_github.fetch_team_prs(["gage"], limit=50)
    assert [(item.number, item.queue) for item in items] == [(2, "unassigned")]


def test_provider_refuses_truncated_search(monkeypatch):
    monkeypatch.setattr(team_github, "_gh_json", lambda args: [_search_pr(1)])
    with pytest.raises(team_github.TeamProviderError, match="reached limit"):
        team_github.fetch_team_prs(["gage"], limit=1)


def test_provider_does_not_treat_missing_assignees_as_unassigned(monkeypatch):
    row = _search_pr(1)

    def gh_json(args):
        if args[:2] == ["search", "prs"]:
            return [row]
        if args[:2] == ["pr", "view"]:
            details = _details(row)
            details.pop("assignees")
            return details
        raise AssertionError(args)

    monkeypatch.setattr(team_github, "_gh_json", gh_json)
    with pytest.raises(team_github.TeamProviderError, match="Unexpected PR details"):
        team_github.fetch_team_prs(["gage"], limit=50)


def test_roster_validation_and_private_storage(tmp_path):
    path = tmp_path / "team_members.json"
    assert team.update_member("Gkrumbach07", "add", self_login="danreed-rh", path=path) == ["Gkrumbach07"]
    assert team.update_member("gkrumbach07", "add", path=path) == ["Gkrumbach07"]
    assert team.update_member("GKRUMBACH07", "remove", path=path) == []
    assert os.stat(path).st_mode & 0o777 == 0o600
    for invalid in ("-bad", "foo--bar", "bad name", "--limit=1000"):
        with pytest.raises(ValueError):
            team.update_member(invalid, "add", path=path)
    with pytest.raises(ValueError, match="My Work"):
        team.update_member("danreed-rh", "add", self_login="danreed-rh", path=path)


def test_invalid_local_json_shapes_report_errors(tmp_path):
    roster_path = tmp_path / "team_members.json"
    queue_path = tmp_path / "team_queue.json"
    roster_path.write_text("[]")
    queue_path.write_text("[]")
    with pytest.raises(ValueError, match="Invalid team roster"):
        team.load_members(roster_path)
    with pytest.raises(ValueError, match="Invalid team queue"):
        team.load_team_queue(queue_path)
    queue_path.write_text('{"items": "not-a-list"}')
    with pytest.raises(ValueError, match="Invalid team queue items"):
        team.load_team_queue(queue_path)


def test_refresh_preserves_queue_age_and_old_results_on_failure(tmp_path, monkeypatch):
    roster = tmp_path / "team_members.json"
    cache = tmp_path / "team_queue.json"
    monkeypatch.setattr(team, "team_members_path", lambda: roster)
    monkeypatch.setattr(team, "team_queue_path", lambda: cache)
    team.save_members(["gage"])
    seen = [
        team.TeamPr(
            repo="org/repo", number=1, title="PR", author="gage",
            url="https://github.com/org/repo/pull/1", queue="unassigned",
            unassigned=True,
        )
    ]
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-20T10:00:00Z")
    monkeypatch.setattr(team_github, "fetch_team_prs", lambda *a, **k: seen)
    first = team.refresh_team_queue()
    assert first.items[0].entered_at == "2026-11-20T10:00:00Z"

    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-23T10:00:00Z")
    second = team.refresh_team_queue()
    assert second.items[0].entered_at == first.items[0].entered_at

    def fail(*_args, **_kwargs):
        raise team_github.TeamProviderError("GitHub unavailable")

    monkeypatch.setattr(team_github, "fetch_team_prs", fail)
    stale = team.refresh_team_queue()
    assert stale.last_error == "GitHub unavailable"
    assert stale.updated_at == second.updated_at
    assert stale.items[0].entered_at == first.items[0].entered_at

    team.save_members([])
    assert team.team_payload()["items"] == []
    assert json.loads(cache.read_text())["items"][0]["author"] == "gage"


def test_switching_queue_resets_observed_age(tmp_path, monkeypatch):
    monkeypatch.setattr(team, "team_members_path", lambda: tmp_path / "team_members.json")
    monkeypatch.setattr(team, "team_queue_path", lambda: tmp_path / "team_queue.json")
    team.save_members(["gage"])
    queue = [team.TeamPr(repo="org/repo", number=1, title="PR", author="gage", url="", queue="unassigned", unassigned=True)]
    monkeypatch.setattr(team_github, "fetch_team_prs", lambda *a, **k: queue)
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-20T10:00:00Z")
    team.refresh_team_queue()
    queue[0].queue = "lgtm"
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-23T10:00:00Z")
    assert team.refresh_team_queue().items[0].entered_at == "2026-11-23T10:00:00Z"


def test_leaving_and_reentering_queue_starts_a_new_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(team, "team_members_path", lambda: tmp_path / "team_members.json")
    monkeypatch.setattr(team, "team_queue_path", lambda: tmp_path / "team_queue.json")
    team.save_members(["gage"])
    current = [team.TeamPr(repo="org/repo", number=1, title="PR", author="gage", url="", queue="unassigned", unassigned=True)]
    monkeypatch.setattr(team_github, "fetch_team_prs", lambda *a, **k: current)
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-20T10:00:00Z")
    assert team.refresh_team_queue().items[0].entered_at == "2026-11-20T10:00:00Z"
    current.clear()
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-21T10:00:00Z")
    assert team.refresh_team_queue().items == []
    current.append(team.TeamPr(repo="org/repo", number=1, title="PR", author="gage", url="", queue="unassigned", unassigned=True))
    monkeypatch.setattr(team, "utc_now", lambda: "2026-11-23T10:00:00Z")
    assert team.refresh_team_queue().items[0].entered_at == "2026-11-23T10:00:00Z"
