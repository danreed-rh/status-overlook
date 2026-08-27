from status_overlook.config import AppConfig, WorkingHoursConfig, load_config, save_config
from status_overlook.doctor import CheckResult
from status_overlook.init import _choose_working_hours, next_steps_lines, run_init


def test_next_steps_include_run_show_serve():
    text = "\n".join(next_steps_lines())
    assert "run --force" in text
    assert "status-overlook show" in text
    assert "serve --open" in text


def test_choose_working_hours_new_non_interactive():
    cfg = AppConfig()
    wh = _choose_working_hours(path_exists=False, existing=cfg, non_interactive=True)
    assert wh.enabled


def test_choose_working_hours_old_config_non_interactive_stays_off():
    cfg = AppConfig()
    assert cfg.raw.get("working_hours") is None
    wh = _choose_working_hours(path_exists=True, existing=cfg, non_interactive=True)
    assert not wh.enabled


def test_choose_working_hours_keeps_existing_block():
    existing = AppConfig(working_hours=WorkingHoursConfig(enabled=True, start="09:00"))
    existing.raw = {"working_hours": {"enabled": True}}
    wh = _choose_working_hours(path_exists=True, existing=existing, non_interactive=True)
    assert wh.enabled
    assert wh.start == "09:00"


def test_init_preserves_github_issue_pins(monkeypatch, tmp_path, capsys):
    cfg_path = tmp_path / "config.yaml"
    save_config(
        AppConfig(
            github_login="me",
            jira_site="example.atlassian.net",
            pins_jira=("X-1",),
            pins_github=("org/repo#2",),
            pins_github_issues=("org/repo#1",),
            working_hours=WorkingHoursConfig(enabled=True),
        ),
        cfg_path,
    )

    monkeypatch.setattr("status_overlook.init.config_path", lambda: cfg_path)
    monkeypatch.setattr(
        "status_overlook.init.check_gh",
        lambda: CheckResult("gh", True, "me"),
    )
    monkeypatch.setattr(
        "status_overlook.init.check_acli",
        lambda: CheckResult("acli", True, "ok"),
    )
    monkeypatch.setattr("status_overlook.init.print_doctor", lambda _r: None)
    monkeypatch.setattr("status_overlook.init.probe_github_login", lambda: "me")
    monkeypatch.setattr("status_overlook.init.probe_jira_account_id", lambda: "aid")
    monkeypatch.setattr(
        "status_overlook.init._guess_jira_site_from_acli", lambda: "example.atlassian.net"
    )
    monkeypatch.setattr("status_overlook.init.ensure_private_dir", lambda _p: None)
    monkeypatch.setattr("status_overlook.init.data_dir", lambda: tmp_path)
    monkeypatch.setattr("status_overlook.init.cache_dir", lambda: tmp_path)
    monkeypatch.setattr("status_overlook.init.log_dir", lambda: tmp_path)

    assert run_init(non_interactive=True, force=True) == 0
    out, _ = capsys.readouterr()
    assert "serve --open" in out
    result, _ = load_config(cfg_path)
    assert result.pins_github_issues == ("org/repo#1",)
    assert result.pins_github == ("org/repo#2",)
    assert result.pins_jira == ("X-1",)
