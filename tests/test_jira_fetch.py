import base64
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-fetch"

captured: dict = {}

ISSUE_JSON = {
    "fields": {"summary": "Extract parse_session_id helper"},
    "renderedFields": {"description": "<p>Refactor the duplicated parser.</p>"},
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        captured["path"] = self.path
        captured["auth"] = self.headers["Authorization"]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(ISSUE_JSON).encode())

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_fetch_emits_prompt():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1"],
        env={
            **os.environ,
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.shutdown()

    assert result.returncode == 0, result.stderr
    assert captured["path"].startswith("/rest/api/3/issue/PROJ-1")
    assert "expand=renderedFields" in captured["path"]
    expected_auth = base64.b64encode(b"bot@example.com:secret-token").decode()
    assert captured["auth"] == f"Basic {expected_auth}"
    assert "PROJ-1" in result.stdout
    assert "Extract parse_session_id helper" in result.stdout
    assert "Refactor the duplicated parser." in result.stdout
    # The workflow relies on Claude pushing a branch named claude/<key>
    # before `ensure-pr` runs, so the prompt must instruct it explicitly.
    assert "git checkout -b claude/PROJ-1" in result.stdout
    assert "git push --set-upstream origin claude/PROJ-1" in result.stdout
