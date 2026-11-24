from datetime import datetime, timezone

from status_overlook.store import TrackStore, TrackedItem
from status_overlook.term_show import (
    format_terminal_digest,
    relative_changed,
    short_key,
    truncate,
    use_color,
)


def _item(**kwargs) -> TrackedItem:
    base = dict(
        id="jira:X-1",
        source="jira",
        key="X-1",
        lifecycle="active",
        action="actionable",
        summary="Do the thing",
        remote_status="In Progress",
        state_changed_at="2026-08-10T12:00:00Z",
    )
    base.update(kwargs)
    return TrackedItem(**base)


def test_short_key_github():
    item = _item(
        id="github-pr:opendatahub-io/odh-dashboard#9099",
        source="github_pr",
        key="opendatahub-io/odh-dashboard#9099",
    )
    assert short_key(item) == "#9099"


def test_short_key_jira():
    assert short_key(_item(key="RHOAIENG-81066")) == "RHOAIENG-81066"


def test_truncate():
    assert truncate("hello", 10) == "hello"
    assert truncate("hello world", 8) == "hello w…"
    assert truncate("ab", 1) == "a"


def test_use_color_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert use_color(force=None) is False
    assert use_color(force=True) is True
    assert use_color(force=False) is False


def test_format_hides_empty_sections_and_omits_ansi_when_color_false():
    store = TrackStore(
        items={
            "jira:A-1": _item(
                id="jira:A-1",
                key="A-1",
                action="actionable",
                reasons=["jira_active_assignee"],
                summary="Act now with a fairly long summary that should truncate",
            ),
            "jira:P-1": _item(
                id="jira:P-1",
                key="P-1",
                action="pending",
                reasons=["jira_in_review"],
                summary="Wait",
                remote_status="Review",
            ),
        }
    )
    text = format_terminal_digest(store, width=40, color=False, verbose=False)
    assert "\033[" not in text
    assert "ACTIONABLE (1)" in text
    assert "PENDING (1)" in text
    assert text.index("ACTIONABLE") < text.index("PENDING")
    assert "BLOCKED" not in text
    assert "RECENTLY DONE" not in text
    assert "[actionable]" not in text
    assert "**" not in text
    assert "Develop" in text
    assert "Waiting for review" in text
    assert "jira_active_assignee" not in text
    assert "https://" not in text
    assert "A-1" in text
    assert "P-1" in text
    # blank line between items within section — only one item per section here
    assert "Act now" in text or "Act now with" in text


def test_format_includes_status_age_and_linked_status_age():
    store = TrackStore(
        items={
            "github-pr:org/repo#4": _item(
                id="github-pr:org/repo#4",
                source="github_pr",
                key="org/repo#4",
                summary="Fix CI",
                remote_status="open+ci_fail",
                state_changed_at="2026-08-10T10:00:00Z",
                action="actionable",
                reasons=["github_ci_failed"],
            ),
            "jira:PAIR-4": _item(
                id="jira:PAIR-4",
                key="PAIR-4",
                summary="linked Jira",
                remote_status="In Progress",
                state_changed_at="2026-08-05T10:00:00Z",
                action="pending",
                reasons=["jira_in_review"],
                pr_link="https://github.com/org/repo/pull/4",
            ),
        }
    )
    text = format_terminal_digest(store, width=120, color=False)
    assert "open+ci_fail · " in text
    assert "↔ PAIR-4  In Progress · " in text


def test_verbose_includes_reasons_and_url():
    store = TrackStore(
        items={
            "jira:A-1": _item(
                id="jira:A-1",
                key="A-1",
                action="actionable",
                reasons=["jira_active_assignee"],
                url="https://example.com/browse/A-1",
            ),
        }
    )
    text = format_terminal_digest(store, width=80, color=False, verbose=True)
    assert "jira_active_assignee" in text
    assert "Develop" in text
    assert "https://example.com/browse/A-1" in text


def test_since_read_filters():
    store = TrackStore(
        items={
            "jira:NEW": _item(
                id="jira:NEW",
                key="NEW-1",
                action="actionable",
                state_changed_at="2026-08-10T12:00:00Z",
                last_read_at=None,
            ),
            "jira:OLD": _item(
                id="jira:OLD",
                key="OLD-1",
                action="actionable",
                state_changed_at="2026-08-01T12:00:00Z",
                last_read_at="2026-08-10T12:00:00Z",
            ),
        }
    )
    text = format_terminal_digest(
        store, width=60, color=False, since_read=True
    )
    assert "NEW-1" in text
    assert "OLD-1" not in text


def test_epics_denoted_and_sorted_last_in_section():
    store = TrackStore(
        items={
            "jira:EPIC": _item(
                id="jira:EPIC",
                key="E-1",
                action="actionable",
                issue_type="Epic",
                summary="Epic work",
                state_changed_at="2026-08-10T14:00:00Z",
            ),
            "jira:STORY": _item(
                id="jira:STORY",
                key="S-1",
                action="actionable",
                issue_type="Story",
                summary="Story work",
                state_changed_at="2026-08-10T10:00:00Z",
            ),
        }
    )
    text = format_terminal_digest(store, width=60, color=False, verbose=False)
    assert "[Epic]" in text
    assert text.index("S-1") < text.index("E-1")
    assert text.index("S-1") < text.index("[Epic]")


def test_show_groups_jira_pr_once():
    store = TrackStore(
        items={
            "jira:RHOAIENG-76231": _item(
                id="jira:RHOAIENG-76231",
                key="RHOAIENG-76231",
                action="pending",
                summary="BUG: dropdowns",
                remote_status="Review",
            ),
            "github-pr:opendatahub-io/odh-dashboard#8787": _item(
                id="github-pr:opendatahub-io/odh-dashboard#8787",
                source="github_pr",
                key="opendatahub-io/odh-dashboard#8787",
                action="actionable",
                summary="fix(RHOAIENG-76231): modal dropdowns",
                remote_status="open+ci_fail",
            ),
        }
    )
    text = format_terminal_digest(store, width=80, color=False, verbose=False)
    assert "ACTIONABLE (1)" in text
    assert "PENDING" not in text
    assert "#8787" in text
    assert "↔ RHOAIENG-76231" in text
    assert "open+ci_fail" in text


def test_relative_changed():
    now = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
    assert relative_changed("2026-08-10T13:30:00Z", now=now) == "30m ago"
    assert relative_changed("2026-08-09T14:00:00Z", now=now) == "1d ago"
