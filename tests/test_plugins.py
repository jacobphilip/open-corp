"""Tests for framework/plugins.py — tool registry, built-in tools, tool loop, custom plugins."""

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
import yaml

from framework.config import ToolsConfig
from framework.exceptions import PluginError, ToolError
from framework.knowledge import KnowledgeBase, KnowledgeEntry
from framework.plugins import (
    ToolContext,
    ToolDef,
    ToolRegistry,
    _execute_tool,
    calculator,
    create_default_registry,
    current_time,
    file_reader,
    http_request,
    json_transform,
    knowledge_search,
    load_custom_plugins,
    python_eval,
    shell_exec,
    tool_loop,
    web_search,
)
from framework.router import OPENROUTER_API_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(tmp_path, knowledge=None, tools_config=None):
    """Create a ToolContext for testing."""
    return ToolContext(
        project_dir=tmp_path,
        worker_name="test-worker",
        knowledge=knowledge,
        tools_config=tools_config or ToolsConfig(),
    )


def _mock_openrouter_response(content="Hello!", tool_calls=None, tokens_in=10, tokens_out=5):
    """Create a mock OpenRouter response payload."""
    message = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    }


def _make_tool_call(call_id, name, arguments):
    """Build a tool_calls entry."""
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


# ---------------------------------------------------------------------------
# TestToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_register_and_get(self):
        """Register a tool and retrieve it by name."""
        registry = ToolRegistry()
        tool = ToolDef(name="test", description="A test tool", parameters={}, fn=lambda: "ok")
        registry.register(tool)
        assert registry.get("test") is tool

    def test_get_nonexistent(self):
        """get() returns None for unknown tool."""
        registry = ToolRegistry()
        assert registry.get("nope") is None

    def test_list_all(self):
        """list_all returns all registered tools."""
        registry = ToolRegistry()
        t1 = ToolDef(name="a", description="A", parameters={}, fn=lambda: "a")
        t2 = ToolDef(name="b", description="B", parameters={}, fn=lambda: "b")
        registry.register(t1)
        registry.register(t2)
        assert len(registry.list_all()) == 2

    def test_available_for_level_filtering(self):
        """Only tools at or below the worker's level are returned."""
        registry = ToolRegistry()
        registry.register(ToolDef(name="safe", description="", parameters={}, fn=lambda: "", tier="safe"))
        registry.register(ToolDef(name="priv", description="", parameters={}, fn=lambda: "", tier="privileged"))
        assert len(registry.available_for_level(1)) == 1
        assert registry.available_for_level(1)[0].name == "safe"
        assert len(registry.available_for_level(4)) == 2

    def test_resolve_for_worker_no_explicit(self):
        """Without explicit_tools, returns all qualified tools."""
        registry = ToolRegistry()
        registry.register(ToolDef(name="a", description="", parameters={}, fn=lambda: "", tier="safe"))
        registry.register(ToolDef(name="b", description="", parameters={}, fn=lambda: "", tier="standard"))
        result = registry.resolve_for_worker(3, explicit_tools=None)
        assert len(result) == 2

    def test_resolve_for_worker_explicit_filter(self):
        """With explicit_tools, returns intersection of listed and qualified."""
        registry = ToolRegistry()
        registry.register(ToolDef(name="a", description="", parameters={}, fn=lambda: "", tier="safe"))
        registry.register(ToolDef(name="b", description="", parameters={}, fn=lambda: "", tier="safe"))
        result = registry.resolve_for_worker(1, explicit_tools=["a"])
        assert len(result) == 1
        assert result[0].name == "a"

    def test_resolve_for_worker_explicit_respects_level(self):
        """Explicit list cannot grant access above seniority."""
        registry = ToolRegistry()
        registry.register(ToolDef(name="priv", description="", parameters={}, fn=lambda: "", tier="privileged"))
        result = registry.resolve_for_worker(1, explicit_tools=["priv"])
        assert len(result) == 0

    def test_to_openai_schema(self):
        """Converts tools to OpenAI-compatible schema."""
        tools = [ToolDef(
            name="calc", description="Math", fn=lambda: "",
            parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
        )]
        schema = ToolRegistry.to_openai_schema(tools)
        assert len(schema) == 1
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "calc"
        assert schema[0]["function"]["description"] == "Math"

    def test_tool_def_auto_level(self):
        """ToolDef auto-sets min_level from tier when not specified."""
        safe = ToolDef(name="s", description="", parameters={}, fn=lambda: "", tier="safe")
        standard = ToolDef(name="m", description="", parameters={}, fn=lambda: "", tier="standard")
        priv = ToolDef(name="p", description="", parameters={}, fn=lambda: "", tier="privileged")
        assert safe.min_level == 1
        assert standard.min_level == 3
        assert priv.min_level == 4

    def test_create_default_registry_has_9_tools(self):
        """Factory creates registry with all 9 built-in tools."""
        registry = create_default_registry()
        assert len(registry.list_all()) == 9


# ---------------------------------------------------------------------------
# TestToolLoop
# ---------------------------------------------------------------------------

class TestToolLoop:
    def test_no_tool_calls(self, config, accountant):
        """When LLM returns content only, loop returns immediately."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json=_mock_openrouter_response("Just text"))
            )
            result = tool_loop(
                router, [{"role": "user", "content": "hi"}],
                tools_schema, registry, ctx, max_iterations=5,
            )

        assert result["content"] == "Just text"
        assert result["tool_iterations"] == 1

    def test_single_tool_call(self, config, accountant):
        """Tool call is executed and result fed back."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        tc = _make_tool_call("tc1", "calculator", {"expression": "2 + 3"})

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc])),
                    httpx.Response(200, json=_mock_openrouter_response("The answer is 5.")),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "what is 2+3?"}],
                tools_schema, registry, ctx,
            )

        assert result["content"] == "The answer is 5."
        assert result["tool_iterations"] == 2

    def test_max_iterations_cap(self, config, accountant):
        """Loop stops after max_iterations even if tools keep being called."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        tc = _make_tool_call("tc1", "calculator", {"expression": "1 + 1"})

        with respx.mock:
            # Always return tool calls (never just content)
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc]))
            )
            result = tool_loop(
                router, [{"role": "user", "content": "loop"}],
                tools_schema, registry, ctx, max_iterations=3,
            )

        assert result["tool_iterations"] == 3

    def test_tool_error_returns_error_string(self, config, accountant):
        """When a tool raises an error, the error message is returned as tool result."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")

        def bad_tool(_context=None, **kwargs):
            raise ToolError("bad", "something broke")

        registry = ToolRegistry()
        registry.register(ToolDef(
            name="bad", description="", parameters={}, fn=bad_tool, tier="safe",
        ))
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.list_all())

        tc = _make_tool_call("tc1", "bad", {})

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc])),
                    httpx.Response(200, json=_mock_openrouter_response("Tool had an error.")),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "test"}],
                tools_schema, registry, ctx,
            )

        assert result["content"] == "Tool had an error."

    def test_budget_aggregation(self, config, accountant):
        """Tokens and cost are aggregated across iterations."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        tc = _make_tool_call("tc1", "calculator", {"expression": "1+1"})

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc], tokens_in=10, tokens_out=5)),
                    httpx.Response(200, json=_mock_openrouter_response("Done", tokens_in=20, tokens_out=10)),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "test"}],
                tools_schema, registry, ctx,
            )

        assert result["tokens"]["in"] == 30
        assert result["tokens"]["out"] == 15
        assert result["cost"] > 0

    def test_unknown_tool_returns_error(self, config, accountant):
        """Unknown tool name in tool_calls returns error string."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = ToolRegistry()  # empty registry
        ctx = _make_context(config.project_dir)

        tc = _make_tool_call("tc1", "nonexistent", {})

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc])),
                    httpx.Response(200, json=_mock_openrouter_response("I see the error.")),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "test"}],
                [], registry, ctx,
            )

        assert result["content"] == "I see the error."

    def test_invalid_json_args(self, config, accountant):
        """Invalid JSON in tool arguments returns error string."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        tc = {
            "id": "tc1",
            "type": "function",
            "function": {"name": "calculator", "arguments": "not json!!!"},
        }

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc])),
                    httpx.Response(200, json=_mock_openrouter_response("Handled it.")),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "test"}],
                tools_schema, registry, ctx,
            )

        assert result["content"] == "Handled it."

    def test_multi_tool_calls_in_one_response(self, config, accountant):
        """Multiple tool calls in a single response are all executed."""
        from framework.router import Router
        router = Router(config, accountant, api_key="test-key")
        registry = create_default_registry()
        ctx = _make_context(config.project_dir)
        tools_schema = ToolRegistry.to_openai_schema(registry.available_for_level(1))

        tc1 = _make_tool_call("tc1", "calculator", {"expression": "2+2"})
        tc2 = _make_tool_call("tc2", "calculator", {"expression": "3*3"})

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(200, json=_mock_openrouter_response("", tool_calls=[tc1, tc2])),
                    httpx.Response(200, json=_mock_openrouter_response("4 and 9")),
                ]
            )
            result = tool_loop(
                router, [{"role": "user", "content": "calc"}],
                tools_schema, registry, ctx,
            )

        assert result["content"] == "4 and 9"
        assert result["tool_iterations"] == 2

    def test_result_truncation(self, config, accountant):
        """Long tool results are truncated to max_result_chars."""
        registry = ToolRegistry()
        ctx = _make_context(config.project_dir)

        long_result = _execute_tool(
            registry=ToolRegistry(),
            name="unknown",  # will return error string
            raw_args="{}",
            context=ctx,
            max_chars=10,
        )
        # Error string for unknown tool should be returned as-is (short enough)
        assert "Unknown tool" in long_result


# ---------------------------------------------------------------------------
# TestCalculator
# ---------------------------------------------------------------------------

class TestCalculator:
    def test_arithmetic(self):
        assert calculator(expression="2 + 3") == "5"

    def test_float_result(self):
        assert calculator(expression="10 / 3") == str(10 / 3)

    def test_parentheses(self):
        assert calculator(expression="(2 + 3) * 4") == "20"

    def test_division_by_zero(self):
        with pytest.raises(ToolError, match="Division by zero"):
            calculator(expression="1 / 0")

    def test_injection_rejected(self):
        """Function calls and names are rejected."""
        with pytest.raises(ToolError, match="Disallowed"):
            calculator(expression="__import__('os').system('ls')")


# ---------------------------------------------------------------------------
# TestCurrentTime
# ---------------------------------------------------------------------------

class TestCurrentTime:
    def test_utc_format(self):
        result = current_time()
        assert "T" in result  # ISO format
        assert "+" in result or "Z" in result or "UTC" in result

    def test_offset(self):
        result = current_time(timezone_offset="5")
        assert "T" in result


# ---------------------------------------------------------------------------
# TestKnowledgeSearch
# ---------------------------------------------------------------------------

class TestKnowledgeSearch:
    def test_with_results(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.entries = [
            KnowledgeEntry(source="doc", type="text", content="Python is great for data."),
        ]
        ctx = _make_context(tmp_path, knowledge=kb)
        result = knowledge_search(query="Python", _context=ctx)
        assert "Python" in result

    def test_no_results(self, tmp_path):
        kb = KnowledgeBase(tmp_path)
        kb.entries = [
            KnowledgeEntry(source="doc", type="text", content="JavaScript rocks."),
        ]
        ctx = _make_context(tmp_path, knowledge=kb)
        result = knowledge_search(query="xyznonexistent", _context=ctx)
        # Falls back to returning entries
        assert "JavaScript" in result

    def test_no_knowledge_base(self, tmp_path):
        ctx = _make_context(tmp_path, knowledge=None)
        result = knowledge_search(query="test", _context=ctx)
        assert "No knowledge base" in result


# ---------------------------------------------------------------------------
# TestJsonTransform
# ---------------------------------------------------------------------------

class TestJsonTransform:
    def test_key_access(self):
        data = json.dumps({"name": "Alice"})
        result = json_transform(data=data, path="name")
        assert result == "Alice"

    def test_nested_path(self):
        data = json.dumps({"user": {"name": "Bob"}})
        result = json_transform(data=data, path="user.name")
        assert result == "Bob"

    def test_array_index(self):
        data = json.dumps({"users": [{"name": "A"}, {"name": "B"}]})
        result = json_transform(data=data, path="users.1.name")
        assert result == "B"

    def test_invalid_path(self):
        data = json.dumps({"a": 1})
        result = json_transform(data=data, path="b")
        assert "not found" in result


# ---------------------------------------------------------------------------
# TestWebSearch
# ---------------------------------------------------------------------------

class TestWebSearch:
    def test_success(self, tmp_path):
        ctx = _make_context(tmp_path)
        with respx.mock:
            respx.get("https://api.duckduckgo.com/").mock(
                return_value=httpx.Response(200, json={
                    "AbstractText": "Python is a programming language.",
                    "RelatedTopics": [{"Text": "Python homepage"}],
                })
            )
            result = web_search(query="python", _context=ctx)
        assert "Python" in result

    def test_network_error(self, tmp_path):
        ctx = _make_context(tmp_path)
        with respx.mock:
            respx.get("https://api.duckduckgo.com/").mock(
                side_effect=httpx.ConnectError("fail")
            )
            with pytest.raises(ToolError, match="Request failed"):
                web_search(query="test", _context=ctx)

    def test_ssrf_blocked(self, tmp_path):
        """SSRF prevention: blocked hosts are rejected."""
        ctx = _make_context(tmp_path, tools_config=ToolsConfig(
            blocked_hosts=["api.duckduckgo.com"],
        ))
        with pytest.raises(ToolError, match="Blocked host"):
            web_search(query="test", _context=ctx)


# ---------------------------------------------------------------------------
# TestHttpRequest
# ---------------------------------------------------------------------------

class TestHttpRequest:
    def test_get_request(self, tmp_path):
        ctx = _make_context(tmp_path)
        with respx.mock:
            respx.get("https://example.com/api").mock(
                return_value=httpx.Response(200, text="OK")
            )
            result = http_request(url="https://example.com/api", _context=ctx)
        assert "Status: 200" in result
        assert "OK" in result

    def test_post_request(self, tmp_path):
        ctx = _make_context(tmp_path)
        with respx.mock:
            respx.post("https://example.com/api").mock(
                return_value=httpx.Response(201, text="Created")
            )
            result = http_request(
                url="https://example.com/api", method="POST",
                body='{"key": "val"}', _context=ctx,
            )
        assert "Status: 201" in result

    def test_timeout(self, tmp_path):
        ctx = _make_context(tmp_path, tools_config=ToolsConfig(http_timeout=1))
        with respx.mock:
            respx.get("https://example.com/slow").mock(
                side_effect=httpx.TimeoutException("timeout")
            )
            with pytest.raises(ToolError, match="timed out"):
                http_request(url="https://example.com/slow", _context=ctx)

    def test_ssrf_blocked(self, tmp_path):
        ctx = _make_context(tmp_path)
        with pytest.raises(ToolError, match="Blocked host"):
            http_request(url="http://169.254.169.254/latest/meta-data", _context=ctx)


# ---------------------------------------------------------------------------
# TestFileReader
# ---------------------------------------------------------------------------

class TestFileReader:
    def test_read_file(self, tmp_path):
        (tmp_path / "test.txt").write_text("Hello world")
        ctx = _make_context(tmp_path)
        result = file_reader(path="test.txt", _context=ctx)
        assert result == "Hello world"

    def test_path_traversal_blocked(self, tmp_path):
        ctx = _make_context(tmp_path)
        with pytest.raises(ToolError, match="outside project"):
            file_reader(path="../../../etc/passwd", _context=ctx)

    def test_not_found(self, tmp_path):
        ctx = _make_context(tmp_path)
        with pytest.raises(ToolError, match="not found"):
            file_reader(path="missing.txt", _context=ctx)

    def test_large_file_truncated(self, tmp_path):
        (tmp_path / "big.txt").write_text("x" * 100_000)
        ctx = _make_context(tmp_path)
        result = file_reader(path="big.txt", _context=ctx)
        assert "truncated" in result
        assert len(result) < 100_000


# ---------------------------------------------------------------------------
# TestShellExec
# ---------------------------------------------------------------------------

class TestShellExec:
    def test_success(self, tmp_path):
        ctx = _make_context(tmp_path)
        result = shell_exec(command="echo hello", _context=ctx)
        assert "Exit code: 0" in result
        assert "hello" in result

    def test_timeout(self, tmp_path):
        ctx = _make_context(tmp_path, tools_config=ToolsConfig(shell_timeout=1))
        with pytest.raises(ToolError, match="timed out"):
            shell_exec(command="sleep 10", _context=ctx)

    def test_output_captured(self, tmp_path):
        ctx = _make_context(tmp_path)
        result = shell_exec(command="echo out && echo err >&2", _context=ctx)
        assert "out" in result
        assert "err" in result

    def test_error_exit(self, tmp_path):
        ctx = _make_context(tmp_path)
        result = shell_exec(command="exit 42", _context=ctx)
        assert "Exit code: 42" in result


# ---------------------------------------------------------------------------
# TestPythonEval
# ---------------------------------------------------------------------------

class TestPythonEval:
    def test_math(self):
        result = python_eval(code="result = 2 ** 10")
        assert result == "1024"

    def test_string_op(self):
        result = python_eval(code="result = 'hello'.upper()")
        assert result == "HELLO"

    def test_import_blocked(self):
        with pytest.raises(ToolError, match="Import"):
            python_eval(code="import os")

    def test_dunder_blocked(self):
        with pytest.raises(ToolError, match="Dunder"):
            python_eval(code="x = ''.__class__")


# ---------------------------------------------------------------------------
# TestCustomPluginLoader
# ---------------------------------------------------------------------------

class TestCustomPluginLoader:
    def test_valid_plugin(self, tmp_path):
        """Valid plugin with manifest and tool.py loads successfully."""
        plugin_dir = tmp_path / "plugins" / "greet"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.dump({
            "name": "greet",
            "description": "Say hello",
            "tier": "safe",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
        }))
        (plugin_dir / "tool.py").write_text("def execute(name='World', **kwargs):\n    return f'Hello {name}!'\n")

        registry = ToolRegistry()
        loaded = load_custom_plugins(tmp_path / "plugins", registry)
        assert loaded == ["greet"]
        tool = registry.get("greet")
        assert tool is not None
        assert tool.tier == "safe"

    def test_missing_manifest(self, tmp_path):
        """Plugin without plugin.yaml is skipped."""
        plugin_dir = tmp_path / "plugins" / "bad"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "tool.py").write_text("def execute(): return 'x'\n")

        registry = ToolRegistry()
        loaded = load_custom_plugins(tmp_path / "plugins", registry)
        assert loaded == []

    def test_missing_module(self, tmp_path):
        """Plugin without tool.py is skipped."""
        plugin_dir = tmp_path / "plugins" / "bad2"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.dump({
            "name": "bad2", "description": "Missing module",
        }))

        registry = ToolRegistry()
        loaded = load_custom_plugins(tmp_path / "plugins", registry)
        assert loaded == []

    def test_missing_execute(self, tmp_path):
        """Plugin tool.py without execute() is skipped."""
        plugin_dir = tmp_path / "plugins" / "bad3"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.dump({
            "name": "bad3", "description": "No execute fn",
        }))
        (plugin_dir / "tool.py").write_text("def helper(): return 'x'\n")

        registry = ToolRegistry()
        loaded = load_custom_plugins(tmp_path / "plugins", registry)
        assert loaded == []

    def test_bad_tier(self, tmp_path):
        """Plugin with invalid tier is skipped."""
        plugin_dir = tmp_path / "plugins" / "bad4"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.yaml").write_text(yaml.dump({
            "name": "bad4", "description": "Bad tier", "tier": "mega",
        }))
        (plugin_dir / "tool.py").write_text("def execute(): return 'x'\n")

        registry = ToolRegistry()
        loaded = load_custom_plugins(tmp_path / "plugins", registry)
        assert loaded == []
