"""Shared utilities for InfraWatch collectors.

All collectors are stdlib-only — no pip dependencies required.
Runs on any machine with Python 3.x.
"""

import json
import os
import socket
import sys
import urllib.request
import urllib.error

INFRAWATCH_BASE = "https://infrawatch-ennead-projects.vercel.app/infra/api/ingest"
# 2026-04-08: skipTrailingSlashRedirect fixed on ErrorDump, but keep
# trailing slash for backwards compat with older deployments
ERRORDUMP_URL = "https://error-dump-ennead-projects.vercel.app/error-dump/api/ingest/"

# Local failure counter — survives within a single collect_all run.
# If ErrorDump itself is down, at least stderr shows something.
_error_dump_failures = 0


def post_to_infrawatch_detailed(endpoint, payload):
    """POST JSON to an InfraWatch ingest endpoint.

    Returns (ok, detail) where ok is True only on HTTP 200. ``detail`` is a
    short, classified string describing the outcome so callers can report
    WHY a POST failed instead of an opaque "POST failed". Failure classes:

      - payload-serialize : JSON serialization of the payload failed (client bug)
      - http <code>       : endpoint responded with a non-2xx status (+truncated body)
      - timeout           : no response within the socket timeout window
      - network           : DNS / connection / TLS failure (URLError.reason)
      - unexpected        : anything else (type + message)

    Response bodies are truncated to keep the reported error small enough for
    ErrorDump (5000-char cap on error_message).
    """
    url = "{}/{}".format(INFRAWATCH_BASE, endpoint)
    try:
        data = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError) as e:
        return False, "payload-serialize: {}: {}".format(type(e).__name__, e)

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Collector-Protocol": "2026-05-07",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return True, "ok"
            body = _read_body_snippet(resp)
            return False, "http {}: {}".format(resp.status, body)
    except urllib.error.HTTPError as e:
        # Non-2xx: the response body usually carries the real reason
        # (validation error, auth failure, etc.) — surface it.
        body = _read_body_snippet(e)
        return False, "http {} {}: {}".format(e.code, e.reason, body)
    except socket.timeout:
        return False, "timeout: no response within 15s"
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, socket.timeout):
            return False, "timeout: no response within 15s"
        return False, "network: {}".format(reason)
    except Exception as e:
        return False, "unexpected: {}: {}".format(type(e).__name__, e)


def _read_body_snippet(resp, limit=500):
    """Best-effort read of a (truncated) response body for diagnostics."""
    try:
        raw = resp.read(limit)
        if not raw:
            return "<empty body>"
        return raw.decode("utf-8", "replace").strip()
    except Exception:
        return "<body unavailable>"


def post_to_infrawatch(endpoint, payload):
    """POST JSON to an InfraWatch ingest endpoint. Returns True on success.

    Backward-compatible bool wrapper around ``post_to_infrawatch_detailed``.
    Logs the classified failure detail to stderr for scheduled-task logs.
    """
    ok, detail = post_to_infrawatch_detailed(endpoint, payload)
    if not ok:
        print("[infrawatch] POST to {} failed: {}".format(endpoint, detail),
              file=sys.stderr)
    return ok


def report_error(func_name, error_msg):
    """Report failure to ErrorDump. Never raises, but logs to stderr on failure."""
    global _error_dump_failures
    try:
        data = json.dumps({
            "source_app": "EnneadTab-OS",
            "environment": "terminal",
            "error_message": str(error_msg)[:5000],
            "function_name": func_name,
            "user_name": os.environ.get("USERNAME", "Unknown"),
            "machine_name": socket.gethostname(),
            "context": {"is_silent": True, "collector": "infrawatch"},
        }).encode("utf-8")
        req = urllib.request.Request(
            ERRORDUMP_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        _error_dump_failures = 0  # reset on success
    except Exception as e:
        _error_dump_failures += 1
        # 2026-04-08: bare except:pass hid months of ErrorDump failures.
        # Log to stderr so at least scheduled-task logs capture it.
        print("[infrawatch] ErrorDump report failed ({}x): {}".format(
            _error_dump_failures, e), file=sys.stderr)


def get_machine_name():
    return socket.gethostname()


def get_username():
    return os.environ.get("USERNAME", "Unknown")
