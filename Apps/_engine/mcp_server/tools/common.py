"""Common MCP tool definitions shared across all application adapters."""

from __future__ import annotations

import base64
import glob
import json
import os
from typing import Dict, List, Optional

from ..adapter import AppAdapter
from ..server import McpServer


# EnneadTab source code root for research tools
def _get_enneadtab_source_roots() -> List[str]:
    """Return paths where EnneadTab source code can be found."""
    roots = []
    # Distributed copy (always present on user machines)
    dump = os.path.join(
        os.environ.get("USERPROFILE", ""),
        "Documents", "EnneadTab Ecosystem", "EA_Dist", "Apps",
    )
    if os.path.isdir(dump):
        roots.append(dump)
    # Dev repo (only on developer machines)
    dev = os.path.join(
        os.environ.get("USERPROFILE", ""),
        "github", "ennead-llp", "EnneadTab-OS", "Apps",
    )
    if os.path.isdir(dev):
        roots.append(dev)
    return roots


def register_common_tools(mcp: McpServer, adapter: AppAdapter) -> None:
    """Register application-agnostic tools on *mcp*."""

    def get_app_status() -> dict:
        """Get the connected application's status."""
        return adapter.get_status()

    mcp.tool(
        name="get_app_status",
        description="Get the connected application's status: app name, version, active document, and connection health.",
        handler=get_app_status,
    )

    def get_model_info() -> dict:
        """Get high-level information about the active model or document."""
        return adapter.get_model_info()

    mcp.tool(
        name="get_model_info",
        description="Get high-level information about the active model or document, such as file path, units, and element counts.",
        handler=get_model_info,
    )

    def list_elements(category: str = "", filters: str = "") -> List[dict]:
        """List elements of the given category."""
        parsed_filters: Optional[Dict] = None
        if filters:
            parsed_filters = json.loads(filters)
        return adapter.list_elements(category, filters=parsed_filters)

    mcp.tool(
        name="list_elements",
        description=(
            "List elements of the given category in the active model.\n\n"
            "Args:\n"
            "  category: Element category to query (e.g. 'Walls', 'Doors').\n"
            "  filters: Optional JSON object of additional filter key/value pairs. "
            "Pass an empty string for no filtering."
        ),
        handler=list_elements,
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Element category to query (e.g. 'Walls', 'Doors')."},
                "filters": {"type": "string", "description": "Optional JSON object of additional filter key/value pairs. Pass an empty string for no filtering.", "default": ""},
            },
            "required": ["category"],
        },
    )

    def get_element_parameters(element_id: str = "") -> dict:
        """Return all parameters for a single element."""
        return adapter.get_element_parameters(element_id)

    mcp.tool(
        name="get_element_parameters",
        description="Return all parameters for a single element identified by its ID.",
        handler=get_element_parameters,
        parameters={
            "type": "object",
            "properties": {
                "element_id": {"type": "string", "description": "The unique identifier of the element."},
            },
            "required": ["element_id"],
        },
    )

    def set_element_parameter(element_id: str = "", param_name: str = "", value: str = "") -> dict:
        """Set a parameter on an element."""
        return adapter.set_element_parameter(element_id, param_name, value)

    mcp.tool(
        name="set_element_parameter",
        description=(
            "Set a parameter on an element and return the updated state.\n\n"
            "Args:\n"
            "  element_id: The unique identifier of the element.\n"
            "  param_name: Name of the parameter to set.\n"
            "  value: New value for the parameter (always passed as a string)."
        ),
        handler=set_element_parameter,
        parameters={
            "type": "object",
            "properties": {
                "element_id": {"type": "string", "description": "The unique identifier of the element."},
                "param_name": {"type": "string", "description": "Name of the parameter to set."},
                "value": {"type": "string", "description": "New value for the parameter (always passed as a string)."},
            },
            "required": ["element_id", "param_name", "value"],
        },
    )

    def execute_code(code: str = "") -> dict:
        """Execute arbitrary code inside the connected application."""
        return adapter.execute_code(code)

    mcp.tool(
        name="execute_code",
        description=(
            "Execute arbitrary code inside the connected application and return stdout, stderr, and error info.\n\n"
            "WARNING: This tool runs code directly in the host application process. "
            "It can modify the model, change application state, or cause data loss. "
            "Use with extreme caution and always review the code before execution.\n\n"
            "Args:\n"
            "  code: Source code string to execute in the host application's scripting environment."
        ),
        handler=execute_code,
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code string to execute in the host application's scripting environment."},
            },
            "required": ["code"],
        },
    )

    def get_view_image(view_name: str = "") -> str:
        """Capture a PNG screenshot."""
        image_bytes = adapter.get_view_image(view_name or None)
        return base64.b64encode(image_bytes).decode("ascii")

    mcp.tool(
        name="get_view_image",
        description=(
            "Capture a PNG screenshot of the specified view (or the active view) "
            "and return it as a base64-encoded string.\n\n"
            "Args:\n"
            "  view_name: Name of the view to capture. Leave empty for the active view."
        ),
        handler=get_view_image,
        parameters={
            "type": "object",
            "properties": {
                "view_name": {"type": "string", "description": "Name of the view to capture. Leave empty for the active view.", "default": ""},
            },
        },
    )

    def list_enneadtab_tools() -> List[dict]:
        """List all available EnneadTab tool modules."""
        return adapter.list_enneadtab_tools()

    mcp.tool(
        name="list_enneadtab_tools",
        description="List all available EnneadTab tool modules and their descriptions.",
        handler=list_enneadtab_tools,
    )

    def run_enneadtab_tool(module: str = "", function: str = "", args: str = "{}") -> dict:
        """Invoke an EnneadTab tool function."""
        parsed_args: Optional[Dict] = None
        if args and args != "{}":
            parsed_args = json.loads(args)
        return adapter.run_enneadtab_tool(module, function, args=parsed_args)

    mcp.tool(
        name="run_enneadtab_tool",
        description=(
            "Invoke an EnneadTab tool function by module and function name.\n\n"
            "Args:\n"
            "  module: The EnneadTab module name (e.g. 'COLOR').\n"
            "  function: The function to call within the module.\n"
            "  args: JSON object of keyword arguments to pass to the function. Defaults to empty object."
        ),
        handler=run_enneadtab_tool,
        parameters={
            "type": "object",
            "properties": {
                "module": {"type": "string", "description": "The EnneadTab module name (e.g. 'COLOR')."},
                "function": {"type": "string", "description": "The function to call within the module."},
                "args": {"type": "string", "description": "JSON object of keyword arguments. Defaults to empty object.", "default": "{}"},
            },
            "required": ["module", "function"],
        },
    )

    # ------------------------------------------------------------------
    # Source code research tools — let the LLM learn from EnneadTab code
    # ------------------------------------------------------------------

    def search_enneadtab_source(query: str = "", file_pattern: str = "*.py") -> str:
        """Search EnneadTab source code for a keyword or pattern."""
        roots = _get_enneadtab_source_roots()
        if not roots:
            return "No EnneadTab source directories found."
        results = []
        for root in roots:
            for dirpath, _, filenames in os.walk(root):
                if "node_modules" in dirpath or "__pycache__" in dirpath:
                    continue
                for fn in filenames:
                    if not fn.endswith(file_pattern.replace("*", "")):
                        continue
                    fpath = os.path.join(dirpath, fn)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for i, line in enumerate(f, 1):
                                if query.lower() in line.lower():
                                    rel = os.path.relpath(fpath, root)
                                    results.append("{}:{}: {}".format(rel, i, line.rstrip()[:200]))
                                    if len(results) >= 50:
                                        return "\n".join(results) + "\n... (truncated at 50 matches)"
                    except Exception:
                        continue
        if not results:
            return "No matches for '{}' in {}".format(query, file_pattern)
        return "\n".join(results)

    mcp.tool(
        name="search_enneadtab_source",
        description=(
            "Search EnneadTab source code for a keyword or pattern. Use this to learn how EnneadTab "
            "implements features, find function names, or understand Revit API usage patterns. "
            "Returns matching lines with file paths and line numbers.\n\n"
            "Args:\n"
            "  query: Text to search for (case-insensitive).\n"
            "  file_pattern: Glob pattern for file types (default '*.py')."
        ),
        handler=search_enneadtab_source,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for (case-insensitive)."},
                "file_pattern": {"type": "string", "description": "Glob pattern for file types (default '*.py').", "default": "*.py"},
            },
            "required": ["query"],
        },
    )

    def read_enneadtab_file(file_path: str = "", start_line: int = 1, end_line: int = 200) -> str:
        """Read a file from the EnneadTab source tree."""
        roots = _get_enneadtab_source_roots()
        for root in roots:
            full = os.path.join(root, file_path)
            if os.path.isfile(full):
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    selected = lines[max(0, start_line - 1):end_line]
                    return "".join("{}:{} {}".format(start_line + i, " ", l) for i, l in enumerate(selected))
                except Exception as e:
                    return "Error reading {}: {}".format(file_path, e)
        return "File not found: {}. Use search_enneadtab_source to find the right path.".format(file_path)

    mcp.tool(
        name="read_enneadtab_file",
        description=(
            "Read a file from the EnneadTab source code. Use after search_enneadtab_source "
            "to read full function implementations. Paths are relative to the Apps/ directory.\n\n"
            "Args:\n"
            "  file_path: Relative path within EnneadTab (e.g. 'lib/EnneadTab/REVIT/REVIT_VIEW.py').\n"
            "  start_line: First line to read (default 1).\n"
            "  end_line: Last line to read (default 200)."
        ),
        handler=read_enneadtab_file,
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path within EnneadTab source."},
                "start_line": {"type": "integer", "description": "First line to read (default 1).", "default": 1},
                "end_line": {"type": "integer", "description": "Last line to read (default 200).", "default": 200},
            },
            "required": ["file_path"],
        },
    )

    def list_enneadtab_modules(directory: str = "lib/EnneadTab") -> str:
        """List Python modules in an EnneadTab directory."""
        roots = _get_enneadtab_source_roots()
        results = []
        for root in roots:
            target = os.path.join(root, directory)
            if not os.path.isdir(target):
                continue
            for item in sorted(os.listdir(target)):
                full = os.path.join(target, item)
                if item.startswith("_") and item != "__init__.py":
                    continue
                if os.path.isdir(full):
                    py_count = len([f for f in os.listdir(full) if f.endswith(".py")])
                    results.append("[DIR]  {}/  ({} .py files)".format(item, py_count))
                elif item.endswith(".py"):
                    # Read first docstring or __doc__
                    desc = ""
                    try:
                        with open(full, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(2000)
                        for line in content.split("\n"):
                            if line.strip().startswith('"""') or line.strip().startswith("'''"):
                                desc = line.strip().strip("\"'")[:80]
                                break
                    except Exception:
                        pass
                    results.append("[FILE] {}  {}".format(item, "- " + desc if desc else ""))
            break  # only use first found root
        if not results:
            return "Directory not found: {}".format(directory)
        return "\n".join(results)

    mcp.tool(
        name="list_enneadtab_modules",
        description=(
            "List Python modules and subdirectories in an EnneadTab directory. "
            "Start with 'lib/EnneadTab' for the core library, 'lib/EnneadTab/REVIT' for Revit-specific modules, "
            "or '_revit/EnneaDuck.extension/EnneadTab.tab' for UI tool scripts.\n\n"
            "Args:\n"
            "  directory: Relative path within Apps/ (default 'lib/EnneadTab')."
        ),
        handler=list_enneadtab_modules,
        parameters={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative path within Apps/ (default 'lib/EnneadTab').", "default": "lib/EnneadTab"},
            },
        },
    )

    # ------------------------------------------------------------------
    # Web research tools — shared across Revit & Rhino
    # ------------------------------------------------------------------

    _API_DOC_SITES = {
        "revit": "revitapidocs.com",
        "rhino": "developer.rhino3d.com",
    }

    def search_api_docs(query: str = "", platform: str = "") -> str:
        """Search official API documentation for Revit or Rhino."""
        import re
        import urllib.request
        import urllib.parse
        site = _API_DOC_SITES.get(platform, "")
        if site:
            search_q = "{} site:{}".format(query, site)
        else:
            search_q = "{} (site:revitapidocs.com OR site:developer.rhino3d.com)".format(query)
        url = "https://www.google.com/search?q={}".format(urllib.parse.quote(search_q))
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            results = []
            for match in re.finditer(r'href="/url\?q=(https?://(?:www\.revitapidocs\.com|developer\.rhino3d\.com)[^&"]+)', html):
                results.append(urllib.parse.unquote(match.group(1)))
            if results:
                return "API doc links:\n" + "\n".join(dict.fromkeys(results)[:10])
            return "No results. Try broader terms."
        except Exception as e:
            return "Search failed: {}".format(e)

    mcp.tool(
        name="search_api_docs",
        description=(
            "Search official API documentation for Revit (revitapidocs.com) or Rhino (developer.rhino3d.com). "
            "Use to look up classes, methods, enums, or concepts.\n\n"
            "Args:\n"
            "  query: Search query (e.g. 'FilteredElementCollector', 'RhinoDoc.Objects').\n"
            "  platform: 'revit' or 'rhino' (leave empty to search both)."
        ),
        handler=search_api_docs,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "API search query."},
                "platform": {"type": "string", "description": "'revit', 'rhino', or empty for both.", "default": ""},
            },
            "required": ["query"],
        },
    )

    def fetch_webpage(url: str = "") -> str:
        """Fetch a webpage and extract text content."""
        import re
        import urllib.request
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            # Strip tags, keep text
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]
        except Exception as e:
            return "Failed to fetch: {}".format(e)

    mcp.tool(
        name="fetch_webpage",
        description=(
            "Fetch a webpage and extract its text content. Use after search_api_docs to read "
            "the actual documentation page.\n\n"
            "Args:\n"
            "  url: Full URL to fetch."
        ),
        handler=fetch_webpage,
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to fetch."},
            },
            "required": ["url"],
        },
    )

    def web_search(query: str = "") -> str:
        """General web search for BIM/architecture topics."""
        import re
        import urllib.request
        import urllib.parse
        url = "https://www.google.com/search?q={}".format(urllib.parse.quote(query))
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            snippets = re.findall(r'<span[^>]*>((?:(?!</span>).)+)</span>', html)
            meaningful = [s for s in snippets if len(s) > 40 and '<' not in s][:10]
            if meaningful:
                return "\n---\n".join(meaningful)
            return "No useful results found."
        except Exception as e:
            return "Search failed: {}".format(e)

    mcp.tool(
        name="web_search",
        description=(
            "Search the web for BIM, architecture, Revit, Rhino, or general technical information.\n\n"
            "Args:\n"
            "  query: Search query."
        ),
        handler=web_search,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
            },
            "required": ["query"],
        },
    )
