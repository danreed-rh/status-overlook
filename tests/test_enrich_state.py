"""Unit tests for GitHub PR state normalization (no network)."""

from status_overlook.enrich import (
    _body_has_slash_lgtm,
    _status_is_terminal,
    _user_gave_lgtm,
    blocked_by_unresolved_from_fields,
    github_remote_status,
    normalize_github_pr_state,
    parse_github_pr_url,
)
from status_overlook.models import ClassifyConfig, GitHubPrSnapshot


def test_merged_state_is_closed_merged():
    state, merged = normalize_github_pr_state("MERGED", "2026-08-07T19:53:06Z")
    assert state == "closed"
    assert merged is True


def test_merged_at_without_merged_enum():
    state, merged = normalize_github_pr_state("OPEN", "2026-08-07T19:53:06Z")
    assert state == "closed"
    assert merged is True


def test_open_pr():
    state, merged = normalize_github_pr_state("OPEN", None)
    assert state == "open"
    assert merged is False


def test_closed_unmerged():
    state, merged = normalize_github_pr_state("CLOSED", None)
    assert state == "closed"
    assert merged is False


def test_remote_status_merged_not_open_ci_fail():
    snap = GitHubPrSnapshot(
        repo="opendatahub-io/odh-dashboard",
        number=8758,
        state="closed",
        merged=True,
        ci_failed=True,
    )
    assert github_remote_status(snap) == "merged"


def test_remote_status_unresolved_threads():
    snap = GitHubPrSnapshot(
        repo="opendatahub-io/odh-dashboard",
        number=8787,
        state="open",
        has_unresolved_reviews=True,
    )
    assert github_remote_status(snap) == "open+unresolved_threads"


def test_probe_pr_review_threads_any_and_mine(monkeypatch):
    from status_overlook import enrich as enrich_mod

    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": True,
                                "comments": {
                                    "nodes": [{"author": {"login": "other"}}]
                                },
                            },
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [{"author": {"login": "reviewer"}}]
                                },
                            },
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [{"author": {"login": "danreed-rh"}}]
                                },
                            },
                        ]
                    }
                }
            }
        }
    }

    class FakeProc:
        returncode = 0
        stdout = __import__("json").dumps(payload)

    monkeypatch.setattr(
        enrich_mod.subprocess,
        "run",
        lambda *a, **k: FakeProc(),
    )
    any_u, mine = enrich_mod.probe_pr_review_threads(
        "opendatahub-io/odh-dashboard", 8787, "danreed-rh"
    )
    assert any_u is True
    assert mine is True


def test_probe_pr_review_threads_all_resolved(monkeypatch):
    from status_overlook import enrich as enrich_mod

    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": True,
                                "comments": {
                                    "nodes": [{"author": {"login": "other"}}]
                                },
                            }
                        ]
                    }
                }
            }
        }
    }

    class FakeProc:
        returncode = 0
        stdout = __import__("json").dumps(payload)

    monkeypatch.setattr(enrich_mod.subprocess, "run", lambda *a, **k: FakeProc())
    any_u, mine = enrich_mod.probe_pr_review_threads("o/r", 1, "me")
    assert any_u is False
    assert mine is False


def test_status_is_terminal_category_and_name():
    cfg = ClassifyConfig()
    assert _status_is_terminal(
        {"name": "Whatever", "statusCategory": {"key": "done"}}, cfg
    )
    assert _status_is_terminal({"name": "Closed", "statusCategory": {"key": "new"}}, cfg)
    assert not _status_is_terminal(
        {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}, cfg
    )


def test_blocked_by_unresolved_open_blocker():
    cfg = ClassifyConfig()
    fields = {
        "issuelinks": [
            {
                "type": {
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "inwardIssue": {
                    "key": "Y-2",
                    "fields": {
                        "status": {
                            "name": "New",
                            "statusCategory": {"key": "new"},
                        }
                    },
                },
            }
        ]
    }
    assert blocked_by_unresolved_from_fields(fields, cfg)


def test_blocked_by_resolved_blocker_not_blocked():
    cfg = ClassifyConfig()
    fields = {
        "issuelinks": [
            {
                "type": {
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "inwardIssue": {
                    "key": "Y-2",
                    "fields": {
                        "status": {
                            "name": "Closed",
                            "statusCategory": {"key": "done"},
                        }
                    },
                },
            }
        ]
    }
    assert not blocked_by_unresolved_from_fields(fields, cfg)


def test_blocks_outward_only_does_not_block_self():
    """This issue blocks another — that does not make this issue blocked."""
    cfg = ClassifyConfig()
    fields = {
        "issuelinks": [
            {
                "type": {
                    "name": "Blocks",
                    "inward": "is blocked by",
                    "outward": "blocks",
                },
                "outwardIssue": {
                    "key": "Y-3",
                    "fields": {
                        "status": {
                            "name": "New",
                            "statusCategory": {"key": "new"},
                        }
                    },
                },
            }
        ]
    }
    assert not blocked_by_unresolved_from_fields(fields, cfg)


def test_informs_link_ignored():
    cfg = ClassifyConfig()
    fields = {
        "issuelinks": [
            {
                "type": {
                    "name": "Informs",
                    "inward": "is Informed by",
                    "outward": "informs",
                },
                "inwardIssue": {
                    "key": "PF-1",
                    "fields": {
                        "status": {
                            "name": "New",
                            "statusCategory": {"key": "new"},
                        }
                    },
                },
            }
        ]
    }
    assert not blocked_by_unresolved_from_fields(fields, cfg)


def test_parse_github_pr_url():
    assert parse_github_pr_url("https://github.com/opendatahub-io/odh-dashboard/pull/8758") == (
        "opendatahub-io/odh-dashboard",
        8758,
    )
    assert parse_github_pr_url("Not Applicable") is None
    assert parse_github_pr_url("") is None


def test_slash_lgtm_body_detection():
    assert _body_has_slash_lgtm("/lgtm")
    assert _body_has_slash_lgtm("thanks\n/lgtm\n")
    assert not _body_has_slash_lgtm("lgtm without slash")
    assert not _body_has_slash_lgtm("/lgtmfoo")


def test_user_gave_lgtm_from_comment_or_label():
    data = {
        "comments": [{"author": {"login": "danreed-rh"}, "body": "/lgtm"}],
        "reviews": [],
    }
    assert _user_gave_lgtm(
        data,
        me="danreed-rh",
        assignee_is_user=True,
        labels=(),
        actionable_labels=("lgtm",),
        label_insensitive=True,
    )
    assert _user_gave_lgtm(
        {"comments": [], "reviews": []},
        me="danreed-rh",
        assignee_is_user=True,
        labels=("lgtm",),
        actionable_labels=("lgtm",),
        label_insensitive=True,
    )
    assert not _user_gave_lgtm(
        {"comments": [], "reviews": []},
        me="danreed-rh",
        assignee_is_user=False,
        labels=("lgtm",),
        actionable_labels=("lgtm",),
        label_insensitive=True,
    )
