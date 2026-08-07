"""Revit-specific MCP tool definitions."""

from __future__ import annotations

from typing import List

from ..server import McpServer


def register_revit_tools(mcp: McpServer, adapter) -> None:
    """Register Revit-only tools on *mcp*.

    The *adapter* must be a ``RevitAdapter`` (or compatible) instance that
    exposes the Revit-specific helper methods.
    """

    def list_levels() -> List[dict]:
        """List all levels defined in the active Revit model."""
        return adapter.list_levels()

    mcp.tool(
        name="list_levels",
        description="List all levels defined in the active Revit model.",
        handler=list_levels,
    )

    def list_views() -> List[dict]:
        """List all views in the active Revit model."""
        return adapter.list_views()

    mcp.tool(
        name="list_views",
        description="List all views in the active Revit model.",
        handler=list_views,
    )

    def list_families(category: str = "") -> List[dict]:
        """List loaded families, optionally filtered by category."""
        return adapter.list_families(category=category or None)

    mcp.tool(
        name="list_families",
        description=(
            "List loaded families in the active Revit model, optionally filtered by category.\n\n"
            "Args:\n"
            "  category: Revit category name to filter by (e.g. 'Doors'). Leave empty for all families."
        ),
        handler=list_families,
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Revit category name to filter by (e.g. 'Doors'). Leave empty for all families.", "default": ""},
            },
        },
    )

    def create_sheet(sheet_number: str = "", sheet_name: str = "", title_block_name: str = "") -> dict:
        """Create a new sheet in the active Revit document."""
        return adapter.create_sheet(
            sheet_number,
            sheet_name,
            title_block_name=title_block_name or None,
        )

    mcp.tool(
        name="create_sheet",
        description=(
            "Create a new sheet in the active Revit document.\n\n"
            "Args:\n"
            "  sheet_number: The sheet number (e.g. 'A101').\n"
            "  sheet_name: Display name for the sheet.\n"
            "  title_block_name: Name of the title block family to use. Leave empty for the default."
        ),
        handler=create_sheet,
        parameters={
            "type": "object",
            "properties": {
                "sheet_number": {"type": "string", "description": "The sheet number (e.g. 'A101')."},
                "sheet_name": {"type": "string", "description": "Display name for the sheet."},
                "title_block_name": {"type": "string", "description": "Name of the title block family to use. Leave empty for the default.", "default": ""},
            },
            "required": ["sheet_number", "sheet_name"],
        },
    )

    def create_view(view_type: str = "", level_name: str = "", name: str = "") -> dict:
        """Create a new view of the specified type."""
        return adapter.create_view(
            view_type,
            level_name=level_name or None,
            name=name or None,
        )

    mcp.tool(
        name="create_view",
        description=(
            "Create a new view of the specified type in the active Revit document.\n\n"
            "Args:\n"
            "  view_type: Type of view to create (e.g. 'FloorPlan', 'CeilingPlan', 'Section').\n"
            "  level_name: Level to associate the view with. Leave empty if not applicable.\n"
            "  name: Optional custom name for the new view."
        ),
        handler=create_view,
        parameters={
            "type": "object",
            "properties": {
                "view_type": {"type": "string", "description": "Type of view to create (e.g. 'FloorPlan', 'CeilingPlan', 'Section')."},
                "level_name": {"type": "string", "description": "Level to associate the view with. Leave empty if not applicable.", "default": ""},
                "name": {"type": "string", "description": "Optional custom name for the new view.", "default": ""},
            },
            "required": ["view_type"],
        },
    )

    def place_family(
        family_name: str = "",
        type_name: str = "",
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        level_name: str = "",
    ) -> dict:
        """Place a family instance at the given coordinates."""
        return adapter.place_family(
            family_name,
            type_name,
            x,
            y,
            z,
            level_name=level_name or None,
        )

    mcp.tool(
        name="place_family",
        description=(
            "Place a family instance at the given coordinates in the active Revit model.\n\n"
            "Args:\n"
            "  family_name: Name of the loaded family.\n"
            "  type_name: Family type to place.\n"
            "  x: X coordinate in project units.\n"
            "  y: Y coordinate in project units.\n"
            "  z: Z coordinate in project units.\n"
            "  level_name: Level to place the instance on. Leave empty for automatic level detection."
        ),
        handler=place_family,
        parameters={
            "type": "object",
            "properties": {
                "family_name": {"type": "string", "description": "Name of the loaded family."},
                "type_name": {"type": "string", "description": "Family type to place."},
                "x": {"type": "number", "description": "X coordinate in project units."},
                "y": {"type": "number", "description": "Y coordinate in project units."},
                "z": {"type": "number", "description": "Z coordinate in project units."},
                "level_name": {"type": "string", "description": "Level to place the instance on. Leave empty for automatic level detection.", "default": ""},
            },
            "required": ["family_name", "type_name", "x", "y", "z"],
        },
    )

    def sync_with_central() -> dict:
        """Synchronize the local Revit model with central."""
        return adapter.sync_with_central()

    mcp.tool(
        name="sync_with_central",
        description="Synchronize the local Revit model with central. This saves local changes to the central model.",
        handler=sync_with_central,
    )

    # ------------------------------------------------------------------
    # Extended Revit tools — element operations
    # ------------------------------------------------------------------

    def delete_elements(element_ids: str = "") -> dict:
        """Delete elements by their IDs."""
        code = (
            "from Autodesk.Revit import DB\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "ids = {ids}\n"
            "t = DB.Transaction(doc, 'MCP Delete Elements')\n"
            "t.Start()\n"
            "deleted = []\n"
            "for eid in ids:\n"
            "    try:\n"
            "        doc.Delete(DB.ElementId(int(eid)))\n"
            "        deleted.append(eid)\n"
            "    except: pass\n"
            "t.Commit()\n"
            "print(str(len(deleted)) + ' elements deleted')\n"
        ).format(ids=element_ids.split(",") if element_ids else [])
        return adapter.execute_code(code)

    mcp.tool(
        name="delete_elements",
        description="Delete one or more elements from the model by their IDs.\n\nArgs:\n  element_ids: Comma-separated element IDs to delete.",
        handler=delete_elements,
        parameters={"type": "object", "properties": {"element_ids": {"type": "string", "description": "Comma-separated element IDs (e.g. '12345,67890')."}}, "required": ["element_ids"]},
    )

    def get_selected_elements() -> dict:
        """Get the currently selected elements in Revit."""
        code = (
            "import json\n"
            "uidoc = __revit__.ActiveUIDocument\n"
            "sel = uidoc.Selection.GetElementIds()\n"
            "doc = uidoc.Document\n"
            "result = []\n"
            "for eid in sel:\n"
            "    el = doc.GetElement(eid)\n"
            "    result.append({'id': str(eid.IntegerValue), 'category': str(el.Category.Name) if el.Category else 'None', 'name': el.Name if hasattr(el, 'Name') else ''})\n"
            "print(json.dumps(result))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(
        name="get_selected_elements",
        description="Get information about the elements currently selected in the Revit UI.",
        handler=get_selected_elements,
    )

    def count_elements(category: str = "") -> dict:
        """Count elements by category without the 500-element limit."""
        code = (
            "from Autodesk.Revit import DB\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "import json\n"
            "collector = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()\n"
            "cats = {{}}\n"
            "for el in collector:\n"
            "    if el.Category:\n"
            "        name = el.Category.Name\n"
            "        cats[name] = cats.get(name, 0) + 1\n"
            "if '{cat}':\n"
            "    print(json.dumps({{'category': '{cat}', 'count': cats.get('{cat}', 0)}}))\n"
            "else:\n"
            "    sorted_cats = sorted(cats.items(), key=lambda x: -x[1])[:50]\n"
            "    print(json.dumps([{{'category': k, 'count': v}} for k, v in sorted_cats]))\n"
        ).format(cat=category)
        return adapter.execute_code(code)

    mcp.tool(
        name="count_elements",
        description="Count elements by category (no limit). Returns top 50 categories if no category specified.\n\nArgs:\n  category: Category name to count (leave empty for all categories).",
        handler=count_elements,
        parameters={"type": "object", "properties": {"category": {"type": "string", "description": "Category name to count, or empty for all.", "default": ""}}},
    )

    # ------------------------------------------------------------------
    # View & sheet operations
    # ------------------------------------------------------------------

    def list_sheets() -> dict:
        """List all sheets in the model."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "sheets = DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements()\n"
            "result = [{'id': str(s.Id.IntegerValue), 'number': s.SheetNumber, 'name': s.Name} for s in sheets]\n"
            "result.sort(key=lambda x: x['number'])\n"
            "print(json.dumps(result))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(name="list_sheets", description="List all sheets in the active Revit model with their numbers and names.", handler=list_sheets)

    def get_view_filters(view_name: str = "") -> dict:
        """Get filters applied to a view."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "views = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()\n"
            "view = None\n"
            "for v in views:\n"
            "    if v.Name == '{name}':\n"
            "        view = v\n"
            "        break\n"
            "if not view:\n"
            "    print(json.dumps({{'error': 'View not found: {name}'}}))\n"
            "else:\n"
            "    filters = view.GetFilters()\n"
            "    result = []\n"
            "    for fid in filters:\n"
            "        f = doc.GetElement(fid)\n"
            "        vis = view.GetFilterVisibility(fid)\n"
            "        result.append({{'id': str(fid.IntegerValue), 'name': f.Name, 'visible': vis}})\n"
            "    print(json.dumps(result))\n"
        ).format(name=view_name)
        return adapter.execute_code(code)

    mcp.tool(
        name="get_view_filters",
        description="Get all filters applied to a view and their visibility state.\n\nArgs:\n  view_name: Name of the view.",
        handler=get_view_filters,
        parameters={"type": "object", "properties": {"view_name": {"type": "string", "description": "Name of the view."}}, "required": ["view_name"]},
    )

    def set_active_view(view_name: str = "") -> dict:
        """Switch the active view in Revit."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "uidoc = __revit__.ActiveUIDocument\n"
            "views = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()\n"
            "for v in views:\n"
            "    if v.Name == '{name}':\n"
            "        uidoc.ActiveView = v\n"
            "        print(json.dumps({{'success': True, 'view': '{name}'}}))\n"
            "        break\n"
            "else:\n"
            "    print(json.dumps({{'error': 'View not found: {name}'}}))\n"
        ).format(name=view_name)
        return adapter.execute_code(code)

    mcp.tool(
        name="set_active_view",
        description="Switch the active view in the Revit UI.\n\nArgs:\n  view_name: Name of the view to activate.",
        handler=set_active_view,
        parameters={"type": "object", "properties": {"view_name": {"type": "string", "description": "Name of the view."}}, "required": ["view_name"]},
    )

    # ------------------------------------------------------------------
    # Worksets
    # ------------------------------------------------------------------

    def list_worksets() -> dict:
        """List all user worksets in the model."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "if not doc.IsWorkshared:\n"
            "    print(json.dumps({'error': 'Document is not workshared'}))\n"
            "else:\n"
            "    wsets = DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset).ToWorksets()\n"
            "    result = [{'id': str(w.Id.IntegerValue), 'name': w.Name, 'is_open': w.IsOpen, 'owner': w.Owner} for w in wsets]\n"
            "    print(json.dumps(result))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(name="list_worksets", description="List all user worksets in the active workshared model.", handler=list_worksets)

    # ------------------------------------------------------------------
    # Rooms & Spaces
    # ------------------------------------------------------------------

    def list_rooms(level_name: str = "") -> dict:
        """List rooms, optionally filtered by level."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "rooms = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()\n"
            "result = []\n"
            "for r in rooms:\n"
            "    if r.Area > 0:\n"
            "        lvl = r.Level.Name if r.Level else ''\n"
            "        if '{level}' and lvl != '{level}':\n"
            "            continue\n"
            "        result.append({{'id': str(r.Id.IntegerValue), 'name': r.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or '', 'number': r.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() or '', 'level': lvl, 'area_sqft': round(r.Area, 1)}})\n"
            "print(json.dumps(result[:200]))\n"
        ).format(level=level_name)
        return adapter.execute_code(code)

    mcp.tool(
        name="list_rooms",
        description="List all placed rooms with name, number, level, and area.\n\nArgs:\n  level_name: Filter by level name (optional).",
        handler=list_rooms,
        parameters={"type": "object", "properties": {"level_name": {"type": "string", "description": "Level name to filter by (optional).", "default": ""}}},
    )

    # ------------------------------------------------------------------
    # Warnings & model health
    # ------------------------------------------------------------------

    def list_warnings() -> dict:
        """List all active warnings in the model."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "warnings = doc.GetWarnings()\n"
            "result = []\n"
            "for w in warnings[:100]:\n"
            "    eids = [str(e.IntegerValue) for e in w.GetFailingElements()]\n"
            "    result.append({'description': w.GetDescriptionText(), 'element_ids': eids})\n"
            "print(json.dumps({'count': len(warnings), 'warnings': result}))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(name="list_warnings", description="List active warnings in the Revit model (max 100). Shows warning text and affected element IDs.", handler=list_warnings)

    # ------------------------------------------------------------------
    # Parameters bulk operations
    # ------------------------------------------------------------------

    def get_elements_by_parameter(category: str = "", param_name: str = "", param_value: str = "") -> dict:
        """Find elements by parameter value."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "collector = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()\n"
            "result = []\n"
            "for el in collector:\n"
            "    if el.Category and el.Category.Name == '{cat}':\n"
            "        p = el.LookupParameter('{pname}')\n"
            "        if p and p.AsString() == '{pval}':\n"
            "            result.append({{'id': str(el.Id.IntegerValue), 'name': el.Name if hasattr(el, 'Name') else ''}})\n"
            "    if len(result) >= 200:\n"
            "        break\n"
            "print(json.dumps(result))\n"
        ).format(cat=category, pname=param_name, pval=param_value)
        return adapter.execute_code(code)

    mcp.tool(
        name="get_elements_by_parameter",
        description="Find elements matching a specific parameter value.\n\nArgs:\n  category: Element category.\n  param_name: Parameter name to match.\n  param_value: Parameter value to match.",
        handler=get_elements_by_parameter,
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Element category (e.g. 'Walls')."},
                "param_name": {"type": "string", "description": "Parameter name to match."},
                "param_value": {"type": "string", "description": "Parameter value to match."},
            },
            "required": ["category", "param_name", "param_value"],
        },
    )

    def set_parameter_bulk(element_ids: str = "", param_name: str = "", value: str = "") -> dict:
        """Set a parameter on multiple elements at once."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "ids = [{ids}]\n"
            "t = DB.Transaction(doc, 'MCP Bulk Set Parameter')\n"
            "t.Start()\n"
            "count = 0\n"
            "for eid in ids:\n"
            "    el = doc.GetElement(DB.ElementId(int(eid)))\n"
            "    if el:\n"
            "        p = el.LookupParameter('{pname}')\n"
            "        if p and not p.IsReadOnly:\n"
            "            p.Set('{val}')\n"
            "            count += 1\n"
            "t.Commit()\n"
            "print(json.dumps({{'updated': count, 'total': len(ids)}}))\n"
        ).format(ids=element_ids, pname=param_name, val=value)
        return adapter.execute_code(code)

    mcp.tool(
        name="set_parameter_bulk",
        description="Set a parameter value on multiple elements at once.\n\nArgs:\n  element_ids: Comma-separated element IDs.\n  param_name: Parameter name to set.\n  value: New value.",
        handler=set_parameter_bulk,
        parameters={
            "type": "object",
            "properties": {
                "element_ids": {"type": "string", "description": "Comma-separated element IDs."},
                "param_name": {"type": "string", "description": "Parameter name to set."},
                "value": {"type": "string", "description": "New value."},
            },
            "required": ["element_ids", "param_name", "value"],
        },
    )

    # ------------------------------------------------------------------
    # Geometry & spatial
    # ------------------------------------------------------------------

    def get_element_location(element_id: str = "") -> dict:
        """Get the location (XYZ coordinates) of an element."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "el = doc.GetElement(DB.ElementId(int('{eid}')))\n"
            "loc = el.Location\n"
            "if hasattr(loc, 'Point'):\n"
            "    p = loc.Point\n"
            "    print(json.dumps({{'type': 'point', 'x': round(p.X, 4), 'y': round(p.Y, 4), 'z': round(p.Z, 4)}}))\n"
            "elif hasattr(loc, 'Curve'):\n"
            "    c = loc.Curve\n"
            "    s, e = c.GetEndPoint(0), c.GetEndPoint(1)\n"
            "    print(json.dumps({{'type': 'curve', 'start': {{'x': round(s.X,4), 'y': round(s.Y,4), 'z': round(s.Z,4)}}, 'end': {{'x': round(e.X,4), 'y': round(e.Y,4), 'z': round(e.Z,4)}}, 'length': round(c.Length, 4)}}))\n"
            "else:\n"
            "    bb = el.get_BoundingBox(None)\n"
            "    if bb:\n"
            "        mid = (bb.Min + bb.Max) / 2\n"
            "        print(json.dumps({{'type': 'bbox_center', 'x': round(mid.X,4), 'y': round(mid.Y,4), 'z': round(mid.Z,4)}}))\n"
            "    else:\n"
            "        print(json.dumps({{'type': 'unknown'}}))\n"
        ).format(eid=element_id)
        return adapter.execute_code(code)

    mcp.tool(
        name="get_element_location",
        description="Get the location (XYZ coordinates) of an element — point, curve endpoints, or bounding box center.\n\nArgs:\n  element_id: Element ID.",
        handler=get_element_location,
        parameters={"type": "object", "properties": {"element_id": {"type": "string", "description": "Element ID."}}, "required": ["element_id"]},
    )

    # ------------------------------------------------------------------
    # Links & imports
    # ------------------------------------------------------------------

    def list_linked_models() -> dict:
        """List all linked Revit models and CAD files."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "result = []\n"
            "# Revit links\n"
            "for link in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements():\n"
            "    lt = doc.GetElement(link.GetTypeId())\n"
            "    result.append({'type': 'revit', 'name': lt.Name if lt else str(link.Id.IntegerValue), 'id': str(link.Id.IntegerValue)})\n"
            "# CAD links\n"
            "for imp in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance).ToElements():\n"
            "    result.append({'type': 'cad', 'name': imp.Name, 'id': str(imp.Id.IntegerValue)})\n"
            "print(json.dumps(result))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(name="list_linked_models", description="List all linked Revit models and imported CAD files.", handler=list_linked_models)

    # ------------------------------------------------------------------
    # Materials
    # ------------------------------------------------------------------

    def list_materials(search: str = "") -> dict:
        """List materials in the model."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()\n"
            "result = []\n"
            "for m in mats:\n"
            "    if '{q}' and '{q}'.lower() not in m.Name.lower():\n"
            "        continue\n"
            "    result.append({{'id': str(m.Id.IntegerValue), 'name': m.Name}})\n"
            "result.sort(key=lambda x: x['name'])\n"
            "print(json.dumps(result[:100]))\n"
        ).format(q=search)
        return adapter.execute_code(code)

    mcp.tool(
        name="list_materials",
        description="List materials in the model, optionally filtered by name.\n\nArgs:\n  search: Text to filter material names (optional).",
        handler=list_materials,
        parameters={"type": "object", "properties": {"search": {"type": "string", "description": "Text to filter material names.", "default": ""}}},
    )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_view_to_image(view_name: str = "", file_path: str = "", dpi: int = 150) -> dict:
        """Export a view to a PNG image file on disk."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "views = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()\n"
            "view = None\n"
            "for v in views:\n"
            "    if v.Name == '{name}':\n"
            "        view = v\n"
            "        break\n"
            "if not view:\n"
            "    print(json.dumps({{'error': 'View not found'}}))\n"
            "else:\n"
            "    import os\n"
            "    opt = DB.ImageExportOptions()\n"
            "    opt.FilePath = r'{path}'\n"
            "    opt.ExportRange = DB.ExportRange.SetOfViews\n"
            "    opt.SetViewsAndSheets([view.Id])\n"
            "    opt.HLRandWFViewsFileType = DB.ImageFileType.PNG\n"
            "    opt.ImageResolution = DB.ImageResolution.DPI_{dpi}\n"
            "    opt.ZoomType = DB.ZoomFitType.FitToPage\n"
            "    opt.PixelSize = 1920\n"
            "    doc.ExportImage(opt)\n"
            "    print(json.dumps({{'success': True, 'path': r'{path}'}}))\n"
        ).format(name=view_name, path=file_path, dpi=dpi)
        return adapter.execute_code(code)

    mcp.tool(
        name="export_view_to_image",
        description="Export a view to a PNG image file on disk.\n\nArgs:\n  view_name: View name to export.\n  file_path: Output file path.\n  dpi: Resolution (default 150).",
        handler=export_view_to_image,
        parameters={
            "type": "object",
            "properties": {
                "view_name": {"type": "string", "description": "View name to export."},
                "file_path": {"type": "string", "description": "Output file path (e.g. 'C:/Users/user/Desktop/view.png')."},
                "dpi": {"type": "integer", "description": "Resolution (default 150).", "default": 150},
            },
            "required": ["view_name", "file_path"],
        },
    )

    # ------------------------------------------------------------------
    # Project info
    # ------------------------------------------------------------------

    def get_project_info() -> dict:
        """Get project information (name, number, address, client, etc.)."""
        code = (
            "from Autodesk.Revit import DB\n"
            "import json\n"
            "doc = __revit__.ActiveUIDocument.Document\n"
            "pi = doc.ProjectInformation\n"
            "result = {}\n"
            "for p in pi.Parameters:\n"
            "    if p.HasValue:\n"
            "        result[p.Definition.Name] = p.AsString() or str(p.AsValueString() or '')\n"
            "print(json.dumps(result))\n"
        )
        return adapter.execute_code(code)

    mcp.tool(name="get_project_info", description="Get all project information parameters (name, number, address, client, status, etc.).", handler=get_project_info)

