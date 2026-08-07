"""Fire-and-forget error reporter that POSTs to ErrorHub."""

from __future__ import annotations

import json
import traceback
import urllib.request
from typing import Any, Dict, Optional

_INGEST_URL = "https://error-dump-ennead-projects.vercel.app/error-dump/api/ingest"
_TIMEOUT = 5.0  # seconds


def report_error(
    error: Any,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Send an error report to ErrorHub.

    This is intentionally fire-and-forget: it never raises and silently
    swallows any network or serialisation failures so that the MCP server
    can keep running.

    Parameters
    ----------
    error:
        The exception instance or a plain error message string.
    extra:
        Optional dictionary of additional context merged into the payload.
    """
    try:
        if isinstance(error, BaseException):
            message = str(error)
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            stack = "".join(tb)
        else:
            message = str(error)
            stack = ""

        payload: Dict[str, Any] = {
            "source_app": "EnneadTab-MCP",
            "environment": "mcp-server",
            "error_message": message,
            "traceback": stack,
        }
        if extra:
            payload.update(extra)

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _INGEST_URL,
            data=data,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=_TIMEOUT)
    except Exception:  # noqa: BLE001 — intentionally broad
        pass
