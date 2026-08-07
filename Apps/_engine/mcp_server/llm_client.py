"""LLM client supporting both Gemini and Claude APIs with function calling.

Stdlib-only (urllib). Handles the tool-use loop for both providers.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional, Tuple

SYSTEM_PROMPT = (
    "You are an AI assistant for Ennead Architects, connected to a live Revit session. "
    "You can query and modify the active Revit model using the available tools. "
    "Be concise. When using tools, briefly explain what you're doing. "
    "If a request could modify the model, confirm with the user before proceeding."
)


# ---------------------------------------------------------------------------
# Shared interface
# ---------------------------------------------------------------------------

def run_chat(
    provider: str,
    api_key: str,
    messages: List[Dict[str, str]],
    mcp_tools: List[Dict[str, Any]],
    execute_fn: Callable[[str, Dict], Any],
    system_text: str = SYSTEM_PROMPT,
    max_iterations: int = 10,
) -> Dict[str, Any]:
    """Run a chat turn with tool-use loop.

    Args:
        provider: "gemini" or "anthropic"
        api_key: API key for the provider
        messages: Conversation history [{role, content}]
        mcp_tools: Tool definitions in MCP format
        execute_fn: Callback to execute a tool: (name, args) -> result
        system_text: System prompt
        max_iterations: Safety cap on tool-use loops

    Returns:
        {content: str, tool_calls: [{name, input, result}]}
    """
    if provider == "gemini":
        return _run_gemini(api_key, messages, mcp_tools, execute_fn, system_text, max_iterations)
    elif provider == "anthropic":
        return _run_anthropic(api_key, messages, mcp_tools, execute_fn, system_text, max_iterations)
    else:
        raise ValueError("Unknown provider: {}".format(provider))


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _gemini_tools(mcp_tools: List[Dict]) -> List[Dict]:
    """Convert MCP tool schemas to Gemini functionDeclarations."""
    declarations = []
    for t in mcp_tools:
        decl = {"name": t["name"], "description": t.get("description", "")}
        schema = t.get("inputSchema")
        if schema and schema.get("properties"):
            decl["parameters"] = schema
        declarations.append(decl)
    return [{"functionDeclarations": declarations}]


def _to_gemini_contents(messages: List[Dict[str, str]]) -> List[Dict]:
    """Convert [{role, content}] to Gemini contents format."""
    contents = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    return contents


def _call_gemini(api_key: str, contents: List[Dict], tools: List[Dict],
                 system_text: str) -> Dict:
    url = ("https://generativelanguage.googleapis.com/v1beta/"
           "models/gemini-2.5-flash:generateContent?key={}".format(api_key))
    body = {
        "contents": contents,
        "tools": tools,
        "systemInstruction": {"parts": [{"text": system_text}]},
        "generationConfig": {"temperature": 0.3},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_gemini(api_key, messages, mcp_tools, execute_fn, system_text, max_iter):
    tools = _gemini_tools(mcp_tools)
    contents = _to_gemini_contents(messages)
    tool_calls = []

    for _ in range(max_iter):
        resp = _call_gemini(api_key, contents, tools, system_text)
        candidate = resp.get("candidates", [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])

        # Check for function calls
        fn_calls = [p for p in parts if "functionCall" in p]
        if not fn_calls:
            # No tool calls — extract final text
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            return {"content": "\n".join(text_parts), "tool_calls": tool_calls}

        # Execute each function call
        model_msg = {"role": "model", "parts": parts}
        contents.append(model_msg)

        fn_responses = []
        for fc in fn_calls:
            name = fc["functionCall"]["name"]
            args = fc["functionCall"].get("args", {})
            try:
                result = execute_fn(name, args)
                result_str = result if isinstance(result, str) else json.dumps(result, default=str)
            except Exception as e:
                result_str = "Error: {}".format(e)
            tool_calls.append({"name": name, "input": args, "result": result_str})
            fn_responses.append({
                "functionResponse": {
                    "name": name,
                    "response": {"result": result_str},
                }
            })

        contents.append({"role": "user", "parts": fn_responses})

    return {"content": "Reached tool call limit.", "tool_calls": tool_calls}


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

def _anthropic_tools(mcp_tools: List[Dict]) -> List[Dict]:
    """Convert MCP tool schemas to Anthropic tool format."""
    tools = []
    for t in mcp_tools:
        tools.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
        })
    return tools


def _to_anthropic_messages(messages: List[Dict[str, str]]) -> List[Dict]:
    """Convert to Anthropic messages format."""
    return [{"role": m["role"], "content": m["content"]} for m in messages]


def _call_anthropic(api_key: str, messages: List[Dict], tools: List[Dict],
                    system_text: str) -> Dict:
    url = "https://api.anthropic.com/v1/messages"
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "system": system_text,
        "messages": messages,
        "tools": tools,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_anthropic(api_key, messages, mcp_tools, execute_fn, system_text, max_iter):
    tools = _anthropic_tools(mcp_tools)
    api_messages = _to_anthropic_messages(messages)
    tool_calls = []

    for _ in range(max_iter):
        resp = _call_anthropic(api_key, api_messages, tools, system_text)
        stop_reason = resp.get("stop_reason", "end_turn")
        content_blocks = resp.get("content", [])

        if stop_reason != "tool_use":
            # Final text response
            text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
            return {"content": "\n".join(text_parts), "tool_calls": tool_calls}

        # Append the assistant message with tool_use blocks
        api_messages.append({"role": "assistant", "content": content_blocks})

        # Execute each tool_use block
        tool_results = []
        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            args = block.get("input", {})
            tool_id = block["id"]
            try:
                result = execute_fn(name, args)
                result_str = result if isinstance(result, str) else json.dumps(result, default=str)
            except Exception as e:
                result_str = "Error: {}".format(e)
            tool_calls.append({"name": name, "input": args, "result": result_str})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_str,
            })

        api_messages.append({"role": "user", "content": tool_results})

    return {"content": "Reached tool call limit.", "tool_calls": tool_calls}
