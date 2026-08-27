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
