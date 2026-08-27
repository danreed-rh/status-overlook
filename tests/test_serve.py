from status_overlook.digest import build_ui_digest
from status_overlook.serve import OverlookHandler, _WEB_DIR, run_serve
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
