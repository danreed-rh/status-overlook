from status_overlook.doctor import CheckResult, doctor_ok
from status_overlook.scheduler import (
    parse_every,
    render_plist,
    render_systemd_service,
    render_systemd_timer,
    render_windows_task_xml,
)


def test_parse_every():
    assert parse_every("15m") == 900
    assert parse_every("900s") == 900
    assert parse_every("1h") == 3600
    assert parse_every("30") == 1800  # bare number = minutes


def test_render_plist_contains_label_and_interval():
    xml = render_plist(every_seconds=900, program=["/usr/bin/status-overlook", "run"])
    assert "dev.statusoverlook.sync" in xml
    assert "<integer>900</integer>" in xml
    assert "/usr/bin/status-overlook" in xml
    assert "StartInterval" in xml
    assert "/opt/homebrew/bin" in xml


def test_render_systemd_units():
    service = render_systemd_service(program=["/usr/bin/status-overlook", "run"])
    assert "ExecStart=/usr/bin/status-overlook run" in service
    assert "Type=oneshot" in service
    timer = render_systemd_timer(every_seconds=900)
    assert "OnUnitActiveSec=15min" in timer
    assert "status-overlook.sync.service" in timer
    timer_h = render_systemd_timer(every_seconds=3600)
    assert "OnUnitActiveSec=1h" in timer_h


def test_render_windows_task_xml():
    xml = render_windows_task_xml(
        every_seconds=900, program=[r"C:\Tools\status-overlook.exe", "run"]
    )
    assert "PT15M" in xml
    assert r"C:\Tools\status-overlook.exe" in xml
    assert "run" in xml


def test_doctor_ok_respects_skip_flags():
    results = [
        CheckResult(name="gh", ok=False, detail="nope"),
        CheckResult(name="acli", ok=True, detail="ok"),
    ]
    assert doctor_ok(results, require_gh=False, require_acli=True)
    assert not doctor_ok(results, require_gh=True, require_acli=True)
