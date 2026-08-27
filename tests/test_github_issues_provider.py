"""Unit tests for GitHub issue discovery helpers."""

from status_overlook.providers import github as github_provider
from status_overlook.store import Candidate


def test_issue_candidate_id_and_url():
    row = {
        "number": 27,
        "url": "https://github.com/org/repo/issues/27",
        "title": "Add i18n stub",
        "repository": {"nameWithOwner": "org/repo"},
    }
    cand = github_provider._issue_candidate(row)
    assert isinstance(cand, Candidate)
    assert cand.source == "github_issue"
    assert cand.key == "org/repo#27"
    assert cand.id == "github-issue:org/repo#27"
    assert cand.url.endswith("/issues/27")


def test_fetch_assigned_issues_uses_assignee_and_is_issue(monkeypatch):
    calls: list[list[str]] = []

    def fake_gh_json(args: list[str]):
        calls.append(args)
        return [
            {
                "number": 1,
                "url": "https://github.com/o/r/issues/1",
                "title": "One",
                "repository": {"nameWithOwner": "o/r"},
            }
        ]

    monkeypatch.setattr(github_provider, "_gh_json", fake_gh_json)
    out = github_provider.fetch_assigned_issues(limit=50)
    assert len(out) == 1
    assert out[0].id == "github-issue:o/r#1"
    assert len(calls) == 1
    assert calls[0][0:2] == ["search", "issues"]
    assert "--assignee=@me" in calls[0]
    assert "--author=@me" not in calls[0]
    assert "is:issue" in calls[0]
