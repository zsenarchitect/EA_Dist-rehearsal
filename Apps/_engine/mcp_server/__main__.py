"""EnneadTab MCP Server entry point.

Usage:
    python -m mcp_server --app revit                  # stdio MCP mode
    python -m mcp_server --app revit --web             # web chat UI
    python -m mcp_server --app revit --web --web-port 5000
    python -m mcp_server                               # auto-detect
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
import urllib.error

from .error_reporter import report_error
from .revit_adapter import RevitAdapter
from .rhino_adapter import RhinoAdapter
from .server import McpServer
from .tools.common import register_common_tools
from .tools.revit_tools import register_revit_tools
from .tools.rhino_tools import register_rhino_tools


RHINO_PORT_START = 48900
RHINO_PORT_SPAN = 16


def detect_rhino_port(explicit_port: int = 0) -> int:
    """Find the live Rhino RPC server's port.

    rhino_rpc_server.py (running inside Rhino) does not bind a fixed port --
    it binds the first free port in [RHINO_PORT_START, RHINO_PORT_START +
    RHINO_PORT_SPAN), moved there specifically to stop colliding with
    pyRevit Routes on a second Revit instance. Scan that window the same
    way detect_app() below scans Revit's Routes window. Returns 0 if no
    server responds anywhere in the window.
    """
    if explicit_port:
        return explicit_port

    for p in range(RHINO_PORT_START, RHINO_PORT_START + RHINO_PORT_SPAN):
        try:
            url = "http://localhost:{}/enneadtab/status/".format(p)
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return p
        except Exception:
            pass
    return 0


def detect_app(port: int = 0) -> tuple:
    """Probe localhost ports to detect which app is running.

    Returns (app_name, port) tuple.
    pyRevit Routes assigns ports dynamically starting at 48884.
    """
    # If a specific port was given, probe it directly
    if port:
        try:
            url = "http://localhost:{}/enneadtab/status/".format(port)
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return ("revit", port)
        except Exception:
            pass

    # Scan a range of ports (pyRevit increments from 48884 per Revit instance)
    for p in range(48884, 48894):
        try:
            url = "http://localhost:{}/enneadtab/status/".format(p)
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return ("revit", p)
        except Exception:
            pass

    print("ERROR: No supported app detected.", file=sys.stderr)
    print("Is Revit running with pyRevit Routes enabled? (checked ports 48884-48893)", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="EnneadTab MCP Server")
    parser.add_argument("--app", choices=["revit", "rhino"], default=None,
                        help="Target application (default: auto-detect)")
    parser.add_argument("--port", type=int, default=0,
                        help="pyRevit Routes port (default: auto-detect)")
    parser.add_argument("--web", action="store_true",
                        help="Start web chat UI instead of stdio MCP server")
    parser.add_argument("--web-port", type=int, default=5000,
                        help="Port for web UI (default: 5000)")
    args = parser.parse_args()

    if args.app:
        app = args.app
        port = args.port or 48884
    else:
        app, port = detect_app(args.port)

    mcp = McpServer(
        "EnneadTab",
        description="EnneadTab MCP Server — control Revit or Rhino from Claude Code. "
                    "Query models, modify parameters, execute code, and run EnneadTab tools.",
    )

    if app == "revit":
        base_url = "http://localhost:{}".format(port)
        try:
            adapter = RevitAdapter(base_url=base_url)
            adapter.get_status()  # verify connection
        except Exception as e:
            msg = "Failed to connect to Revit on port {}: {}".format(port, e)
            report_error(msg, extra={"adapter": "revit", "port": port})
            print("ERROR: {}".format(msg), file=sys.stderr)
            sys.exit(1)

        register_common_tools(mcp, adapter)
        register_revit_tools(mcp, adapter)
        print("EnneadTab MCP Server started (app=revit, port={})".format(port), file=sys.stderr)
    elif app == "rhino":
        rhino_port = detect_rhino_port(args.port)
        if not rhino_port:
            msg = "No running Rhino RPC server found on ports {}-{}".format(
                RHINO_PORT_START, RHINO_PORT_START + RHINO_PORT_SPAN - 1
            )
            report_error(msg, extra={"adapter": "rhino"})
            print("ERROR: {}".format(msg), file=sys.stderr)
            sys.exit(1)

        try:
            adapter = RhinoAdapter(base_url="http://localhost:{}".format(rhino_port))
            adapter.get_status()
        except Exception as e:
            msg = "Failed to connect to Rhino on port {}: {}".format(rhino_port, e)
            report_error(msg, extra={"adapter": "rhino", "port": rhino_port})
            print("ERROR: {}".format(msg), file=sys.stderr)
            sys.exit(1)

        register_common_tools(mcp, adapter)
        register_rhino_tools(mcp, adapter)
        print("EnneadTab MCP Server started (app=rhino, port={})".format(rhino_port), file=sys.stderr)
    else:
        print("ERROR: Unknown app: {}".format(app), file=sys.stderr)
        sys.exit(1)

    if args.web:
        from .web_server import start_web_server
        start_web_server(
            mcp_tools=mcp._tools,
            host="127.0.0.1",
            port=args.web_port,
            open_browser=False,  # pushbutton opens browser instead
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
