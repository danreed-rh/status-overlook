from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_contrib_systemd_service_is_portable():
    text = (ROOT / "contrib/systemd/status-overlook.sync.service").read_text(
        encoding="utf-8"
    )
    assert "/Users/" not in text
    assert "Cursor.app" not in text
    assert "/opt/homebrew" not in text
    assert "ExecStart=status-overlook run" in text
    assert "%h/.local/bin" in text
    assert text.index("%h/.local/bin") < text.index("/usr/bin")


def test_contrib_macos_plist_has_placeholders_not_owner_home():
    text = (ROOT / "contrib/macos/dev.statusoverlook.sync.plist.example").read_text(
        encoding="utf-8"
    )
    assert "/Users/dareed" not in text
    assert "Cursor.app" not in text
    assert "/Users/YOU/" in text
    assert "/path/to/status-overlook" in text


def test_contrib_windows_xml_documents_binary_name():
    raw = (ROOT / "contrib/windows/StatusOverlook.Sync.xml").read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8")
    assert "status-overlook" in text
    assert "InteractiveToken" in text
    assert "P365D" in text
