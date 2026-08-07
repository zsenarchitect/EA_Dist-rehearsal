"""EnneadTab AI Assistant -- local web server.

Serves the chat UI and bridges between enneadtab.com AI proxy and local Revit
instance (pyRevit Routes on localhost:48884).

Usage::

    python -m ai_assistant [--port 3000]
"""

import http.server
import json
import os
import pathlib
import urllib.request
import urllib.error

ENNEADTAB_API = os.environ.get("ENNEADTAB_API", "https://enneadtab.com")
REVIT_API = os.environ.get("REVIT_API", "http://localhost:48884")
API_TOKEN = os.environ.get("ENNEADTAB_API_TOKEN", "")

STATIC_DIR = pathlib.Path(__file__).parent


class AIAssistantHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for the AI assistant webapp."""

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_file("index.html", "text/html")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/chat":
            self._handle_chat()
        elif self.path == "/api/revit/status":
            self._proxy_revit("GET", "/enneadtab/status/")
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------

    def _serve_file(self, filename, content_type):
        filepath = STATIC_DIR / filename
        if not filepath.is_file():
            self.send_error(404)
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------
    # POST /api/chat  --  bridge to enneadtab.com and handle tool calls
    # ------------------------------------------------------------------

    def _handle_chat(self):
        body = self._read_json_body()
        if body is None:
            return
        messages = body.get("messages", [])

        # Start SSE response to the browser immediately
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self._cors_headers()
        self.end_headers()

        try:
            self._chat_loop(messages)
        except Exception as exc:
            self._sse_send("error", {"message": str(exc)})

        # Signal completion
        self._sse_send("done", {})

    def _chat_loop(self, messages, max_rounds=10):
        """Call the AI proxy, relay text chunks, execute tool calls, repeat."""
        for _ in range(max_rounds):
            tool_calls = self._stream_ai_response(messages)
            if not tool_calls:
                # No tool calls -- conversation turn is complete
                return

            # Execute each tool call against Revit
            tool_results = []
            for tc in tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = tc.get("args", {})
                tool_id = tc.get("id", tool_name)

                self._sse_send("tool_start", {
                    "id": tool_id,
                    "name": tool_name,
                    "args": tool_args,
                })

                result = self._execute_revit_tool(tool_name, tool_args)

                self._sse_send("tool_result", {
                    "id": tool_id,
                    "name": tool_name,
                    "result": result,
                })

                tool_results.append({
                    "id": tool_id,
                    "name": tool_name,
                    "result": result,
                })

            # Append tool results to conversation and loop
            messages.append({
                "role": "assistant",
                "tool_calls": tool_calls,
            })
            messages.append({
                "role": "tool",
                "tool_results": tool_results,
            })

    def _stream_ai_response(self, messages):
        """POST messages to enneadtab.com/api/ai/chat and relay SSE events.

        Returns a list of tool_call dicts (empty if none).
        """
        payload = json.dumps({"messages": messages}).encode("utf-8")
        req = urllib.request.Request(
            ENNEADTAB_API + "/api/ai/chat",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "x-debug-bypass": API_TOKEN,
            },
        )

        tool_calls = []

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                buffer = ""
                while True:
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")

                    # Process complete SSE events (delimited by double newline)
                    while "\n\n" in buffer:
                        raw_event, buffer = buffer.split("\n\n", 1)
                        event_type, event_data = self._parse_sse(raw_event)

                        if event_type == "tool_call":
                            tool_calls.append(event_data)
                        elif event_type == "text":
                            # Relay text delta to the browser
                            self._sse_send("text", event_data)
                        elif event_type == "done":
                            pass
                        elif event_type == "error":
                            self._sse_send("error", event_data)
                        else:
                            # Relay unknown events as-is
                            self._sse_send(event_type, event_data)

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            self._sse_send("error", {
                "message": "AI proxy returned HTTP {}".format(exc.code),
                "detail": error_body[:500],
            })
        except urllib.error.URLError as exc:
            self._sse_send("error", {
                "message": "Cannot reach AI proxy: {}".format(exc.reason),
            })

        return tool_calls

    # ------------------------------------------------------------------
    # Revit tool execution via pyRevit Routes
    # ------------------------------------------------------------------

    def _execute_revit_tool(self, tool_name, tool_args):
        """Call localhost:48884/enneadtab/{tool_name}/ with args as JSON body."""
        url = "{}/enneadtab/{}/".format(REVIT_API, tool_name)
        data = json.dumps(tool_args).encode("utf-8") if tool_args else None
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result
        except urllib.error.HTTPError as exc:
            return {"error": "Revit returned HTTP {}".format(exc.code)}
        except urllib.error.URLError as exc:
            return {"error": "Cannot reach Revit: {}".format(exc.reason)}
        except json.JSONDecodeError:
            return {"error": "Revit returned non-JSON response"}
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # POST /api/revit/status  --  proxy to pyRevit Routes
    # ------------------------------------------------------------------

    def _proxy_revit(self, method, path):
        url = REVIT_API + path
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(data)
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self.send_error(400, "Empty request body")
            return None
        try:
            return json.loads(self.rfile.read(content_length))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return None

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _sse_send(self, event_type, data):
        """Write a single SSE event to the client."""
        payload = json.dumps(data) if isinstance(data, dict) else str(data)
        line = "event: {}\ndata: {}\n\n".format(event_type, payload)
        try:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _parse_sse(raw):
        """Parse a raw SSE event string into (event_type, data_dict)."""
        event_type = "message"
        data_lines = []
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())

        data_str = "\n".join(data_lines)
        try:
            data = json.loads(data_str)
        except (json.JSONDecodeError, ValueError):
            data = {"text": data_str}
        return event_type, data

    def log_message(self, format, *args):
        """Quieter logging -- single line per request."""
        print("[AI Assistant] {} - {}".format(
            self.address_string(),
            format % args,
        ))


def run_server(port=3000):
    """Start the HTTP server on the given port."""
    server = http.server.HTTPServer(("127.0.0.1", port), AIAssistantHandler)
    print("EnneadTab AI Assistant running at http://localhost:{}".format(port))
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
