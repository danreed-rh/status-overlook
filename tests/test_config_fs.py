import os
from pathlib import Path

from status_overlook.config import AppConfig, load_config, save_config
from status_overlook.fsutil import DIR_MODE, FILE_MODE, ensure_private_dir, write_private_text


def test_write_private_modes(tmp_path: Path):
    d = tmp_path / "data"
    ensure_private_dir(d)
    f = d / "x.txt"
    write_private_text(f, "hi\n")
    assert f.read_text() == "hi\n"
    assert stat_mode(d) == DIR_MODE
    assert stat_mode(f) == FILE_MODE


def test_save_load_config_roundtrip(tmp_path: Path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg = AppConfig(
        github_login="danreed-rh",
        jira_site="redhat.atlassian.net",
        jira_account_id="abc-123",
        jira_qa_contact_field="customfield_10470",
    )
    save_config(cfg, cfg_path)
    loaded, path = load_config(cfg_path)
    assert path == cfg_path
    assert loaded.github_login == "danreed-rh"
    assert loaded.jira_site == "redhat.atlassian.net"
    assert loaded.jira_account_id == "abc-123"
    assert loaded.jira_qa_contact_field == "customfield_10470"
    assert "In Progress" in loaded.status_active
    assert loaded.pins_github_issues == ()


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
