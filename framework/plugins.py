"""Plugin system — tool registry, built-in tools, tool loop, and custom plugin loader."""

import ast
import importlib.util
import json
import math
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import yaml

from framework.config import ToolsConfig, _DEFAULT_BLOCKED_HOSTS
from framework.exceptions import PluginError, ToolError
from framework.log import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolDef:
    """Definition of a callable tool."""

    name: str
    description: str
    parameters: dict          # JSON Schema
    fn: Callable
    tier: str = "safe"        # "safe" | "standard" | "privileged"
    min_level: int = 1

    def __post_init__(self):
        _TIER_LEVELS = {"safe": 1, "standard": 3, "privileged": 4}
        if self.min_level == 1 and self.tier in _TIER_LEVELS:
            self.min_level = _TIER_LEVELS[self.tier]


@dataclass
class ToolContext:
    """Runtime context passed to tool functions via _context kwarg."""

    project_dir: Path
    worker_name: str
    knowledge: Any = None  # KnowledgeBase | None
    tools_config: ToolsConfig = field(default_factory=ToolsConfig)


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolDef]:
        return list(self._tools.values())

    def available_for_level(self, level: int) -> list[ToolDef]:
        return [t for t in self._tools.values() if t.min_level <= level]

    def resolve_for_worker(
        self, level: int, explicit_tools: list[str] | None = None,
    ) -> list[ToolDef]:
        """Resolve tools available to a worker.

        If explicit_tools provided, return intersection of (listed tools) and
        (tools the worker qualifies for by level). If None, return all tools
        the worker qualifies for.
        """
        qualified = {t.name: t for t in self.available_for_level(level)}
        if explicit_tools is None:
            return list(qualified.values())
        return [qualified[n] for n in explicit_tools if n in qualified]

    @staticmethod
    def to_openai_schema(tools: list[ToolDef]) -> list[dict]:
        """Convert tool definitions to OpenAI-compatible tools array."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]


# ---------------------------------------------------------------------------
# Tool loop
# ---------------------------------------------------------------------------

def tool_loop(
    router,
    messages: list[dict],
    tools_schema: list[dict],
    registry: ToolRegistry,
    context: ToolContext,
    worker_name: str = "system",
    tier: str = "cheap",
    max_iterations: int = 10,
    max_result_chars: int = 4000,
) -> dict:
    """Execute the tool-calling loop.

    Calls router.chat() with tools. If response contains tool_calls, executes
    them, appends results, and loops. Returns aggregated result dict.
    """
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    model_used = ""
    iterations = 0

    working_messages = list(messages)

    for iteration in range(max_iterations):
        iterations = iteration + 1

        # First iteration uses tools; subsequent also use tools
        result = router.chat(
            messages=working_messages,
            tier=tier,
            worker_name=worker_name,
            tools=tools_schema,
        )

        model_used = result.get("model_used", model_used)
        total_tokens_in += result.get("tokens", {}).get("in", 0)
        total_tokens_out += result.get("tokens", {}).get("out", 0)
        total_cost += result.get("cost", 0.0)

        tool_calls = result.get("tool_calls")
        if not tool_calls:
            # No tool calls — LLM is done
            return {
                "content": result.get("content", ""),
                "model_used": model_used,
                "tokens": {"in": total_tokens_in, "out": total_tokens_out},
                "cost": total_cost,
                "tool_iterations": iterations,
            }

        # Build assistant message with tool_calls
        assistant_msg = {"role": "assistant", "content": result.get("content", "") or None}
        assistant_msg["tool_calls"] = tool_calls
        working_messages.append(assistant_msg)

        # Execute each tool call and append results
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            func_info = tc.get("function", {})
            func_name = func_info.get("name", "")
            raw_args = func_info.get("arguments", "{}")

            tool_result = _execute_tool(
                registry, func_name, raw_args, context, max_result_chars,
            )

            working_messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": tool_result,
            })

    # Max iterations reached — return last content
    return {
        "content": result.get("content", "") or "Tool loop reached maximum iterations.",
        "model_used": model_used,
        "tokens": {"in": total_tokens_in, "out": total_tokens_out},
        "cost": total_cost,
        "tool_iterations": iterations,
    }


def _execute_tool(
    registry: ToolRegistry,
    name: str,
    raw_args: str,
    context: ToolContext,
    max_chars: int,
) -> str:
    """Execute a single tool call safely."""
    tool = registry.get(name)
    if tool is None:
        return f"Error: Unknown tool '{name}'"

    try:
        kwargs = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError:
        return f"Error: Invalid JSON arguments for tool '{name}'"

    try:
        kwargs["_context"] = context
        result = tool.fn(**kwargs)
        result = str(result)
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n... (truncated to {max_chars} chars)"
        return result
    except ToolError as e:
        return f"Error: {e}"
    except Exception as e:
        logger.warning("Tool '%s' raised: %s", name, e)
        return f"Error executing tool '{name}': {e}"


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------

# 1. Calculator — AST-based safe math eval

_CALC_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.USub, ast.UAdd,
)


def calculator(expression: str = "", _context: ToolContext | None = None) -> str:
    """Evaluate a mathematical expression safely using AST parsing."""
    if not expression:
        raise ToolError("calculator", "No expression provided")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ToolError("calculator", f"Invalid expression: {e}")

    # Validate all nodes are allowed
    for node in ast.walk(tree):
        if not isinstance(node, _CALC_ALLOWED_NODES):
            raise ToolError(
                "calculator",
                f"Disallowed operation: {type(node).__name__}",
                suggestion="Only arithmetic operations are allowed.",
            )

    try:
        result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}})
        return str(result)
    except ZeroDivisionError:
        raise ToolError("calculator", "Division by zero")
    except Exception as e:
        raise ToolError("calculator", f"Evaluation error: {e}")


# 2. Current time

def current_time(timezone_offset: str = "UTC", _context: ToolContext | None = None) -> str:
    """Get the current date and time."""
    if timezone_offset == "UTC" or timezone_offset == "0":
        now = datetime.now(timezone.utc)
    else:
        try:
            offset_hours = float(timezone_offset)
            tz = timezone(timedelta(hours=offset_hours))
            now = datetime.now(tz)
        except (ValueError, OverflowError):
            now = datetime.now(timezone.utc)
    return now.isoformat()


# 3. Knowledge search

def knowledge_search(
    query: str = "", max_results: int = 5,
    _context: ToolContext | None = None,
) -> str:
    """Search the worker's knowledge base."""
    if _context is None or _context.knowledge is None:
        return "No knowledge base available."

    entries = _context.knowledge.entries
    if not entries:
        return "Knowledge base is empty."

    from framework.knowledge import search_knowledge
    results = search_knowledge(entries, query, max_chars=4000)
    if not results:
        return f"No results found for '{query}'."

    output = []
    for i, entry in enumerate(results[:max_results]):
        output.append(f"[{i+1}] ({entry.source}) {entry.content[:500]}")
    return "\n".join(output)


# 4. JSON transform

def json_transform(
    data: str = "", path: str = "",
    _context: ToolContext | None = None,
) -> str:
    """Parse JSON and extract data by dot-path."""
    if not data:
        raise ToolError("json_transform", "No data provided")

    try:
        parsed = json.loads(data)
    except json.JSONDecodeError as e:
        raise ToolError("json_transform", f"Invalid JSON: {e}")

    if not path:
        return json.dumps(parsed, indent=2)

    # Navigate dot-path (supports array indices)
    current = parsed
    for key in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return f"Invalid path: '{key}' is not a valid index"
        elif isinstance(current, dict):
            if key not in current:
                return f"Key not found: '{key}'"
            current = current[key]
        else:
            return f"Cannot traverse into {type(current).__name__} with key '{key}'"

    if isinstance(current, (dict, list)):
        return json.dumps(current, indent=2)
    return str(current)


# 5. Web search (DuckDuckGo API)

def _check_blocked_host(url: str, blocked_hosts: list[str]) -> None:
    """Raise ToolError if URL host is blocked."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host in blocked_hosts:
        raise ToolError("web_search", f"Blocked host: {host}")


def web_search(query: str = "", _context: ToolContext | None = None) -> str:
    """Search the web using DuckDuckGo instant answer API."""
    if not query:
        raise ToolError("web_search", "No query provided")

    url = "https://api.duckduckgo.com/"
    blocked = _context.tools_config.blocked_hosts if _context else list(_DEFAULT_BLOCKED_HOSTS)
    _check_blocked_host(url, blocked)
    timeout = _context.tools_config.http_timeout if _context else 15

    try:
        resp = httpx.get(
            url, params={"q": query, "format": "json", "no_html": "1"},
            timeout=float(timeout),
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        raise ToolError("web_search", f"Request failed: {e}")

    parts = []
    abstract = data.get("AbstractText", "")
    if abstract:
        parts.append(f"Summary: {abstract}")
    for topic in data.get("RelatedTopics", [])[:5]:
        text = topic.get("Text", "")
        if text:
            parts.append(f"- {text}")
    return "\n".join(parts) if parts else f"No results found for '{query}'."


# 6. HTTP request

def http_request(
    url: str = "", method: str = "GET", headers: str = "", body: str = "",
    _context: ToolContext | None = None,
) -> str:
    """Make an HTTP request."""
    if not url:
        raise ToolError("http_request", "No URL provided")

    blocked = _context.tools_config.blocked_hosts if _context else list(_DEFAULT_BLOCKED_HOSTS)
    _check_blocked_host(url, blocked)
    timeout = _context.tools_config.http_timeout if _context else 15

    parsed_headers = {}
    if headers:
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError:
            raise ToolError("http_request", "Invalid headers JSON")

    try:
        resp = httpx.request(
            method.upper(), url,
            headers=parsed_headers,
            content=body if body else None,
            timeout=float(timeout),
        )
        status = resp.status_code
        body_text = resp.text
        return f"Status: {status}\n\n{body_text}"
    except httpx.TimeoutException:
        raise ToolError("http_request", f"Request timed out after {timeout}s")
    except httpx.HTTPError as e:
        raise ToolError("http_request", f"Request failed: {e}")


# 7. File reader

def file_reader(path: str = "", _context: ToolContext | None = None) -> str:
    """Read a file within the project directory."""
    if not path:
        raise ToolError("file_reader", "No path provided")
    if _context is None:
        raise ToolError("file_reader", "No context available")

    from framework.validation import validate_path_within

    file_path = _context.project_dir / path
    try:
        resolved = validate_path_within(file_path, _context.project_dir)
    except Exception:
        raise ToolError(
            "file_reader", f"Path '{path}' is outside project directory",
            suggestion="Use a relative path within the project.",
        )

    if not resolved.exists():
        raise ToolError("file_reader", f"File not found: {path}")
    if not resolved.is_file():
        raise ToolError("file_reader", f"Not a file: {path}")

    max_size = 50 * 1024  # 50KB
    size = resolved.stat().st_size
    if size > max_size:
        content = resolved.read_text(errors="replace")[:max_size]
        return content + f"\n... (truncated, file is {size} bytes)"

    try:
        return resolved.read_text(errors="replace")
    except Exception as e:
        raise ToolError("file_reader", f"Cannot read file: {e}")


# 8. Shell exec

def shell_exec(command: str = "", _context: ToolContext | None = None) -> str:
    """Execute a shell command in the project directory."""
    if not command:
        raise ToolError("shell_exec", "No command provided")
    if _context is None:
        raise ToolError("shell_exec", "No context available")

    timeout = _context.tools_config.shell_timeout

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_context.project_dir),
        )
        output = f"Exit code: {result.returncode}\n"
        if result.stdout:
            output += f"stdout:\n{result.stdout}\n"
        if result.stderr:
            output += f"stderr:\n{result.stderr}\n"
        return output.strip()
    except subprocess.TimeoutExpired:
        raise ToolError("shell_exec", f"Command timed out after {timeout}s")
    except Exception as e:
        raise ToolError("shell_exec", f"Execution failed: {e}")


# 9. Python eval

_PYTHON_EVAL_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom,
)

_PYTHON_EVAL_FORBIDDEN_CALLS = {"exec", "eval", "open", "compile", "__import__"}


def _validate_python_ast(code: str) -> None:
    """Validate Python code AST for safety."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        raise ToolError("python_eval", f"Syntax error: {e}")

    for node in ast.walk(tree):
        if isinstance(node, _PYTHON_EVAL_FORBIDDEN_NODES):
            raise ToolError(
                "python_eval", "Import statements are not allowed",
                suggestion="Use only built-in operations.",
            )
        # Block dunder attribute access
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ToolError(
                "python_eval", f"Dunder attribute access '{node.attr}' is not allowed",
            )
        # Block forbidden function calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _PYTHON_EVAL_FORBIDDEN_CALLS:
                raise ToolError(
                    "python_eval", f"Function '{func.id}' is not allowed",
                )


def python_eval(code: str = "", _context: ToolContext | None = None) -> str:
    """Evaluate Python code with safety restrictions."""
    if not code:
        raise ToolError("python_eval", "No code provided")

    _validate_python_ast(code)

    # Restricted globals
    safe_globals = {
        "__builtins__": {},
        "math": math,
        "json": json,
        "datetime": datetime,
        "timedelta": timedelta,
        "re": re,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "set": set,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "map": map,
        "filter": filter,
        "sorted": sorted,
        "reversed": reversed,
        "sum": sum,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "print": lambda *a, **kw: None,  # swallow print
        "isinstance": isinstance,
        "type": type,
    }

    result_container = [None]
    error_container = [None]

    def _run():
        try:
            local_ns = {}
            exec(compile(code, "<python_eval>", "exec"), safe_globals, local_ns)
            # Return the last expression value if stored as 'result'
            if "result" in local_ns:
                result_container[0] = str(local_ns["result"])
            elif local_ns:
                # Return the last assigned variable
                last_key = list(local_ns.keys())[-1]
                result_container[0] = str(local_ns[last_key])
            else:
                result_container[0] = "(no output)"
        except Exception as e:
            error_container[0] = str(e)

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=5.0)

    if thread.is_alive():
        raise ToolError("python_eval", "Execution timed out (5s limit)")

    if error_container[0] is not None:
        raise ToolError("python_eval", f"Runtime error: {error_container[0]}")

    return result_container[0] or "(no output)"


# ---------------------------------------------------------------------------
# Built-in tool definitions
# ---------------------------------------------------------------------------

def _builtin_tools() -> list[ToolDef]:
    """Create all 9 built-in tool definitions."""
    return [
        ToolDef(
            name="calculator",
            description="Evaluate a mathematical expression (arithmetic only).",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g. '2 + 3 * 4')",
                    },
                },
                "required": ["expression"],
            },
            fn=calculator,
            tier="safe",
        ),
        ToolDef(
            name="current_time",
            description="Get the current date and time.",
            parameters={
                "type": "object",
                "properties": {
                    "timezone_offset": {
                        "type": "string",
                        "description": "UTC offset in hours (e.g. '-5', '5.5') or 'UTC'",
                    },
                },
            },
            fn=current_time,
            tier="safe",
        ),
        ToolDef(
            name="knowledge_search",
            description="Search the worker's knowledge base for relevant information.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
            fn=knowledge_search,
            tier="safe",
        ),
        ToolDef(
            name="json_transform",
            description="Parse JSON data and extract values by dot-path.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "string",
                        "description": "JSON string to parse",
                    },
                    "path": {
                        "type": "string",
                        "description": "Dot-path to extract (e.g. 'users.0.name')",
                    },
                },
                "required": ["data"],
            },
            fn=json_transform,
            tier="safe",
        ),
        ToolDef(
            name="web_search",
            description="Search the web using DuckDuckGo.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                },
                "required": ["query"],
            },
            fn=web_search,
            tier="standard",
        ),
        ToolDef(
            name="http_request",
            description="Make an HTTP request to a URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to request",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                    },
                    "headers": {
                        "type": "string",
                        "description": "JSON string of headers",
                    },
                    "body": {
                        "type": "string",
                        "description": "Request body",
                    },
                },
                "required": ["url"],
            },
            fn=http_request,
            tier="standard",
        ),
        ToolDef(
            name="file_reader",
            description="Read a file from the project directory.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file",
                    },
                },
                "required": ["path"],
            },
            fn=file_reader,
            tier="standard",
        ),
        ToolDef(
            name="shell_exec",
            description="Execute a shell command in the project directory.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                },
                "required": ["command"],
            },
            fn=shell_exec,
            tier="privileged",
        ),
        ToolDef(
            name="python_eval",
            description="Evaluate Python code with safety restrictions (no imports, no file I/O).",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                },
                "required": ["code"],
            },
            fn=python_eval,
            tier="privileged",
        ),
    ]


# ---------------------------------------------------------------------------
# Custom plugin loader
# ---------------------------------------------------------------------------

def load_custom_plugins(plugins_dir: Path, registry: ToolRegistry) -> list[str]:
    """Load custom plugins from plugins/ directory.

    Each plugin is a subdirectory with plugin.yaml + tool.py.
    Returns list of loaded plugin names.
    """
    loaded = []
    if not plugins_dir.exists() or not plugins_dir.is_dir():
        return loaded

    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue

        manifest_path = plugin_dir / "plugin.yaml"
        module_path = plugin_dir / "tool.py"

        if not manifest_path.exists():
            logger.warning("Plugin '%s': missing plugin.yaml, skipping", plugin_dir.name)
            continue
        if not module_path.exists():
            logger.warning("Plugin '%s': missing tool.py, skipping", plugin_dir.name)
            continue

        try:
            manifest = yaml.safe_load(manifest_path.read_text())
        except yaml.YAMLError as e:
            logger.warning("Plugin '%s': invalid YAML: %s", plugin_dir.name, e)
            continue

        if not isinstance(manifest, dict):
            logger.warning("Plugin '%s': manifest must be a mapping", plugin_dir.name)
            continue

        name = manifest.get("name")
        description = manifest.get("description")
        parameters = manifest.get("parameters", {})
        tier = manifest.get("tier", "safe")

        if not name or not description:
            logger.warning("Plugin '%s': name and description required", plugin_dir.name)
            continue

        valid_tiers = {"safe", "standard", "privileged"}
        if tier not in valid_tiers:
            logger.warning("Plugin '%s': invalid tier '%s', skipping", plugin_dir.name, tier)
            continue

        # Load module
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{name}", str(module_path),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.warning("Plugin '%s': failed to load module: %s", plugin_dir.name, e)
            continue

        if not hasattr(module, "execute"):
            logger.warning("Plugin '%s': tool.py must export execute()", plugin_dir.name)
            continue

        # Wrap the execute function to accept _context
        raw_fn = module.execute

        def _make_wrapper(fn):
            def wrapper(_context=None, **kwargs):
                return str(fn(**kwargs))
            return wrapper

        registry.register(ToolDef(
            name=name,
            description=description,
            parameters=parameters,
            fn=_make_wrapper(raw_fn),
            tier=tier,
        ))
        loaded.append(name)
        logger.info("Loaded custom plugin: %s (tier=%s)", name, tier)

    return loaded


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_default_registry() -> ToolRegistry:
    """Create a ToolRegistry with all 9 built-in tools registered."""
    registry = ToolRegistry()
    for tool in _builtin_tools():
        registry.register(tool)
    return registry
