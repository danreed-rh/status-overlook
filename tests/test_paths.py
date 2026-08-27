import sys

from status_overlook import paths


def test_windows_paths(monkeypatch):
    monkeypatch.setattr(paths, "_is_macos", lambda: False)
    monkeypatch.setattr(paths, "_is_windows", lambda: True)
    monkeypatch.setattr(paths, "_is_linux", lambda: False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(key, raising=False)

    assert str(paths.config_dir()).replace("\\", "/").endswith("AppData/Local/status-overlook")
    assert paths.data_dir() == paths.config_dir()
    assert paths.cache_dir() == paths.config_dir() / "Cache"
    assert paths.log_dir() == paths.config_dir() / "Logs"
    managed = paths.all_managed_paths()
    assert paths.windows_task_xml_path() in managed


def test_linux_systemd_paths_in_managed(monkeypatch):
    monkeypatch.setattr(paths, "_is_macos", lambda: False)
    monkeypatch.setattr(paths, "_is_windows", lambda: False)
    monkeypatch.setattr(paths, "_is_linux", lambda: True)
    monkeypatch.setattr(sys, "platform", "linux")
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(key, raising=False)

    managed = paths.all_managed_paths()
    assert paths.systemd_service_path() in managed
    assert paths.systemd_timer_path() in managed
