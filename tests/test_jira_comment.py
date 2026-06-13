import base64
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "jira-comment"

captured: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        captured["path"] = self.path
        captured["auth"] = self.headers["Authorization"]
        captured["body"] = json.loads(self.rfile.read(length))
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence server logging
        pass


def test_jira_comment_posts_adf_comment():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.handle_request, daemon=True).start()

    result = subprocess.run(
        [str(SCRIPT), "PROJ-1", "Agent picked this up. Run: http://x/123"],
        env={
            **os.environ,  # herda PATH para achar bash/curl/jq
            "JIRA_BASE_URL": f"http://127.0.0.1:{port}",
            "JIRA_EMAIL": "bot@example.com",
            "JIRA_API_TOKEN": "secret-token",
        },
        capture_output=True,
        text=True,
    )
    server.server_close()

    assert result.returncode == 0, result.stderr
    assert captured["path"] == "/rest/api/3/issue/PROJ-1/comment"
    expected_auth = base64.b64encode(b"bot@example.com:secret-token").decode()
    assert captured["auth"] == f"Basic {expected_auth}"
    text = captured["body"]["body"]["content"][0]["content"][0]["text"]
    assert text == "Agent picked this up. Run: http://x/123"
