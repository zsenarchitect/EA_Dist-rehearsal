"""HTTP server for the MCP chat web UI.

Serves the chat page and proxies LLM API calls with tool execution.
Uses stdlib only (http.server + urllib).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional

from . import llm_client
from .web_ui import get_index_html

# EnneadTabHome endpoint for centralized API keys
_KEYS_URL = "https://enneadtab.com/api/keys/llm"


class CentralKeyFetchError(Exception):
    """Raised when the EnneadTabHome central key endpoint cannot be reached or parsed.

    Deliberately NOT caught-and-ignored by callers into a silent local-env-var
    fallback -- see todo #2320 Phase 0.
    """


def _kill_pid(pid: int) -> bool:
    """Terminate a process by PID. Returns True if killed successfully."""
    try:
        subprocess.call(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _kill_zombies(port: int) -> None:
    """Kill any existing processes listening on *port*.

    Uses a PID file as the primary mechanism. Falls back to netstat
    scanning if the PID file is stale or missing. Fully automatic —
    end users never need to intervene.
    """
    my_pid = os.getpid()
    pid_file = os.path.join(
        os.environ.get("TEMP", os.environ.get("USERPROFILE", "")),
        "mcp_web_{}.pid".format(port),
    )
    killed = []

    # 1) PID file — fast path
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != my_pid and _kill_pid(old_pid):
                killed.append(old_pid)
        except (ValueError, OSError):
            pass  # stale file or process already gone

    # 2) Fallback — scan netstat for anything else on this port
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], stderr=subprocess.DEVNULL, text=True,
        )
        for line in out.splitlines():
            if "LISTENING" not in line:
                continue
            # Match exact port (e.g., ":5000 " not ":50001")
            if ":{} ".format(port) not in line and ":{}".format(port) not in line.split()[1]:
                continue
            parts = line.split()
            try:
                pid = int(parts[-1])
            except (ValueError, IndexError):
                continue
            if pid == my_pid or pid in killed or pid == 0:
                continue
            if _kill_pid(pid):
                killed.append(pid)
    except Exception:
        pass

    if killed:
        print("[web] Cleaned up {} old server(s): PID {}".format(
            len(killed), ", ".join(str(p) for p in killed)), file=sys.stderr)
        import time
        time.sleep(0.5)

    # Write our PID for next startup to find
    try:
        with open(pid_file, "w") as f:
            f.write(str(my_pid))
    except OSError:
        pass


def _fetch_central_keys() -> Dict[str, Dict[str, str]]:
    """Fetch LLM API keys from EnneadTabHome.

    Uses DEBUG_BYPASS_SECRET for auth (set on the Vercel project). If
    DEBUG_BYPASS_SECRET is unset, central auth is simply not configured and
    this returns an empty dict (not an error). If it IS set but the fetch
    fails or the response can't be parsed, this fails CLOSED: it raises
    CentralKeyFetchError rather than silently resurrecting local
    ANTHROPIC_API_KEY/GOOGLE_API_KEY/GEMINI_API_KEY env vars, which was
    itself a raw-key leak path (todo #2320 Phase 0).
    """
    bypass = os.environ.get("DEBUG_BYPASS_SECRET", "")
    if not bypass:
        return {}

    try:
        req = urllib.request.Request(_KEYS_URL, method="GET")
        req.add_header("x-debug-bypass", bypass)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("providers", {})
    except urllib.error.HTTPError as e:
        print(
            "ERROR: central key fetch failed: GET {} -> HTTP {} ({})".format(
                _KEYS_URL, e.code, type(e).__name__),
            file=sys.stderr,
        )
        raise CentralKeyFetchError("HTTP {} from {}".format(e.code, _KEYS_URL)) from e
    except Exception as e:
        print(
            "ERROR: central key fetch failed: GET {} -> {}: {}".format(
                _KEYS_URL, type(e).__name__, e),
            file=sys.stderr,
        )
        raise CentralKeyFetchError("{}: {}".format(type(e).__name__, e)) from e


def _execute_tool(tools: Dict[str, Any], name: str, arguments: Dict) -> Any:
    """Execute a registered MCP tool by name."""
    entry = tools.get(name)
    if not entry:
        raise ValueError("Unknown tool: {}".format(name))
    return entry.handler(**arguments)


def _get_tool_list(tools: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get MCP tool definitions for the LLM API."""
    result = []
    for name, entry in tools.items():
        result.append({
            "name": name,
            "description": entry.description,
            "inputSchema": entry.parameters,
        })
    return result


def make_handler(
    tools: Dict[str, Any],
    providers: Dict[str, Dict[str, str]],
    port: int,
    central_key_error: Optional[str] = None,
):
    """Create a request handler class with tool and provider context.

    central_key_error, when set, means the central key fetch failed (as
    opposed to central auth simply being unconfigured) -- chat requests
    surface a clean, specific message instead of the generic "no key" one.
    """

    allowed_origins = {
        "http://127.0.0.1:{}".format(port),
        "http://localhost:{}".format(port),
    }

    class ChatHandler(BaseHTTPRequestHandler):

        def _same_origin(self):
            """True if this request can be attributed to OUR OWN served page.

            2026-09-18 SECURITY (senzhang-todo, EnneadTab-OS audit): /api/chat lets
            the LLM invoke the execute_code tool, so any page that can POST here
            can run arbitrary code inside the connected Revit/Rhino process. The
            legitimate caller is this server's OWN chat page running in the user's
            browser -- so unlike a pure local-tool socket, we cannot reject every
            browser-shaped request (that would break the real UI). Instead we
            check that Origin/Referer, WHEN PRESENT, actually names this server.
            A same-origin fetch() always carries a matching Origin on POST; a
            cross-origin page (the attack this closes) carries its own origin.
            Neither header present means a non-browser local caller (curl, a
            script) -- unauthenticated by design already, unchanged by this check.
            """
            origin = self.headers.get("Origin")
            if origin is not None:
                return origin in allowed_origins
            referer = self.headers.get("Referer")
            if referer is not None:
                return any(
                    referer == o or referer.startswith(o + "/")
                    for o in allowed_origins
                )
            return True

        def _refuse_cross_origin(self):
            body = json.dumps({
                "error": "Refused: cross-origin requests are not accepted by "
                         "this local server.",
            }).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # No CORS headers on the refusal -- the attacker's page must not be
            # able to read even this error via a CORS-mode fetch.
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._safe_dispatch(self._do_GET)

        def do_POST(self):
            self._safe_dispatch(self._do_POST)

        def _safe_dispatch(self, route_fn):
            """Run a route handler, converting any unhandled exception into a
            JSON 500 (plus a full stderr traceback) instead of a silently
            dropped socket.

            Without this, an exception raised before a response is written
            propagates out of the handler, the single-threaded HTTPServer
            closes the connection with zero bytes, and the browser reports
            only ``net::ERR_EMPTY_RESPONSE`` with no clue as to the cause.
            """
            try:
                route_fn()
            except Exception:
                import traceback
                tb = traceback.format_exc()
                print("[web] Unhandled handler error on {}:\n{}".format(
                    self.path, tb), file=sys.stderr)
                try:
                    detail = tb.strip().splitlines()[-1][:500] if tb.strip() else ""
                    body = json.dumps({
                        "error": "Internal server error",
                        "detail": detail,
                    }).encode()
                    self._json_response(500, body)
                except Exception:
                    # A response was already partially sent, so we can't emit
                    # clean 500 headers. The stderr traceback above is the
                    # durable record either way.
                    pass

        def _do_GET(self):
            # Parse path and query string
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/":
                html = get_index_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(html)

            elif path == "/api/health":
                # Report which providers are available (without exposing keys)
                available = {}
                for k, v in providers.items():
                    available[k] = {"model": v.get("model", "")}
                has_keys = len(available) > 0
                body = json.dumps({
                    "status": "ok",
                    "providers": available,
                    "has_keys": has_keys,
                    "auth_url": "https://enneadtab.com/api/keys/llm-auth?port={}".format(port),
                }).encode()
                self._json_response(200, body)

            elif path == "/api/tools":
                tool_list = [{"name": n, "description": e.description}
                             for n, e in tools.items()]
                body = json.dumps({"tools": tool_list}).encode()
                self._json_response(200, body)

            elif path == "/api/auth/callback":
                # Handle redirect callback from EnneadTabHome with API keys
                #
                # 2026-09-18 SECURITY (known gap, not fixed here): this endpoint
                # trusts any GET carrying a well-formed base64(json) token, with
                # no signature and no state/nonce binding it to a callback WE
                # initiated. A page that merely navigates the browser here
                # (window.location = '.../api/auth/callback?token=<forged>') can
                # inject its own provider keys and silently capture future chat
                # traffic sent through that provider. _same_origin() does not
                # help: this is a legitimate CROSS-origin top-level navigation
                # BY DESIGN (the redirect comes from enneadtab.com), so an
                # Origin/Referer check cannot distinguish the real callback from
                # a forged one -- it would either accept both or break the real
                # login flow depending on what enneadtab.com's redirect actually
                # sends, which this repo cannot verify without inspecting the
                # EnneadTab-Home server that constructs it. A real fix needs a
                # state/nonce generated here and echoed back by enneadtab.com
                # (or an HMAC-signed token), coordinated with that repo -- do not
                # add a local-only check without confirming the round trip.
                token = query.get("token", [""])[0]
                if not token:
                    self.send_error(400, "Missing token")
                    return
                try:
                    import base64
                    payload = json.loads(base64.urlsafe_b64decode(token + "=="))
                    new_providers = payload.get("providers", {})
                    # Merge into the shared providers dict
                    providers.update(new_providers)
                    user_email = payload.get("user", "unknown")
                    print("[web] Auth callback: {} ({} providers)".format(
                        user_email, len(new_providers)), file=sys.stderr)
                    # Redirect to chat page
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.end_headers()
                except Exception as e:
                    self.send_error(400, "Invalid token: {}".format(e))

            else:
                self.send_error(404)

        def _do_POST(self):
            if self.path == "/api/chat":
                if not self._same_origin():
                    self._refuse_cross_origin()
                    return
                self._handle_chat()
            else:
                self.send_error(404)

        def do_OPTIONS(self):
            # Only emit CORS headers for a preflight that actually names our own
            # origin -- otherwise the browser's preflight fails closed and the
            # real cross-origin POST to /api/chat is never sent.
            if not self._same_origin():
                self.send_response(403)
                self.end_headers()
                return
            self.send_response(200)
            self._cors_headers()
            self.end_headers()

        def _handle_chat(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                self._json_response(400, json.dumps({"error": "Bad request: {}".format(e)}).encode())
                return

            messages = data.get("messages", [])
            provider = data.get("provider", "")
            manual_key = data.get("manual_key", "")

            if not provider or not messages:
                self._json_response(400, json.dumps({"error": "Missing provider or messages"}).encode())
                return

            # Resolve API key: central > manual > none
            prov_info = providers.get(provider, {})
            # Resolve model: central /api/keys/llm payload > GEMINI_MODEL env
            # (todo #1452). None = llm_client built-in default.
            model = prov_info.get("model", "") or os.environ.get("GEMINI_MODEL", "") or None
            api_key = prov_info.get("key", "")
            if not api_key and manual_key:
                api_key = manual_key

            if not api_key:
                if central_key_error:
                    msg = "Could not reach EnneadTab's central key service -- AI chat is unavailable right now."
                else:
                    msg = "No API key for {}".format(provider)
                self._json_response(400, json.dumps({"error": msg}).encode())
                return

            mcp_tools = _get_tool_list(tools)

            execute = lambda name, args: _execute_tool(tools, name, args)

            # Try primary provider, auto-fallback to the other on failure
            fallback_provider = "gemini" if provider == "anthropic" else "anthropic"
            fallback_info = providers.get(fallback_provider, {})
            fallback_model = (fallback_info.get("model", "")
                              or os.environ.get("GEMINI_MODEL", "") or None)
            fallback_key = fallback_info.get("key", "")

            try:
                result = llm_client.run_chat(
                    provider=provider,
                    api_key=api_key,
                    messages=messages,
                    mcp_tools=mcp_tools,
                    execute_fn=execute,
                    model=model,
                )
                result["provider_used"] = provider
                body = json.dumps(result).encode()
                self._json_response(200, body)
            except Exception as primary_err:
                # Auto-fallback to other provider
                if fallback_key:
                    try:
                        result = llm_client.run_chat(
                            provider=fallback_provider,
                            api_key=fallback_key,
                            messages=messages,
                            mcp_tools=mcp_tools,
                            execute_fn=execute,
                            model=fallback_model,
                        )
                        result["provider_used"] = fallback_provider
                        result["fallback_reason"] = str(primary_err)[:200]
                        body = json.dumps(result).encode()
                        self._json_response(200, body)
                        return
                    except Exception:
                        pass

                # Both failed — report primary error
                if isinstance(primary_err, urllib.error.HTTPError):
                    error_body = ""
                    try:
                        error_body = primary_err.read().decode("utf-8", errors="replace")
                    except Exception:
                        pass
                    msg = "LLM API error {}: {}".format(primary_err.code, error_body[:500])
                else:
                    msg = str(primary_err)
                self._json_response(502, json.dumps({"error": msg}).encode())

        def _json_response(self, code: int, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _cors_headers(self):
            # Reflect ONLY our own origin, never "*" -- a wildcard lets any
            # website's JS read the response of a CORS-mode fetch (e.g. the
            # /api/health provider list) even where the request itself was
            # otherwise allowed through.
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def log_message(self, format, *args):
            print("[web] " + (format % args), file=sys.stderr)

    return ChatHandler


def start_web_server(
    mcp_tools: Dict[str, Any],
    host: str = "127.0.0.1",
    port: int = 5000,
    open_browser: bool = True,
) -> None:
    """Start the web chat server.

    Args:
        mcp_tools: Tool registry dict from McpServer._tools
        host: Bind address
        port: Port number
        open_browser: Auto-open browser on start
    """
    # Kill any zombie servers on the target port before binding
    _kill_zombies(port)

    print("Fetching API keys...", file=sys.stderr)
    central_key_error: Optional[str] = None
    try:
        providers = _fetch_central_keys()
    except CentralKeyFetchError as e:
        providers = {}
        central_key_error = str(e)
        print(
            "WARNING: central key service unavailable ({}). Continuing without "
            "central keys -- users must supply a manual API key.".format(e),
            file=sys.stderr,
        )

    if providers:
        print("Available providers: {}".format(", ".join(providers.keys())), file=sys.stderr)
    elif not central_key_error:
        print("WARNING: No API keys found. Users must provide keys manually.", file=sys.stderr)

    handler_class = make_handler(mcp_tools, providers, port, central_key_error)

    try:
        httpd = HTTPServer((host, port), handler_class)
    except OSError as e:
        print("ERROR: Could not bind to port {}: {}".format(port, e), file=sys.stderr)
        sys.exit(1)

    actual_port = port
    url = "http://{}:{}".format(host, actual_port)
    print("Web UI: {}".format(url), file=sys.stderr)

    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=[url]).start()

    pid_file = os.path.join(
        os.environ.get("TEMP", os.environ.get("USERPROFILE", "")),
        "mcp_web_{}.pid".format(port),
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server.", file=sys.stderr)
        httpd.shutdown()
    finally:
        # Clean up PID file so next startup doesn't chase a dead PID
        try:
            os.remove(pid_file)
        except OSError:
            pass
