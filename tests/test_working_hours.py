from datetime import datetime
from zoneinfo import ZoneInfo

from status_overlook.config import WorkingHoursConfig, load_config, save_config
from status_overlook.working_hours import is_within_working_hours

UTC = ZoneInfo("UTC")


def _wh(**kwargs) -> WorkingHoursConfig:
    return WorkingHoursConfig(timezone="UTC", **kwargs)


def test_disabled_always_within():
    wh = WorkingHoursConfig.disabled()
    sat = datetime(2026, 8, 15, 22, 0, tzinfo=UTC)
    assert is_within_working_hours(wh, now=sat)


def test_monday_10am_within():
    wh = _wh()
    mon = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)  # Monday
    assert mon.weekday() == 0
    assert is_within_working_hours(wh, now=mon)


def test_saturday_outside():
    wh = _wh()
    sat = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    assert sat.weekday() == 5
    assert not is_within_working_hours(wh, now=sat)


def test_friday_1759_within():
    wh = _wh()
    fri = datetime(2026, 8, 14, 17, 59, tzinfo=UTC)
    assert is_within_working_hours(wh, now=fri)


def test_friday_1800_outside():
    wh = _wh()
    fri = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)
    assert not is_within_working_hours(wh, now=fri)


def test_before_start_outside():
    wh = _wh()
    mon = datetime(2026, 8, 10, 7, 59, tzinfo=UTC)
    assert not is_within_working_hours(wh, now=mon)


def test_missing_working_hours_block_disabled(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "schema_version: 1\n"
        "github:\n  login: ''\n"
        "jira:\n  site: ''\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("status_overlook.config.config_path", lambda: cfg_path)
    cfg, _ = load_config(cfg_path)
    assert not cfg.working_hours.enabled
    sat = datetime(2026, 8, 15, 22, 0, tzinfo=UTC)
    assert is_within_working_hours(cfg.working_hours, now=sat)


def test_run_pipeline_skips_off_hours(monkeypatch, capsys):
    from status_overlook.config import AppConfig, WorkingHoursConfig
    from status_overlook.run import run_pipeline

    cfg = AppConfig(working_hours=WorkingHoursConfig(enabled=True, timezone="UTC"))
    monkeypatch.setattr("status_overlook.run.load_config", lambda: (cfg, None))
    monkeypatch.setattr(
        "status_overlook.run.should_skip_working_hours",
        lambda wh, force=False: True,
    )

    called: list[int] = []

    def _reconcile(**_kwargs):
        called.append(1)
        return None, None, 0

    monkeypatch.setattr("status_overlook.run.run_reconcile", _reconcile)

    assert run_pipeline() == 0
    assert not called
    assert "Outside working hours" in capsys.readouterr().out


def test_run_pipeline_force_bypasses_hours(monkeypatch):
    from status_overlook.config import AppConfig, WorkingHoursConfig
    from status_overlook.run import run_pipeline
    from status_overlook.team import TeamQueue

    cfg = AppConfig(working_hours=WorkingHoursConfig(enabled=True, timezone="UTC"))
    monkeypatch.setattr("status_overlook.run.load_config", lambda: (cfg, None))
    monkeypatch.setattr(
        "status_overlook.run.should_skip_working_hours",
        lambda wh, force=False: False,
    )
    monkeypatch.setattr(
        "status_overlook.run.run_reconcile",
        lambda **_: (None, None, 0),
    )
    monkeypatch.setattr("status_overlook.run.load_store", lambda: type("S", (), {"items": {}})())
    monkeypatch.setattr("status_overlook.run.refresh_team_queue", lambda **_k: TeamQueue())

    # force passes the guard; empty store yields exit 1 (not off-hours skip 0)
    assert run_pipeline(force=True) == 1


def test_run_pipeline_defers_reconcile_write_until_enrichment_succeeds(monkeypatch, capsys):
    from status_overlook.config import AppConfig
    from status_overlook.run import run_pipeline
    from status_overlook.store import TrackStore, TrackedItem
    from status_overlook.team import TeamQueue

    cfg = AppConfig()
    staged_store = TrackStore(
        items={
            "jira:STAGE-1": TrackedItem(
                id="jira:STAGE-1",
                source="jira",
                key="STAGE-1",
                lifecycle="active",
            )
        }
    )
    calls = []
    saves = []
    team_calls = []

    monkeypatch.setattr("status_overlook.run.load_config", lambda: (cfg, None))
    monkeypatch.setattr("status_overlook.run.should_skip_working_hours", lambda *_a, **_k: False)

    def staged_reconcile(**kwargs):
        calls.append(kwargs)
        return staged_store, None, 0

    def failed_enrichment(_store, _cfg):
        raise RuntimeError("enrichment unavailable")

    monkeypatch.setattr("status_overlook.run.run_reconcile", staged_reconcile)
    monkeypatch.setattr("status_overlook.run.enrich_and_classify_store", failed_enrichment)
    monkeypatch.setattr("status_overlook.run.save_store", lambda store: saves.append(store))
    monkeypatch.setattr(
        "status_overlook.run.refresh_team_queue",
        lambda **kwargs: team_calls.append(kwargs) or TeamQueue(),
    )

    assert run_pipeline() == 1
    assert calls == [
        {
            "skip_github": False,
            "skip_jira": False,
            "persist": False,
            "defer_lifecycle": True,
        }
    ]
    assert saves == []
    assert team_calls == [{"limit": 50, "self_login": ""}]
    assert "Enrich error: enrichment unavailable" in capsys.readouterr().out


def test_team_refresh_error_keeps_personal_run_successful(monkeypatch, capsys, tmp_path):
    from status_overlook.config import AppConfig
    from status_overlook.run import run_pipeline
    from status_overlook.store import TrackStore, TrackedItem
    from status_overlook.team import TeamQueue

    store = TrackStore(items={
        "jira:X-1": TrackedItem(id="jira:X-1", source="jira", key="X-1", action="actionable")
    })
    monkeypatch.setattr("status_overlook.run.load_config", lambda: (AppConfig(github_login="me"), None))
    monkeypatch.setattr("status_overlook.run.should_skip_working_hours", lambda *_a, **_k: False)
    monkeypatch.setattr("status_overlook.run.run_reconcile", lambda **_k: (store, None, 0))
    monkeypatch.setattr("status_overlook.run.enrich_and_classify_store", lambda *_a: (1, 0))
    monkeypatch.setattr("status_overlook.run.save_store", lambda _store: tmp_path / "store.json")
    monkeypatch.setattr("status_overlook.run.write_digests", lambda _store: (tmp_path / "digest.md", tmp_path / "digest.json"))
    calls = []

    def refresh_team_queue(**kwargs):
        calls.append(kwargs)
        return TeamQueue(last_error="GitHub unavailable")

    monkeypatch.setattr("status_overlook.run.refresh_team_queue", refresh_team_queue)
    assert run_pipeline() == 0
    assert calls == [{"limit": 50, "self_login": "me"}]
    assert "Team queue refresh failed" in capsys.readouterr().out

    calls.clear()
    assert run_pipeline(skip_github=True) == 0
    assert calls == []


def test_jira_reconcile_failure_does_not_block_team_update(monkeypatch):
    from status_overlook.config import AppConfig
    from status_overlook.run import run_pipeline
    from status_overlook.store import TrackStore
    from status_overlook.team import TeamQueue

    monkeypatch.setattr(
        "status_overlook.run.load_config",
        lambda: (AppConfig(github_login="me"), None),
    )
    monkeypatch.setattr("status_overlook.run.should_skip_working_hours", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "status_overlook.run.run_reconcile", lambda **_k: (TrackStore(), None, 1)
    )
    calls = []

    def refresh_team_queue(**kwargs):
        calls.append(kwargs)
        return TeamQueue(updated_at="2026-11-23T10:00:00Z")

    monkeypatch.setattr("status_overlook.run.refresh_team_queue", refresh_team_queue)
    assert run_pipeline() == 1
    assert calls == [{"limit": 50, "self_login": "me"}]


def test_working_hours_config_roundtrip(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    wh = WorkingHoursConfig(enabled=True, timezone="UTC", start="09:00", end="17:00")
    from status_overlook.config import AppConfig

    save_config(AppConfig(working_hours=wh), cfg_path)
    loaded, _ = load_config(cfg_path)
    assert loaded.working_hours.enabled
    assert loaded.working_hours.timezone == "UTC"
    assert loaded.working_hours.start == "09:00"
    assert loaded.working_hours.end == "17:00"
    assert loaded.working_hours.days == ("mon", "tue", "wed", "thu", "fri")


def test_invalid_timezone_fail_open():
    wh = WorkingHoursConfig(enabled=True, timezone="Not/AZone")
    sat = datetime(2026, 8, 15, 19, 0, tzinfo=UTC)
    assert sat.weekday() == 5
    assert is_within_working_hours(wh, now=sat) is True


def test_invalid_clock_fail_open():
    wh = WorkingHoursConfig(enabled=True, timezone="UTC", start="nope", end="18:00")
    mon = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
    assert is_within_working_hours(wh, now=mon) is True


def test_invalid_clock_fail_open_on_weekend():
    wh = WorkingHoursConfig(enabled=True, timezone="UTC", start="nope", end="18:00")
    sat = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    assert sat.weekday() == 5
    assert is_within_working_hours(wh, now=sat) is True


def test_empty_days_fail_open():
    wh = WorkingHoursConfig(enabled=True, timezone="UTC", days=())
    sat = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
    assert is_within_working_hours(wh, now=sat) is True


def test_should_skip_respects_force(monkeypatch):
    from status_overlook.working_hours import should_skip_working_hours

    wh = _wh()
    monkeypatch.setattr(
        "status_overlook.working_hours.is_within_working_hours",
        lambda cfg, now=None: False,
    )
    assert should_skip_working_hours(wh, force=False) is True
    assert should_skip_working_hours(wh, force=True) is False
