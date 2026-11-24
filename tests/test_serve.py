from status_overlook.digest import build_ui_digest, ui_status_label
from status_overlook.serve import OverlookHandler, _WEB_DIR, _run_failure_message, run_serve
from status_overlook.store import TrackStore, TrackedItem


def _store_pair() -> TrackStore:
    return TrackStore(
        items={
            "jira:RHOAIENG-76231": TrackedItem(
                id="jira:RHOAIENG-76231",
                source="jira",
                key="RHOAIENG-76231",
                lifecycle="active",
                action="pending",
                summary="BUG",
                remote_status="Review",
            ),
            "github-pr:org/repo#1": TrackedItem(
                id="github-pr:org/repo#1",
                source="github_pr",
                key="org/repo#1",
                lifecycle="active",
                action="actionable",
                summary="fix(RHOAIENG-76231): stuff",
                remote_status="open",
                url="https://github.com/org/repo/pull/1",
            ),
            "jira:ONLY-1": TrackedItem(
                id="jira:ONLY-1",
                source="jira",
                key="ONLY-1",
                lifecycle="active",
                action="actionable",
                summary="Jira only",
                remote_status="In Progress",
                reasons=["jira_active_assignee"],
            ),
        },
        updated_at="2026-08-10T12:00:00Z",
    )


def test_build_ui_digest_actionable_groups_pr():
    payload = build_ui_digest(_store_pair(), view="actionable", source="both")
    assert len(payload["sections"]) == 1
    sec = payload["sections"][0]
    assert sec["id"] == "actionable"
    assert sec["count"] == 2
    keys = {g["primary"]["key"] for g in sec["groups"]}
    assert "org/repo#1" in keys
    assert "ONLY-1" in keys
    pr = next(g for g in sec["groups"] if g["primary"]["key"] == "org/repo#1")
    assert pr["linked"][0]["key"] == "RHOAIENG-76231"
    jira_only = next(g for g in sec["groups"] if g["primary"]["key"] == "ONLY-1")
    assert jira_only["cue"] == {
        "id": "develop",
        "label": "Develop",
        "kind": "actionable",
    }
    assert jira_only["primary"]["cue"]["id"] == "develop"


def test_ui_digest_exposes_independent_group_timestamps():
    store = _store_pair()
    store.items["github-pr:org/repo#1"].state_changed_at = "2026-08-10T11:00:00Z"
    store.items["jira:RHOAIENG-76231"].state_changed_at = "2026-08-05T11:00:00Z"
    payload = build_ui_digest(store, view="actionable", source="both")
    group = next(
        g for g in payload["sections"][0]["groups"]
        if g["primary"]["key"] == "org/repo#1"
    )
    assert group["primary"]["state_changed_at"] == "2026-08-10T11:00:00Z"
    assert group["linked"][0]["state_changed_at"] == "2026-08-05T11:00:00Z"
    assert group["status_item_id"] == "github-pr:org/repo#1"


def test_ui_digest_uses_open_pr_status_even_when_jira_is_primary():
    store = _store_pair()
    jira = store.items["jira:RHOAIENG-76231"]
    pr = store.items["github-pr:org/repo#1"]
    jira.action = "actionable"
    jira.state_changed_at = "2026-08-05T11:00:00Z"
    pr.action = "pending"
    pr.remote_status = "draft"
    pr.state_changed_at = "2026-08-10T11:00:00Z"

    group = next(
        g for g in build_ui_digest(store, view="actionable")["sections"][0]["groups"]
        if g["primary"]["key"] == jira.key
    )
    assert group["primary"]["state_changed_at"] == jira.state_changed_at
    assert group["linked"][0]["state_changed_at"] == pr.state_changed_at
    assert group["status_item_id"] == pr.id
    assert group["linked"][0]["display_status"] == "Draft"


def test_ui_digest_falls_back_to_jira_status_after_pr_closes():
    store = _store_pair()
    jira = store.items["jira:RHOAIENG-76231"]
    pr = store.items["github-pr:org/repo#1"]
    jira.action = "actionable"
    jira.state_changed_at = "2026-08-05T11:00:00Z"
    pr.action = "pending"
    pr.remote_status = "closed"
    pr.state_changed_at = "2026-08-10T11:00:00Z"

    group = next(
        g for g in build_ui_digest(store, view="actionable")["sections"][0]["groups"]
        if g["primary"]["key"] == jira.key
    )
    assert group["status_item_id"] == jira.id
    assert group["primary"]["state_changed_at"] == jira.state_changed_at

    pr.lifecycle = "done"
    pr.action = "done"
    group = next(
        g for g in build_ui_digest(store, view="actionable")["sections"][0]["groups"]
        if g["primary"]["key"] == jira.key
    )
    assert group["linked"] == []
    assert group["status_item_id"] == jira.id


def test_ui_digest_does_not_treat_unknown_pr_state_as_open():
    store = _store_pair()
    jira = store.items["jira:RHOAIENG-76231"]
    pr = store.items["github-pr:org/repo#1"]
    jira.action = "actionable"
    pr.action = "pending"
    pr.remote_status = ""

    group = next(
        g for g in build_ui_digest(store, view="actionable")["sections"][0]["groups"]
        if g["primary"]["key"] == jira.key
    )
    assert group["status_item_id"] == jira.id


def test_pr_display_status_is_readable_without_changing_raw_status():
    store = _store_pair()
    pr = store.items["github-pr:org/repo#1"]
    pr.remote_status = "open+ci_fail+unresolved_threads"
    payload = build_ui_digest(store, view="actionable")
    group = next(
        g for g in payload["sections"][0]["groups"]
        if g["primary"]["key"] == "org/repo#1"
    )
    assert group["primary"]["remote_status"] == "open+ci_fail+unresolved_threads"
    assert group["primary"]["display_status"] == "Open · CI failing · Unresolved review threads"
    assert group["linked"][0]["display_status"] == "Review"


def test_pr_display_status_handles_variants_and_unknown_values():
    item = TrackedItem(id="github-pr:org/repo#2", source="github_pr", key="org/repo#2")
    examples = {
        "open": "Open",
        "open+ci_fail": "Open · CI failing",
        "open+unresolved_threads+awaiting_author": "Open · Unresolved review threads · Awaiting author",
        "draft": "Draft",
        "merged": "Merged",
        "closed": "Closed",
        "open+future_signal": "open+future_signal",
    }
    for raw, expected in examples.items():
        item.remote_status = raw
        assert ui_status_label(item) == expected


def test_ui_refresh_reloads_fingerprint_dependencies_before_enrichment(monkeypatch):
    import importlib

    from status_overlook.serve import _reload_pipeline_modules

    reloaded = []

    def record_reload(module):
        reloaded.append(module.__name__)
        return module

    monkeypatch.setattr(importlib, "reload", record_reload)
    run_mod = _reload_pipeline_modules()

    assert reloaded.index("status_overlook.cues") < reloaded.index("status_overlook.state")
    assert reloaded.index("status_overlook.state") < reloaded.index("status_overlook.enrich")
    assert reloaded.index("status_overlook.enrich") < reloaded.index("status_overlook.run")
    assert run_mod.__name__ == "status_overlook.run"


def test_refresh_error_prefers_first_doctor_failure_and_hint():
    log = (
        '127.0.0.1 - "GET /api/status HTTP/1.1" 200 -\n'
        "gh: ok — user\n"
        "acli: FAIL — Jira authentication failed: unauthorized\n"
        "  → Run: acli jira auth login --web\n"
        "jira.site: ok — redhat.atlassian.net\n"
    )
    message = _run_failure_message(log, 1)
    assert message.startswith("acli: FAIL — Jira authentication failed: unauthorized")
    assert "Run: acli jira auth login --web" in message
    assert _run_failure_message("Provider error: gh down\n", 1) == "Provider error: gh down"
    assert _run_failure_message("Track store empty — nothing to enrich.\n", 1).startswith("Track store empty")
    assert _run_failure_message("", 1) == "run exited 1"


def test_build_ui_digest_source_github():
    payload = build_ui_digest(_store_pair(), view="all", source="github")
    all_groups = [g for s in payload["sections"] for g in s["groups"]]
    assert all(
        any(m["source"] in ("github_pr", "github_issue") for m in [g["primary"], *g["linked"]])
        for g in all_groups
    )
    # ONLY-1 is jira-only actionable — excluded
    primaries = {g["primary"]["key"] for g in all_groups}
    assert "ONLY-1" not in primaries
    assert "org/repo#1" in primaries


def test_build_ui_digest_all_has_three_active_sections():
    payload = build_ui_digest(_store_pair(), view="all")
    assert [s["id"] for s in payload["sections"]] == [
        "actionable",
        "pending",
        "blocked",
    ]


def test_build_ui_digest_everything_includes_done():
    store = _store_pair()
    store.items["jira:DONE-1"] = TrackedItem(
        id="jira:DONE-1",
        source="jira",
        key="DONE-1",
        lifecycle="done",
        action="done",
        summary="Closed",
        remote_status="Closed",
    )
    payload = build_ui_digest(store, view="everything")
    assert [s["id"] for s in payload["sections"]] == [
        "actionable",
        "pending",
        "blocked",
        "done",
    ]
    done = next(s for s in payload["sections"] if s["id"] == "done")
    assert done["count"] >= 1
    assert any(g["primary"]["key"] == "DONE-1" for g in done["groups"])


def test_web_assets_present():
    assert (_WEB_DIR / "index.html").is_file()
    assert (_WEB_DIR / "app.js").is_file()
    assert (_WEB_DIR / "style.css").is_file()
    assert (_WEB_DIR / "team.html").is_file()
    assert (_WEB_DIR / "team.js").is_file()
    assert (_WEB_DIR / "team.css").is_file()
    assert (_WEB_DIR / "header.js").is_file()
    assert (_WEB_DIR / "header.html").is_file()


def test_team_page_and_members_api(monkeypatch, tmp_path):
    import json
    from status_overlook import serve, team
    from status_overlook.config import AppConfig

    monkeypatch.setattr(team, "team_members_path", lambda: tmp_path / "team_members.json")
    monkeypatch.setattr(team, "team_queue_path", lambda: tmp_path / "team_queue.json")
    monkeypatch.setattr(serve, "load_config", lambda: (AppConfig(github_login="danreed-rh"), None))
    handler = OverlookHandler.__new__(OverlookHandler)
    responses = []
    handler._send_json = lambda code, data: responses.append((code, data))

    handler.path = "/api/team"
    handler.do_GET()
    assert responses[-1] == (200, {"members": [], "updated_at": "", "last_attempt_at": "", "last_error": "", "items": []})

    (tmp_path / "team_queue.json").write_text("[]")
    handler.do_GET()
    assert responses[-1][0] == 500
    assert "Invalid team queue" in responses[-1][1]["error"]
    (tmp_path / "team_queue.json").unlink()

    handler.path = "/api/team/members"
    handler._read_json = lambda: {"action": "add", "login": "Gkrumbach07"}
    handler.do_POST()
    assert responses[-1] == (200, {"ok": True, "members": ["Gkrumbach07"]})
    assert json.loads((tmp_path / "team_members.json").read_text())["members"] == ["Gkrumbach07"]

    handler._read_json = lambda: {"action": "add", "login": "danreed-rh"}
    handler.do_POST()
    assert responses[-1][0] == 400

    handler._read_json = lambda: {"action": "remove", "login": "Gkrumbach07"}
    handler.do_POST()
    assert responses[-1] == (200, {"ok": True, "members": []})

    files = []
    handler._serve_file = lambda path: files.append(path)
    handler.path = "/team"
    handler.do_GET()
    assert files[-1] == _WEB_DIR / "team.html"


def test_refuse_non_localhost():
    assert run_serve(host="0.0.0.0", port=8765) == 1


def test_handler_serves_index(monkeypatch):
    from io import BytesIO
    from status_overlook import serve as serve_mod

    class FakeServer:
        pass

    class Handler(OverlookHandler):
        def __init__(self):
            self.requestline = "GET / HTTP/1.1"
            self.command = "GET"
            self.path = "/"
            self.headers = {}
            self.wfile = BytesIO()
            self.rfile = BytesIO()
            self.request_version = "HTTP/1.1"
            self.client_address = ("127.0.0.1", 12345)
            self.server = FakeServer()
            self._headers_buffer = []
            self._status = None

        def send_response(self, code, message=None):
            self._status = code

        def send_header(self, k, v):
            self._headers_buffer.append((k, v))

        def end_headers(self):
            pass

        def address_string(self):
            return "127.0.0.1"

    # Minimal parse: call do_GET after setting path via urlparse path
    h = Handler()
    h.path = "/"
    h.do_GET()
    assert h._status == 200
    body = h.wfile.getvalue().decode("utf-8")
    assert "Status Overlook" in body
    assert '<a href="/" aria-current="page">My work</a>' in body
    assert "<!-- GLOBAL_HEADER -->" not in body

    team = Handler()
    team.path = "/team"
    team.do_GET()
    assert team._status == 200
    body = team.wfile.getvalue().decode("utf-8")
    assert '<a href="/team" aria-current="page">Team review</a>' in body
    assert "<!-- GLOBAL_HEADER -->" not in body


def test_ui_url_ipv4_and_ipv6():
    import socket

    from status_overlook.serve import OverlookHTTPServer, OverlookHTTPServerV6, _ui_url

    assert _ui_url("127.0.0.1", 8765) == "http://127.0.0.1:8765/"
    assert _ui_url("localhost", 8765) == "http://127.0.0.1:8765/"
    assert _ui_url("::1", 8765) == "http://[::1]:8765/"
    assert OverlookHTTPServerV6.address_family == socket.AF_INET6
    assert OverlookHTTPServer.address_family == socket.AF_INET


def test_web_assets_cross_platform():
    css = (_WEB_DIR / "style.css").read_text(encoding="utf-8")
    html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
    team_html = (_WEB_DIR / "team.html").read_text(encoding="utf-8")
    header_js = (_WEB_DIR / "header.js").read_text(encoding="utf-8")
    header_html = (_WEB_DIR / "header.html").read_text(encoding="utf-8")
    js = (_WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "prefers-color-scheme: light" in css
    assert "color-mix" in css
    assert "forced-colors" in css
    assert "Highlight" in css
    assert 'name="color-scheme"' in html
    assert 'id="uiOrigin"' in html
    assert ":8765" not in html
    for page in (html, team_html):
        assert "<!-- GLOBAL_HEADER -->" in page
        assert '<script src="/static/header.js"></script>' in page
        assert 'id="btnRun"' not in page
    assert 'aria-live="polite"' in header_html
    assert 'id="btnRun"' in header_html
    assert "force: Boolean(force)" in header_js
    assert "StatusOverlookHeader.refresh(false)" in js
    assert 'status-overlook:refresh-complete' in header_js
    assert "statusAgeMarkup" in js
    assert ".status-age" in css
    assert 'data-page="personal"' in html
    assert 'data-page="team"' in team_html
    assert 'data.skipped === "working_hours"' in header_js
    assert "response.status === 202" in header_js


def test_api_run_skips_off_hours(monkeypatch):
    from io import BytesIO

    from status_overlook.config import AppConfig, WorkingHoursConfig

    class FakeServer:
        pass

    class Handler(OverlookHandler):
        def __init__(self):
            self.requestline = "POST /api/run HTTP/1.1"
            self.command = "POST"
            self.path = "/api/run"
            self.headers = {"Content-Length": "2"}
            self.wfile = BytesIO()
            self.rfile = BytesIO(b"{}")
            self.request_version = "HTTP/1.1"
            self.client_address = ("127.0.0.1", 12345)
            self.server = FakeServer()
            self._headers_buffer = []
            self._status = None

        def send_response(self, code, message=None):
            self._status = code

        def send_header(self, k, v):
            self._headers_buffer.append((k, v))

        def end_headers(self):
            pass

        def address_string(self):
            return "127.0.0.1"

    monkeypatch.setattr(
        "status_overlook.serve.load_config",
        lambda: (AppConfig(working_hours=WorkingHoursConfig(enabled=True)), None),
    )
    monkeypatch.setattr(
        "status_overlook.serve.should_skip_working_hours",
        lambda _wh, force=False: not force,
    )

    h = Handler()
    h.do_POST()
    assert h._status == 200
    import json

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["skipped"] == "working_hours"
    assert payload["started"] is False
    from status_overlook.serve import _run_state

    assert _run_state["skipped_working_hours"] is True


def test_api_run_force_starts_thread(monkeypatch):
    from io import BytesIO

    from status_overlook.config import AppConfig, WorkingHoursConfig

    class FakeLock:
        def acquire(self, blocking=False):
            return True

        def release(self):
            pass

    started: list[dict] = []

    class FakeThread:
        def __init__(self, target=None, kwargs=None, daemon=None):
            self.kwargs = kwargs or {}

        def start(self):
            started.append(self.kwargs)

    class FakeServer:
        pass

    class Handler(OverlookHandler):
        def __init__(self):
            self.requestline = "POST /api/run HTTP/1.1"
            self.command = "POST"
            self.path = "/api/run"
            self.headers = {"Content-Length": "16"}
            self.wfile = BytesIO()
            self.rfile = BytesIO(b'{"force": true}')
            self.request_version = "HTTP/1.1"
            self.client_address = ("127.0.0.1", 12345)
            self.server = FakeServer()
            self._headers_buffer = []
            self._status = None

        def send_response(self, code, message=None):
            self._status = code

        def send_header(self, k, v):
            self._headers_buffer.append((k, v))

        def end_headers(self):
            pass

        def address_string(self):
            return "127.0.0.1"

    monkeypatch.setattr(
        "status_overlook.serve.load_config",
        lambda: (AppConfig(working_hours=WorkingHoursConfig(enabled=True)), None),
    )
    monkeypatch.setattr(
        "status_overlook.serve.should_skip_working_hours",
        lambda _wh, force=False: not force,
    )
    monkeypatch.setattr("status_overlook.serve._run_lock", FakeLock())
    monkeypatch.setattr("status_overlook.serve.threading.Thread", FakeThread)

    h = Handler()
    h.do_POST()
    assert h._status == 202
    assert started and started[0].get("force") is True


def test_api_run_string_force_does_not_bypass_hours(monkeypatch):
    from io import BytesIO
    import json

    from status_overlook.config import AppConfig, WorkingHoursConfig

    class FakeServer:
        pass

    raw = b'{"force": "false"}'

    class Handler(OverlookHandler):
        def __init__(self):
            self.requestline = "POST /api/run HTTP/1.1"
            self.command = "POST"
            self.path = "/api/run"
            self.headers = {"Content-Length": str(len(raw))}
            self.wfile = BytesIO()
            self.rfile = BytesIO(raw)
            self.request_version = "HTTP/1.1"
            self.client_address = ("127.0.0.1", 12345)
            self.server = FakeServer()
            self._headers_buffer = []
            self._status = None

        def send_response(self, code, message=None):
            self._status = code

        def send_header(self, k, v):
            self._headers_buffer.append((k, v))

        def end_headers(self):
            pass

        def address_string(self):
            return "127.0.0.1"

    monkeypatch.setattr(
        "status_overlook.serve.load_config",
        lambda: (AppConfig(working_hours=WorkingHoursConfig(enabled=True)), None),
    )
    monkeypatch.setattr(
        "status_overlook.serve.should_skip_working_hours",
        lambda _wh, force=False: not force,
    )

    h = Handler()
    h.do_POST()
    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["skipped"] == "working_hours"
