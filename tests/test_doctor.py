import subprocess

from status_overlook import doctor
from status_overlook.config import AppConfig
from status_overlook.doctor import acli_install_hint, gh_install_hint


def test_gh_install_hint_per_os():
    assert "brew install gh" in gh_install_hint(platform="darwin")
    linux = gh_install_hint(platform="linux")
    assert "apt install gh" in linux
    assert "dnf install gh" in linux
    assert "winget install GitHub.cli" in gh_install_hint(platform="win32")
    assert "brew install gh" not in gh_install_hint(platform="win32")


def test_acli_install_hint_mentions_path_and_token():
    win = acli_install_hint(platform="win32")
    assert "PATH" in win
    assert "id.atlassian.com" in win
    linux = acli_install_hint(platform="linux")
    assert ".local/bin" in linux
    mac = acli_install_hint(platform="darwin")
    assert "developer.atlassian.com" in mac


def _result(command, code=0, *, stderr="", stdout="[]"):
    return subprocess.CompletedProcess(command, code, stdout=stdout, stderr=stderr)


def test_expired_jira_auth_reports_login_and_skips_qa_field(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/acli")

    def run(command):
        calls.append(command)
        if command[-2:] == ["auth", "status"]:
            return _result(command, 1, stderr="✗ Error: unauthorized")
        return _result(command, 1, stderr="✗ Error: failed to parse JQL")

    monkeypatch.setattr(doctor, "_run", run)
    results = doctor.run_doctor(
        require_gh=False,
        cfg=AppConfig(jira_site="redhat.atlassian.net", jira_qa_contact_field="customfield_10470"),
    )
    assert [r.name for r in results] == ["acli", "jira.site"]
    assert "unauthorized" in results[0].detail
    assert results[0].hint == "Run: acli jira auth login --web"
    assert len(calls) == 2
    assert not doctor.doctor_ok(results, require_gh=False, require_acli=True)


def test_authenticated_jira_search_error_does_not_claim_expired_auth(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/acli")

    def run(command):
        if command[-2:] == ["auth", "status"]:
            return _result(command, stdout="authenticated")
        return _result(command, 1, stderr="✗ Error: failed to parse JQL")

    monkeypatch.setattr(doctor, "_run", run)
    result = doctor.check_acli()
    assert not result.ok
    assert "Jira search failed" in result.detail
    assert "auth login" not in result.hint


def test_qa_field_checked_only_after_basic_search_passes(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/acli")

    def run(command):
        if "cf[10470]" in " ".join(command):
            return _result(command, 1, stderr="field does not exist")
        return _result(command)

    monkeypatch.setattr(doctor, "_run", run)
    results = doctor.run_doctor(
        require_gh=False,
        cfg=AppConfig(jira_site="redhat.atlassian.net", jira_qa_contact_field="customfield_10470"),
    )
    assert [r.name for r in results] == ["acli", "jira.site", "jira.qa_contact_field"]
    assert results[0].ok
    assert not results[-1].ok
    assert "field does not exist" in results[-1].detail


def test_invalid_qa_field_id_still_reports_config_error_when_jira_works(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/acli")
    monkeypatch.setattr(doctor, "_run", lambda command: _result(command))
    results = doctor.run_doctor(
        require_gh=False,
        cfg=AppConfig(jira_qa_contact_field="not-a-field"),
    )
    assert results[0].ok
    assert results[-1].name == "jira.qa_contact_field"
    assert results[-1].detail == "invalid id 'not-a-field'"
