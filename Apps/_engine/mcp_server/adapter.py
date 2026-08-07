"""Abstract base class for application adapters (Revit, Rhino, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class AppAdapter(ABC):
    """Bridge between the MCP server and a host application.

    Each supported application (Revit, Rhino, CAD) implements a concrete
    subclass that translates these generic calls into app-specific API
    invocations.
    """

    # ------------------------------------------------------------------
    # Application state
    # ------------------------------------------------------------------

    @abstractmethod
    def get_status(self) -> dict:
        """Return current application status (version, document, etc.)."""

    @abstractmethod
    def get_model_info(self) -> dict:
        """Return high-level information about the active model/document."""

    # ------------------------------------------------------------------
    # Element queries
    # ------------------------------------------------------------------

    @abstractmethod
    def list_elements(self, category: str, filters: Optional[Dict] = None) -> List[dict]:
        """List elements of *category*, optionally filtered."""

    @abstractmethod
    def get_element_parameters(self, element_id: str) -> dict:
        """Return all parameters for a single element."""

    @abstractmethod
    def set_element_parameter(self, element_id: str, param_name: str, value: str) -> dict:
        """Set a parameter on an element and return the updated state."""

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    @abstractmethod
    def execute_code(self, code: str) -> dict:
        """Execute arbitrary code in the host and return {stdout, stderr, error}."""

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    @abstractmethod
    def get_view_image(self, view_name: Optional[str] = None) -> bytes:
        """Capture and return a PNG screenshot of *view_name* (or the active view)."""

    # ------------------------------------------------------------------
    # EnneadTab tools
    # ------------------------------------------------------------------

    @abstractmethod
    def list_enneadtab_tools(self) -> List[dict]:
        """List available EnneadTab tool modules and their descriptions."""

    @abstractmethod
    def run_enneadtab_tool(
        self, module: str, function: str, args: Optional[Dict] = None
    ) -> dict:
        """Invoke an EnneadTab tool function and return its result."""
