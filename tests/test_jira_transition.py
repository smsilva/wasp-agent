import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-transition"

captured: dict = {}

TRANSITIONS = {
    "transitions": [
        {"id": "11", "name": "To Do"},
        {"id": "31", "name": "In Review"},
    ]
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        captured["get_path"] = self.path
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(TRANSITIONS).encode())

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        captured["post_path"] = self.path
        captured["post_body"] = json.loads(self.rfile.read(length))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_transition_resolves_name_and_posts_id():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "in review"],  # lowercase -> case-insensitive match
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
    assert captured["get_path"] == "/rest/api/3/issue/PROJ-1/transitions"
    assert captured["post_path"] == "/rest/api/3/issue/PROJ-1/transitions"
    assert captured["post_body"] == {"transition": {"id": "31"}}


def test_jira_transition_unknown_name_fails():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "Nonexistent"],
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

    assert result.returncode != 0
    assert "Transition not found" in result.stderr
