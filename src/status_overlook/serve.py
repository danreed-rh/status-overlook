"""Local localhost web UI — stdlib http.server only."""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from status_overlook.config import load_config
from status_overlook.digest import _iso_now, build_ui_digest, mark_read, write_digests
from status_overlook.run import run_pipeline
from status_overlook.store import load_store, save_store
from status_overlook.working_hours import is_within_working_hours

_WEB_DIR = Path(__file__).resolve().parent / "web"

_run_lock = threading.Lock()
_run_state: dict[str, Any] = {
    "running": False,
    "last_ok": None,
    "last_code": None,
    "last_error": None,
    "last_finished_at": None,
    "started_at": None,
    "phase": None,
    "log_tail": "",
}


def _set_run_state(**kwargs: Any) -> None:
    _run_state.update(kwargs)


def _run_pipeline_bg(
    *,
    skip_github: bool = False,
    skip_jira: bool = False,
    skip_reconcile: bool = False,
) -> None:
    """Caller must hold _run_lock and set running=True before start."""
    import contextlib
    import io

    buf = io.StringIO()
    try:
        _set_run_state(phase="running pipeline", log_tail="")
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = run_pipeline(
                skip_github=skip_github,
                skip_jira=skip_jira,
                skip_reconcile=skip_reconcile,
            )
        text = buf.getvalue()
        _set_run_state(
            last_ok=code == 0,
            last_code=code,
            last_error=None if code == 0 else f"run exited {code}",
            log_tail=text[-1200:] if text else "",
            phase="done" if code == 0 else "failed",
        )
    except Exception as exc:  # noqa: BLE001 — surface to UI
        text = buf.getvalue()
        _set_run_state(
            last_ok=False,
            last_code=1,
            last_error=str(exc),
            log_tail=(text + "\n" + traceback.format_exc())[-1200:],
            phase="failed",
        )
        traceback.print_exc()
    finally:
        _set_run_state(running=False, last_finished_at=_iso_now(), started_at=None)
        _run_lock.release()


class OverlookHandler(BaseHTTPRequestHandler):
    server_version = "StatusOverlookUI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict | list) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8") + b"\n"
        self._send(code, data, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/api/digest":
            qs = parse_qs(parsed.query)
            view = (qs.get("view") or ["all"])[0]
            source = (qs.get("source") or ["both"])[0]
            since_read = (qs.get("since_read") or ["0"])[0] in {"1", "true", "yes"}
            store = load_store()
            payload = build_ui_digest(
                store, view=view, source=source, since_read=since_read
            )
            self._send_json(200, payload)
            return

        if path == "/api/status":
            self._send_json(200, dict(_run_state))
            return

        if path in ("/", "/index.html"):
            self._serve_file(_WEB_DIR / "index.html")
            return

        if path.startswith("/static/"):
            name = path[len("/static/") :]
            if not name or ".." in name or "/" in name or "\\" in name:
                self._send_json(404, {"error": "not found"})
                return
            self._serve_file(_WEB_DIR / name)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/api/run":
            body = self._read_json()
            if not _run_lock.acquire(blocking=False):
                self._send_json(
                    409,
                    {"ok": False, "error": "run already in progress", **dict(_run_state)},
                )
                return
            _set_run_state(
                running=True,
                last_error=None,
                started_at=_iso_now(),
                phase="starting",
                log_tail="",
            )
            thread = threading.Thread(
                target=_run_pipeline_bg,
                kwargs={
                    "skip_github": bool(body.get("skip_github")),
                    "skip_jira": bool(body.get("skip_jira")),
                    "skip_reconcile": bool(body.get("skip_reconcile")),
                },
                daemon=True,
            )
            thread.start()
            self._send_json(202, {"ok": True, "started": True})
            return

        if path == "/api/mark-read":
            body = self._read_json()
            store = load_store()
            ids = body.get("ids")
            all_items = bool(body.get("all", True if not ids else False))
            n = mark_read(
                store,
                ids=list(ids) if isinstance(ids, list) else None,
                all_items=all_items,
            )
            save_store(store)
            write_digests(store)
            self._send_json(200, {"ok": True, "marked": n})
            return

        self._send_json(404, {"error": "not found"})

    def _serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(_WEB_DIR.resolve())
        except ValueError:
            self._send_json(404, {"error": "not found"})
            return
        if not resolved.is_file():
            self._send_json(404, {"error": "not found"})
            return
        data = resolved.read_bytes()
        ctype, _ = mimetypes.guess_type(str(resolved))
        if resolved.suffix == ".js":
            ctype = "application/javascript; charset=utf-8"
        elif resolved.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif resolved.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        self._send(200, data, ctype or "application/octet-stream")


def run_serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    ignore_working_hours: bool = False,
) -> int:
    """Start localhost UI. Blocks until Ctrl-C."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"Refusing non-localhost bind: {host!r} (personal UI only)")
        return 1
    if not (_WEB_DIR / "index.html").is_file():
        print(f"Missing UI files under {_WEB_DIR}")
        return 1

    cfg, _ = load_config()
    if not ignore_working_hours and cfg.working_hours.enabled:
        if not is_within_working_hours(cfg.working_hours):
            print(
                "Outside working hours — not starting UI "
                "(use status-overlook serve --ignore-working-hours)."
            )
            return 0

    httpd = ThreadingHTTPServer((host, port), OverlookHandler)
    url = f"http://{host}:{port}/"
    print(f"Status Overlook UI → {url}")
    print("Agent digests unchanged on disk (status-overlook paths). Ctrl-C to stop.")

    if not ignore_working_hours and cfg.working_hours.enabled:

        def _watch_working_hours() -> None:
            while True:
                time.sleep(60)
                if not is_within_working_hours(cfg.working_hours):
                    print("\nOutside working hours — stopped.")
                    httpd.shutdown()
                    break

        threading.Thread(target=_watch_working_hours, daemon=True).start()

    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0
