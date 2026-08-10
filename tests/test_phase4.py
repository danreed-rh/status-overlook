from status_overlook.doctor import CheckResult, doctor_ok
from status_overlook.scheduler import parse_every, render_plist


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


def test_doctor_ok_respects_skip_flags():
    results = [
        CheckResult(name="gh", ok=False, detail="nope"),
        CheckResult(name="acli", ok=True, detail="ok"),
    ]
    assert doctor_ok(results, require_gh=False, require_acli=True)
    assert not doctor_ok(results, require_gh=True, require_acli=True)
