"""Unit tests for GitHub PR state normalization (no network)."""

import json

from status_overlook.config import AppConfig
from status_overlook.enrich import (
    Identity,
    _acli_workitem_search,
    _body_has_slash_lgtm,
    _jira_search_fields,
    _parse_acli_disallowed_field,
    _qa_contact_is_user,
    _status_is_terminal,
    _user_gave_lgtm,
    apply_classification_to_item,
    blocked_by_unresolved_from_fields,
    enrich_jira_issues,
    github_remote_status,
    normalize_github_pr_state,
    parse_github_pr_url,
)
from status_overlook.models import ActionState, ClassifyConfig, GitHubPrSnapshot
from status_overlook.store import TrackedItem


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


def test_state_changed_at_tracks_visible_transitions_not_reason_only_changes():
    item = TrackedItem(
        id="github-pr:org/repo#4",
        source="github_pr",
        key="org/repo#4",
        lifecycle="active",
    )

    assert apply_classification_to_item(
        item,
        action=ActionState.ACTIONABLE,
        lifecycle="active",
        remote_status="open+ci_fail",
        blocked=False,
        reasons=("github_ci_failed",),
        now_s="2026-08-10T10:00:00Z",
    )
    assert item.state_changed_at == "2026-08-10T10:00:00Z"

    assert apply_classification_to_item(
        item,
        action=ActionState.ACTIONABLE,
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("internal_signal_one",),
        now_s="2026-08-10T11:00:00Z",
    )
    assert item.state_changed_at == "2026-08-10T11:00:00Z"

    assert not apply_classification_to_item(
        item,
        action=ActionState.ACTIONABLE,
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("internal_signal_two",),
        now_s="2026-08-10T12:00:00Z",
    )
    assert item.state_changed_at == "2026-08-10T11:00:00Z"

    # Same remote status and action, but the displayed cue changes to Fix CI.
    assert apply_classification_to_item(
        item,
        action=ActionState.ACTIONABLE,
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_ci_failed",),
        now_s="2026-08-10T13:00:00Z",
    )
    assert item.state_changed_at == "2026-08-10T13:00:00Z"


def test_jira_status_round_trip_resets_on_each_observed_transition():
    item = TrackedItem(
        id="jira:PAIR-1",
        source="jira",
        key="PAIR-1",
        lifecycle="active",
    )
    transitions = (
        ("In Progress", "2026-08-10T10:00:00Z"),
        ("In Review", "2026-08-10T11:00:00Z"),
        ("In Progress", "2026-08-10T12:00:00Z"),
    )
    for status, now_s in transitions:
        changed = apply_classification_to_item(
            item,
            action=ActionState.ACTIONABLE,
            lifecycle="active",
            remote_status=status,
            blocked=False,
            reasons=("jira_active_assignee",),
            now_s=now_s,
        )
        assert changed
        assert item.state_changed_at == now_s


def test_pr_workflow_round_trip_resets_on_each_observed_transition():
    item = TrackedItem(
        id="github-pr:org/repo#5",
        source="github_pr",
        key="org/repo#5",
        lifecycle="active",
    )
    transitions = (
        (
            "open+unresolved_threads",
            ActionState.ACTIONABLE,
            ("github_unresolved_reviews",),
            "2026-08-10T10:00:00Z",
        ),
        (
            "open+awaiting_author",
            ActionState.PENDING,
            ("github_assignee_waiting_on_author",),
            "2026-08-10T11:00:00Z",
        ),
        (
            "open+unresolved_threads",
            ActionState.ACTIONABLE,
            ("github_unresolved_reviews",),
            "2026-08-10T12:00:00Z",
        ),
    )
    for remote_status, action, reasons, now_s in transitions:
        changed = apply_classification_to_item(
            item,
            action=action,
            lifecycle="active",
            remote_status=remote_status,
            blocked=False,
            reasons=reasons,
            now_s=now_s,
        )
        assert changed
        assert item.state_changed_at == now_s


def test_failed_pr_enrichment_preserves_observed_state(monkeypatch):
    from status_overlook.config import AppConfig
    from status_overlook.enrich import enrich_and_classify_store, state_fingerprint
    from status_overlook.store import TrackStore

    item = TrackedItem(
        id="github-pr:org/repo#6",
        source="github_pr",
        key="org/repo#6",
        lifecycle="active",
        action="actionable",
        remote_status="open+ci_fail",
        reasons=["github_ci_failed"],
        state_changed_at="2026-08-10T10:00:00Z",
    )
    item.state_fingerprint = state_fingerprint(
        action=item.action,
        lifecycle=item.lifecycle,
        remote_status=item.remote_status,
        blocked=item.blocked,
        reasons=item.reasons,
    )
    store = TrackStore(items={item.id: item})
    before = (item.action, item.lifecycle, item.remote_status, item.state_changed_at)

    monkeypatch.setattr(
        "status_overlook.enrich.resolve_identity",
        lambda _cfg: Identity(github_login="me", jira_account_id=""),
    )
    monkeypatch.setattr("status_overlook.enrich.enrich_jira_issues", lambda *a, **k: {})

    def fail_enrichment(*_args, **_kwargs):
        raise RuntimeError("temporary gh error")

    monkeypatch.setattr("status_overlook.enrich.enrich_github_pr", fail_enrichment)
    enrich_and_classify_store(store, AppConfig())

    assert (item.action, item.lifecycle, item.remote_status, item.state_changed_at) == before


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


def test_jira_search_fields_omit_custom_and_links():
    fields = _jira_search_fields()
    assert "customfield" not in fields
    assert "issuelinks" not in fields
    assert "status" in fields


def test_qa_contact_is_user_dict_and_list():
    aid = "acc-1"
    assert _qa_contact_is_user({"accountId": "acc-1"}, aid)
    assert not _qa_contact_is_user({"accountId": "other"}, aid)
    assert _qa_contact_is_user([{"accountId": "acc-1"}], aid)
    assert not _qa_contact_is_user(None, aid)
    assert not _qa_contact_is_user({"accountId": "acc-1"}, "")


def test_enrich_jira_qa_via_view_not_search(monkeypatch):
    from status_overlook import enrich as enrich_mod

    search_payload = [
        {
            "key": "RHOAIENG-82724",
            "fields": {
                "summary": "k8s name",
                "status": {"name": "Testing"},
                "assignee": {"accountId": "other"},
                "labels": [],
                "issuetype": {"name": "Bug"},
            },
        }
    ]
    view_payload = {
        "fields": {
            "issuelinks": [],
            "customfield_10470": {"accountId": "me-account"},
        }
    }

    def fake_run(cmd, **_kwargs):
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        if "search" in cmd:
            fields = cmd[cmd.index("--fields") + 1]
            assert "customfield_" not in fields
            Proc.stdout = json.dumps(search_payload)
            return Proc()
        if "view" in cmd:
            fields = cmd[cmd.index("--fields") + 1]
            assert "customfield_10470" in fields
            assert "issuelinks" in fields
            Proc.stdout = json.dumps(view_payload)
            return Proc()
        raise AssertionError(cmd)

    monkeypatch.setattr(enrich_mod.subprocess, "run", fake_run)
    cfg = AppConfig(
        jira_site="redhat.atlassian.net",
        jira_account_id="me-account",
        jira_qa_contact_field="customfield_10470",
    )
    identity = Identity(github_login="x", jira_account_id="me-account")
    out = enrich_jira_issues(["RHOAIENG-82724"], cfg=cfg, identity=identity)
    snap, summary, url = out["RHOAIENG-82724"]
    assert snap.qa_contact_is_user is True
    assert snap.assignee_is_user is False
    assert summary == "k8s name"
    assert url.endswith("/browse/RHOAIENG-82724")


def test_parse_acli_disallowed_field():
    err = "✗ Error: field 'customfield_10470' is not allowed"
    assert _parse_acli_disallowed_field(err) == "customfield_10470"
    assert _parse_acli_disallowed_field("other failure") is None


def test_acli_search_retries_without_disallowed_field(monkeypatch):
    from status_overlook import enrich as enrich_mod

    calls: list[str] = []

    def fake_run(cmd, **_kwargs):
        class Proc:
            returncode = 0
            stdout = "[]"
            stderr = ""

        fields = cmd[cmd.index("--fields") + 1]
        calls.append(fields)
        if "customfield_10470" in fields:
            Proc.returncode = 1
            Proc.stderr = "✗ Error: field 'customfield_10470' is not allowed"
            Proc.stdout = ""
        return Proc()

    monkeypatch.setattr(enrich_mod.subprocess, "run", fake_run)
    rows = _acli_workitem_search(
        jql="key = X-1",
        fields="key,summary,customfield_10470",
        limit=1,
    )
    assert rows == []
    assert calls[0] == "key,summary,customfield_10470"
    assert calls[1] == "key,summary"
