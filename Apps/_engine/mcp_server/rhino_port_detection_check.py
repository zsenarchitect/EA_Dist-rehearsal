"""Regression check for TODO-6584: the MCP server must find Rhino's real,
dynamically-bound port (48900-48915) instead of a hardcoded, unreachable one.

Named without a test_*.py / *_test.* pattern on purpose -- this repo's
.gitignore excludes those globally (they're treated as scratch scripts, see
CLAUDE.md's DEBUG/ folder convention). This file is a committed regression
guard, not scratch, so it needs a name outside that pattern to actually land
in git.

Stdlib-only. Run from Apps/_engine (mcp_server's package parent) so the
package-relative imports in __main__.py resolve:

    cd Apps/_engine && python3 -m mcp_server.rhino_port_detection_check
"""

from __future__ import annotations

import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from mcp_server.__main__ import detect_rhino_port, RHINO_PORT_START, RHINO_PORT_SPAN


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/enneadtab/status/":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # keep test output quiet


def _find_free_port_in_window() -> int:
    for port in range(RHINO_PORT_START, RHINO_PORT_START + RHINO_PORT_SPAN):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("localhost", port))
            s.close()
            return port
        except OSError:
            s.close()
            continue
    raise RuntimeError("No free port in the Rhino window for this test")


class RhinoPortDetectionTests(unittest.TestCase):
    def test_no_server_running_returns_zero(self):
        # Nothing is bound in the window (assuming a clean CI/dev box) -- detection
        # must fail loud (0), never fall back to a stale, always-wrong port.
        self.assertEqual(detect_rhino_port(explicit_port=0), 0)

    def test_explicit_port_bypasses_scan(self):
        # An explicit --port always wins, exactly like the Revit branch already does.
        self.assertEqual(detect_rhino_port(explicit_port=12345), 12345)

    def test_finds_real_dynamically_bound_port(self):
        port = _find_free_port_in_window()
        server = HTTPServer(("localhost", port), _StatusHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            found = detect_rhino_port(explicit_port=0)
            self.assertEqual(
                found, port,
                "detect_rhino_port() must find the port rhino_rpc_server.py "
                "actually bound, not a hardcoded default outside its window",
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


if __name__ == "__main__":
    sys.exit(unittest.main())
