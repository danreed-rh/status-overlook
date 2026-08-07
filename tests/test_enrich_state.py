"""Unit tests for GitHub PR state normalization (no network)."""

from status_overlook.enrich import (
    _body_has_slash_lgtm,
    _status_is_terminal,
    _user_gave_lgtm,
    github_remote_status,
    normalize_github_pr_state,
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


def test_status_is_terminal_category_and_name():
    cfg = ClassifyConfig()
    assert _status_is_terminal(
        {"name": "Whatever", "statusCategory": {"key": "done"}}, cfg
    )
    assert _status_is_terminal({"name": "Closed", "statusCategory": {"key": "new"}}, cfg)
    assert not _status_is_terminal(
        {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}, cfg
    )


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
