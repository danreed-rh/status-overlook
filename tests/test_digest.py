from datetime import datetime, timezone

from status_overlook.digest import (
    build_digest_json,
    build_digest_markdown,
    is_unread,
    mark_read,
    status_age_label,
)
from status_overlook.enrich import state_fingerprint
from status_overlook.store import TrackStore, TrackedItem


def test_fingerprint_stable():
    a = state_fingerprint(
        action="pending",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_waiting",),
    )
    b = state_fingerprint(
        action="pending",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_waiting",),
    )
    assert a == b


def test_fingerprint_changes_on_action():
    a = state_fingerprint(
        action="pending", lifecycle="active", remote_status="open", blocked=False, reasons=()
    )
    b = state_fingerprint(
        action="actionable", lifecycle="active", remote_status="open", blocked=False, reasons=()
    )
    assert a != b


def test_fingerprint_ignores_reason_changes_when_visible_cue_is_same():
    from status_overlook.enrich import state_fingerprint

    a = state_fingerprint(
        action="actionable",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("jira_active_assignee",),
    )
    b = state_fingerprint(
        action="actionable",
        lifecycle="active",
        remote_status="open",
        blocked=False,
        reasons=("github_issue_open",),
    )
    assert a == b


def test_fingerprint_changes_when_displayed_cue_changes():
    from status_overlook.enrich import state_fingerprint

    base = dict(action="actionable", lifecycle="active", remote_status="open")
    review = state_fingerprint(**base, reasons=("github_assignee_to_review",))
    fix_ci = state_fingerprint(**base, reasons=("github_ci_failed",))
    assert review != fix_ci


def test_status_age_label_uses_whole_days_and_clamps_future():
    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert status_age_label("2026-08-10T11:59:30Z", now=now) == "<1d"
    assert status_age_label("2026-08-10T11:40:00Z", now=now) == "<1d"
    assert status_age_label("2026-08-09T12:00:01Z", now=now) == "<1d"
    assert status_age_label("2026-08-09T12:00:00Z", now=now) == "1d"
    assert status_age_label("2026-08-08T12:00:01Z", now=now) == "1d"
    assert status_age_label("2026-08-08T12:00:00Z", now=now) == "2d"
    assert status_age_label("2026-08-05T12:00:00Z", now=now) == "5d"
    assert status_age_label("2026-08-11T12:00:00Z", now=now) == "<1d"
    assert status_age_label("not-a-date", now=now) == ""
    assert status_age_label("", now=now) == ""


def test_unread_and_mark_read():
    store = TrackStore(
        items={
            "jira:X-1": TrackedItem(
                id="jira:X-1",
                source="jira",
                key="X-1",
                lifecycle="active",
                action="pending",
                state_changed_at="2026-08-07T12:00:00Z",
            )
        }
    )
    item = store.items["jira:X-1"]
    assert is_unread(item)
    mark_read(store, all_items=True)
    assert item.last_read_at
    assert not is_unread(item)


def test_digest_sections():
    store = TrackStore(
        items={
            "jira:A-1": TrackedItem(
                id="jira:A-1",
                source="jira",
                key="A-1",
                lifecycle="active",
                action="actionable",
                summary="do it",
                remote_status="In Progress",
                reasons=["jira_active_assignee"],
            ),
            "jira:B-1": TrackedItem(
                id="jira:B-1",
                source="jira",
                key="B-1",
                lifecycle="active",
                action="blocked",
                blocked=True,
                summary="stuck",
                remote_status="In Progress",
                reasons=["jira_blocked_by_unresolved"],
            ),
        }
    )
    md = build_digest_markdown(store)
    assert "## Actionable" in md
    assert "A-1" in md
    assert "Develop" in md
    assert "jira_active_assignee" not in md
    assert "## Blocked" in md
    assert "B-1" in md
    assert "Blocked by issue" in md


def test_digest_epics_marked_and_last():
    from status_overlook.digest import _section_items

    store = TrackStore(
        items={
            "jira:E-1": TrackedItem(
                id="jira:E-1",
                source="jira",
                key="E-1",
                lifecycle="active",
                action="pending",
                issue_type="Epic",
                summary="epic",
                remote_status="In Progress",
                state_changed_at="2026-08-10T15:00:00Z",
            ),
            "jira:S-1": TrackedItem(
                id="jira:S-1",
                source="jira",
                key="S-1",
                lifecycle="active",
                action="pending",
                issue_type="Story",
                summary="story",
                remote_status="Review",
                state_changed_at="2026-08-10T12:00:00Z",
            ),
        }
    )
    items = _section_items(store, "pending")
    assert [i.key for i in items] == ["S-1", "E-1"]
    md = build_digest_markdown(store)
    assert "**E-1** [Epic]" in md


def test_group_pending_jira_with_actionable_pr_via_title():
    """76231-style: Review Jira pending + open PR actionable → one actionable, PR primary."""
    from status_overlook.digest import _section_groups, build_work_groups

    store = TrackStore(
        items={
            "jira:RHOAIENG-76231": TrackedItem(
                id="jira:RHOAIENG-76231",
                source="jira",
                key="RHOAIENG-76231",
                lifecycle="active",
                action="pending",
                summary="BUG: dropdowns in modals",
                remote_status="Review",
                state_changed_at="2026-08-07T19:00:00Z",
            ),
            "github-pr:opendatahub-io/odh-dashboard#8787": TrackedItem(
                id="github-pr:opendatahub-io/odh-dashboard#8787",
                source="github_pr",
                key="opendatahub-io/odh-dashboard#8787",
                lifecycle="active",
                action="actionable",
                summary="fix(RHOAIENG-76231): make modal dropdowns reachable",
                remote_status="open+ci_fail",
                state_changed_at="2026-08-07T19:55:00Z",
            ),
        }
    )
    groups = build_work_groups(store)
    assert len(groups) == 1
    g = groups[0]
    assert g.action == "actionable"
    assert g.primary.key == "opendatahub-io/odh-dashboard#8787"
    assert [m.key for m in g.linked] == ["RHOAIENG-76231"]

    actionable = _section_groups(store, "actionable")
    pending = _section_groups(store, "pending")
    assert len(actionable) == 1
    assert len(pending) == 0
    md = build_digest_markdown(store)
    assert "↔ RHOAIENG-76231" in md
    assert md.count("RHOAIENG-76231") >= 1
    # Pending section empty
    assert "## Pending" in md
    pending_block = md.split("## Pending")[1].split("##")[0]
    assert "_None_" in pending_block


def test_group_via_pr_link_without_title_key():
    from status_overlook.digest import build_work_groups

    store = TrackStore(
        items={
            "jira:ABC-1": TrackedItem(
                id="jira:ABC-1",
                source="jira",
                key="ABC-1",
                lifecycle="active",
                action="pending",
                summary="Something",
                remote_status="Review",
                pr_link="https://github.com/org/repo/pull/99",
            ),
            "github-pr:org/repo#99": TrackedItem(
                id="github-pr:org/repo#99",
                source="github_pr",
                key="org/repo#99",
                lifecycle="active",
                action="actionable",
                summary="Fix the bug",  # no Jira key in title
                remote_status="open",
            ),
        }
    )
    groups = build_work_groups(store)
    assert len(groups) == 1
    assert groups[0].primary.source == "github_pr"
    assert groups[0].linked[0].key == "ABC-1"


def test_actionable_jira_alone_when_pr_not_active():
    """Review+merged case: only Jira active/actionable; no duplicate PR in lists."""
    from status_overlook.digest import build_work_groups

    store = TrackStore(
        items={
            "jira:ABC-2": TrackedItem(
                id="jira:ABC-2",
                source="jira",
                key="ABC-2",
                lifecycle="active",
                action="actionable",
                summary="Move to testing",
                remote_status="Review",
                pr_link="https://github.com/org/repo/pull/50",
                reasons=["jira_review_pr_merged"],
            ),
            "github-pr:org/repo#50": TrackedItem(
                id="github-pr:org/repo#50",
                source="github_pr",
                key="org/repo#50",
                lifecycle="done",
                action="done",
                summary="Fix(ABC-2): merged work",
                remote_status="merged",
            ),
        }
    )
    groups = build_work_groups(store)
    assert len(groups) == 1
    assert groups[0].primary.key == "ABC-2"
    assert groups[0].linked == []
    assert groups[0].action == "actionable"


def test_digest_excludes_ignore_from_recently_done():
    store = TrackStore(
        items={
            "jira:IGN-1": TrackedItem(
                id="jira:IGN-1",
                source="jira",
                key="IGN-1",
                lifecycle="done",
                action="ignore",
                summary="not assignee",
                remote_status="Testing",
            ),
            "jira:DONE-1": TrackedItem(
                id="jira:DONE-1",
                source="jira",
                key="DONE-1",
                lifecycle="done",
                action="done",
                summary="closed",
                remote_status="Closed",
            ),
        }
    )
    md = build_digest_markdown(store)
    assert "DONE-1" in md
    assert "IGN-1" not in md


def test_digest_json_includes_cue_and_reasons():
    from status_overlook.digest import build_digest_json

    store = TrackStore(
        items={
            "jira:A-1": TrackedItem(
                id="jira:A-1",
                source="jira",
                key="A-1",
                lifecycle="active",
                action="actionable",
                reasons=["jira_active_assignee"],
            ),
        }
    )
    payload = build_digest_json(store)
    row = payload["items"][0]
    assert row["reasons"] == ["jira_active_assignee"]
    assert row["cue"] == {
        "id": "develop",
        "label": "Develop",
        "kind": "actionable",
    }


def test_status_age_rendered_for_each_member_of_group():
    store = TrackStore(
        items={
            "jira:PAIR-1": TrackedItem(
                id="jira:PAIR-1",
                source="jira",
                key="PAIR-1",
                lifecycle="active",
                action="pending",
                summary="paired",
                remote_status="In Review",
                state_changed_at="2026-08-05T12:00:00Z",
                reasons=["jira_in_review"],
                pr_link="https://github.com/org/repo/pull/4",
            ),
            "github-pr:org/repo#4": TrackedItem(
                id="github-pr:org/repo#4",
                source="github_pr",
                key="org/repo#4",
                lifecycle="active",
                action="actionable",
                summary="fix(PAIR-1): implement",
                remote_status="open+ci_fail",
                state_changed_at="2026-08-10T11:00:00Z",
            ),
        }
    )
    payload = build_digest_json(store)
    rows = {row["key"]: row for row in payload["items"]}
    assert rows["PAIR-1"]["state_changed_at"] == "2026-08-05T12:00:00Z"
    assert rows["org/repo#4"]["state_changed_at"] == "2026-08-10T11:00:00Z"
    markdown = build_digest_markdown(store)
    assert "[open+ci_fail · " in markdown
    assert "↔ PAIR-1 [In Review · " in markdown
