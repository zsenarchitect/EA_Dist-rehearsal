"""Minimal HTTP helpers using only urllib (stdlib).

Python 3.9 compatible. Replaces httpx usage throughout the MCP server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class HttpResponse:
    """Thin wrapper around the raw bytes returned by urllib."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self.content = body

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class HttpClient:
    """Simple HTTP client scoped to a base URL.

    Drop-in replacement for the subset of ``httpx.Client`` used by
    the adapter classes.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> HttpResponse:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        return self._do(req)

    def post(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> HttpResponse:
        url = self.base_url + path
        data = json.dumps(json_body).encode("utf-8") if json_body else None
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        return self._do(req)

    def _do(self, req: urllib.request.Request) -> HttpResponse:
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return HttpResponse(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            raise HttpStatusError(exc.code, exc.read()) from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(
                "Cannot reach {}:  {}".format(req.full_url, exc.reason)
            ) from exc

    def close(self) -> None:
        """No-op — urllib has no persistent connection pool to close."""


class HttpStatusError(Exception):
    """Raised on 4xx / 5xx responses (mirrors httpx.HTTPStatusError role)."""

    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__("HTTP {}".format(status_code))
