"""Rhino-specific MCP tools — only registered when RhinoAdapter is active."""

from __future__ import annotations

from ..server import McpServer


def register_rhino_tools(mcp: McpServer, adapter) -> None:
    """Register Rhino-only tools on *mcp*.

    The *adapter* must be a ``RhinoAdapter`` (or compatible) instance that
    exposes the Rhino-specific helper methods.
    """

    def list_layers() -> list:
        """List all Rhino layers."""
        return adapter.list_layers()

    mcp.tool(
        name="list_layers",
        description="List all Rhino layers with visibility, color, and lock state.",
        handler=list_layers,
    )

    def set_layer_state(
        layer_name: str = "",
        visible: str = "",
        locked: str = "",
        color: str = "",
    ) -> dict:
        """Set layer visibility, lock state, or color."""
        v = None if not visible else visible.lower() == "true"
        l_val = None if not locked else locked.lower() == "true"
        c = None if not color else color
        return adapter.set_layer_state(layer_name, visible=v, locked=l_val, color=c)

    mcp.tool(
        name="set_layer_state",
        description=(
            "Set layer visibility, lock state, or color.\n\n"
            "Args:\n"
            "  layer_name: Full layer path (e.g. 'Default' or 'Parent::Child').\n"
            "  visible: 'true' or 'false' to change visibility. Leave empty to keep current state.\n"
            "  locked: 'true' or 'false' to change lock state. Leave empty to keep current state.\n"
            "  color: 'R,G,B' string (e.g. '255,0,0') to change layer color. Leave empty to keep current color."
        ),
        handler=set_layer_state,
        parameters={
            "type": "object",
            "properties": {
                "layer_name": {"type": "string", "description": "Full layer path (e.g. 'Default' or 'Parent::Child')."},
                "visible": {"type": "string", "description": "'true' or 'false' to change visibility. Leave empty to keep current state.", "default": ""},
                "locked": {"type": "string", "description": "'true' or 'false' to change lock state. Leave empty to keep current state.", "default": ""},
                "color": {"type": "string", "description": "'R,G,B' string (e.g. '255,0,0') to change layer color. Leave empty to keep current color.", "default": ""},
            },
            "required": ["layer_name"],
        },
    )

    def export_geometry(format: str = "", filepath: str = "") -> dict:
        """Export selected objects to file."""
        return adapter.export_geometry(format, filepath)

    mcp.tool(
        name="export_geometry",
        description=(
            "Export selected objects to file.\n\n"
            "Args:\n"
            "  format: Export format -- '3dm', 'obj', 'stl', 'step', or 'iges'.\n"
            "  filepath: Full path for the exported file."
        ),
        handler=export_geometry,
        parameters={
            "type": "object",
            "properties": {
                "format": {"type": "string", "description": "Export format -- '3dm', 'obj', 'stl', 'step', or 'iges'."},
                "filepath": {"type": "string", "description": "Full path for the exported file."},
            },
            "required": ["format", "filepath"],
        },
    )
