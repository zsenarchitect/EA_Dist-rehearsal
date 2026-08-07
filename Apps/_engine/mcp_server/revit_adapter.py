"""RevitAdapter — HTTP client that talks to pyRevit Routes inside Revit."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .adapter import AppAdapter
from ._http import HttpClient, HttpStatusError
from .error_reporter import report_error

_BASE_URL = "http://localhost:48884"
_TIMEOUT = 30.0  # seconds
_PREFIX = "/enneadtab"


class RevitAdapter(AppAdapter):
    """Concrete adapter that forwards MCP calls to a running Revit instance.

    Communication happens over HTTP via pyRevit Routes, which exposes a
    lightweight REST API inside the Revit process on port 48884.
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
        """Issue a GET request and return the parsed JSON response.

        Raises ``ConnectionError`` (after reporting) on transport failures
        and re-raises ``HttpStatusError`` on 4xx / 5xx responses.
        """
        url = "{}{}".format(_PREFIX, path)
        try:
            return self._client.get(url, params=params)
        except ConnectionError as exc:
            report_error(exc, extra={"url": url, "method": "GET"})
            raise ConnectionError(
                "Cannot reach Revit at {}{}".format(self._client.base_url, url)
            ) from exc
        except HttpStatusError as exc:
            report_error(exc, extra={"url": url, "method": "GET", "status": exc.status_code})
            raise

    def _post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Issue a POST request and return the parsed JSON response."""
        url = "{}{}".format(_PREFIX, path)
        try:
            return self._client.post(url, json_body=data)
        except ConnectionError as exc:
            report_error(exc, extra={"url": url, "method": "POST"})
            raise ConnectionError(
                "Cannot reach Revit at {}{}".format(self._client.base_url, url)
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
    # Revit-specific methods (not in base adapter)
    # ------------------------------------------------------------------

    def list_levels(self) -> List[dict]:
        """Return all levels in the active Revit model."""
        return self._get("/levels/").json()

    def list_views(self) -> List[dict]:
        """Return all views in the active Revit model."""
        return self._get("/views/").json()

    def list_families(self, category: Optional[str] = None) -> List[dict]:
        """Return loaded families, optionally filtered by *category*."""
        params = {"category": category} if category else None
        return self._get("/families/", params=params).json()

    def create_sheet(
        self,
        sheet_number: str,
        sheet_name: str,
        title_block_name: Optional[str] = None,
    ) -> dict:
        """Create a new sheet in the active document."""
        payload: Dict[str, Any] = {
            "sheet_number": sheet_number,
            "sheet_name": sheet_name,
        }
        if title_block_name:
            payload["title_block_name"] = title_block_name
        return self._post("/create-sheet/", data=payload).json()

    def create_view(
        self,
        view_type: str,
        level_name: Optional[str] = None,
        name: Optional[str] = None,
    ) -> dict:
        """Create a new view of the given *view_type* at *level_name*."""
        payload: Dict[str, Any] = {
            "view_type": view_type,
        }
        if level_name:
            payload["level_name"] = level_name
        if name:
            payload["name"] = name
        return self._post("/create-view/", data=payload).json()

    def place_family(
        self,
        family_name: str,
        type_name: str,
        x: float,
        y: float,
        z: float,
        level_name: Optional[str] = None,
    ) -> dict:
        """Place a family instance at the given coordinates."""
        payload: Dict[str, Any] = {
            "family_name": family_name,
            "type_name": type_name,
            "x": x,
            "y": y,
            "z": z,
        }
        if level_name:
            payload["level_name"] = level_name
        return self._post("/place-family/", data=payload).json()

    def sync_with_central(self) -> dict:
        """Synchronize the local model with central."""
        return self._post("/sync-with-central/").json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
