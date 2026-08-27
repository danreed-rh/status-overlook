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

    # force passes the guard; empty store yields exit 1 (not off-hours skip 0)
    assert run_pipeline(force=True) == 1


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
