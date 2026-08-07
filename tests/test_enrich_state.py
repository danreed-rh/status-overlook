"""Unit tests for GitHub PR state normalization (no network)."""

from status_overlook.enrich import github_remote_status, normalize_github_pr_state
from status_overlook.models import GitHubPrSnapshot


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
