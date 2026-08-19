"""RhinoAdapter — HTTP client that talks to the Rhino RPC server."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .adapter import AppAdapter
from ._http import HttpClient, HttpStatusError
from .error_reporter import report_error

_BASE_URL = "http://localhost:48885"
_TIMEOUT = 30.0  # seconds
_PREFIX = "/enneadtab"


class RhinoAdapter(AppAdapter):
    """Concrete adapter that forwards MCP calls to a running Rhino instance.

    Communication happens over HTTP via a custom RPC server running inside
    Rhino on port 48885.
    """

    def __init__(self, base_url: str = _BASE_URL, timeout: float = _TIMEOUT) -> None:
        self._client = HttpClient(base_url=base_url, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Issue a GET request and return the response.

        Raises ``ConnectionError`` (after reporting) on transport failures
        and re-raises ``HttpStatusError`` on 4xx / 5xx responses.
        """
        url = "{}{}".format(_PREFIX, path)
        try:
            return self._client.get(url, params=params)
        except ConnectionError as exc:
            report_error(exc, extra={"url": url, "method": "GET"})
            raise ConnectionError(
                "Cannot reach Rhino at {}{}".format(self._client.base_url, url)
            ) from exc
        except HttpStatusError as exc:
            report_error(exc, extra={"url": url, "method": "GET", "status": exc.status_code})
            raise

    def _post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Issue a POST request and return the response."""
        url = "{}{}".format(_PREFIX, path)
        try:
            return self._client.post(url, json_body=data)
        except ConnectionError as exc:
            report_error(exc, extra={"url": url, "method": "POST"})
            raise ConnectionError(
                "Cannot reach Rhino at {}{}".format(self._client.base_url, url)
            ) from exc
        except HttpStatusError as exc:
            report_error(exc, extra={"url": url, "method": "POST", "status": exc.status_code})
            raise

    # ------------------------------------------------------------------
    # AppAdapter — application state
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        return self._get("/status/").json()

    def get_model_info(self) -> dict:
        return self._get("/model-info/").json()

    # ------------------------------------------------------------------
    # AppAdapter — element queries
    # ------------------------------------------------------------------

    def list_elements(self, category: str, filters: Optional[Dict] = None) -> List[dict]:
        params: Dict[str, Any] = {"category": category}
        if filters:
            params.update(filters)
        return self._get("/elements/", params=params).json()

    def get_element_parameters(self, element_id: str) -> dict:
        return self._get("/element/{}/parameters/".format(element_id)).json()

    def set_element_parameter(self, element_id: str, param_name: str, value: str) -> dict:
        return self._post(
            "/element/{}/set-parameter/".format(element_id),
            data={"param_name": param_name, "value": value},
        ).json()

    # ------------------------------------------------------------------
    # AppAdapter — code execution
    # ------------------------------------------------------------------

    def execute_code(self, code: str) -> dict:
        return self._post("/execute-code/", data={"code": code}).json()

    # ------------------------------------------------------------------
    # AppAdapter — visualization
    # ------------------------------------------------------------------

    def get_view_image(self, view_name: Optional[str] = None) -> bytes:
        params = {"view_name": view_name} if view_name else None
        return self._get("/view-image/", params=params).content

    # ------------------------------------------------------------------
    # AppAdapter — EnneadTab tools
    # ------------------------------------------------------------------

    def list_enneadtab_tools(self) -> List[dict]:
        return self._get("/tools/").json()

    def run_enneadtab_tool(
        self, module: str, function: str, args: Optional[Dict] = None
    ) -> dict:
        payload: Dict[str, Any] = {"module": module, "function": function}
        if args:
            payload["args"] = args
        return self._post("/run-tool/", data=payload).json()

    # ------------------------------------------------------------------
    # Rhino-specific methods (not in base adapter)
    # ------------------------------------------------------------------

    def list_layers(self) -> List[dict]:
        """Return all layers in the active Rhino document."""
        return self._get("/layers/").json()

    def list_views(self) -> List[dict]:
        """Return all named views in the active Rhino document."""
        return self._get("/views/").json()

    def list_blocks(self, category: Optional[str] = None) -> List[dict]:
        """Return block definitions, optionally filtered by *category*."""
        params = {"category": category} if category else None
        return self._get("/blocks/", params=params).json()

    def set_layer_state(
        self,
        layer_name: str,
        visible: Optional[bool] = None,
        locked: Optional[bool] = None,
        color: Optional[str] = None,
    ) -> dict:
        """Set layer visibility, lock state, or color."""
        payload: Dict[str, Any] = {"layer_name": layer_name}
        if visible is not None:
            payload["visible"] = visible
        if locked is not None:
            payload["locked"] = locked
        if color is not None:
            payload["color"] = color
        return self._post("/set-layer-state/", data=payload).json()

    def export_geometry(self, format: str, filepath: str) -> dict:
        """Export selected geometry to a file."""
        return self._post(
            "/export-geometry/",
            data={"format": format, "filepath": filepath},
        ).json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
