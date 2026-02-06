# Plugins & Tools

Workers can call tools during conversations. When a worker needs to calculate something, search the web, or read a file, it makes a tool call — the framework executes the tool locally and feeds the result back to the model.

## How It Works

1. Worker sends a message with available tool definitions
2. The model returns `tool_calls` instead of (or alongside) text
3. The framework executes each tool call locally
4. Results are appended to the conversation and sent back to the model
5. The model either makes more tool calls or returns a final text response

This loop repeats up to `max_tool_iterations` (default: 10) per chat message.

## Built-in Tools

### Safe Tier (L1+)

All workers can use these tools:

| Tool | Description |
|------|-------------|
| `calculator` | Safe math evaluation (AST-only, no code execution) |
| `current_time` | Current UTC time with optional timezone offset |
| `knowledge_search` | Search the worker's knowledge base |
| `json_transform` | Parse JSON and extract values by dot-path |

### Standard Tier (L3+)

Mid-level and above workers additionally get:

| Tool | Description |
|------|-------------|
| `web_search` | Search the web via DuckDuckGo API |
| `http_request` | Make HTTP requests (GET, POST, etc.) |
| `file_reader` | Read files within the project directory |

### Privileged Tier (L4+)

Senior and principal workers additionally get:

| Tool | Description |
|------|-------------|
| `shell_exec` | Execute shell commands with timeout |
| `python_eval` | Evaluate Python expressions (AST-validated) |

## CLI

```bash
# List all available tools
corp tools

# List tools available to a specific worker
corp tools alice
```

## Configuration

In `charter.yaml`:

```yaml
tools:
  enabled: true               # Set to false to disable globally
  max_tool_iterations: 10     # Max tool-calling rounds per chat
  tool_result_max_chars: 4000 # Truncate tool results
  shell_timeout: 30           # shell_exec timeout (seconds)
  http_timeout: 15            # HTTP timeout (seconds)
```

### Per-Worker Tool Restrictions

In a worker's `config.yaml`, add an optional `tools` list to restrict which tools are available:

```yaml
level: 3
tools: [calculator, web_search]
```

Without this list, workers get all tools their level qualifies for.

## Safety Measures

| Tool | Risk | Mitigation |
|------|------|------------|
| `calculator` | Eval injection | AST-only parsing — only arithmetic nodes allowed |
| `python_eval` | Code injection | AST validation rejects imports, `__` dunder access, exec/eval/open; restricted globals; 5s timeout |
| `shell_exec` | Arbitrary code | L4+ only, subprocess timeout, output truncation, cwd = project directory |
| `http_request` | SSRF | Blocked hosts list (cloud metadata endpoints, localhost) |
| `web_search` | SSRF | Same blocked hosts check |
| `file_reader` | Path traversal | `validate_path_within()`, 50KB max size |
| All tools | Context blowup | Results truncated to `tool_result_max_chars` |
| All tools | Budget drain | `max_tool_iterations` cap, Accountant enforces per API call |

The `blocked_hosts` list blocks requests to: `169.254.169.254`, `metadata.google.internal`, `localhost`, `127.0.0.1`, `0.0.0.0`.

## Custom Plugins

Create custom tools by adding a directory under `plugins/`:

```
plugins/
  weather/
    plugin.yaml
    tool.py
```

### plugin.yaml

```yaml
name: weather
description: "Get current weather for a location"
tier: standard          # safe | standard | privileged
parameters:
  type: object
  properties:
    location:
      type: string
      description: "City name"
  required: [location]
```

### tool.py

```python
import httpx

def execute(location: str, **kwargs) -> str:
    resp = httpx.get(f"https://wttr.in/{location}?format=3", timeout=10.0)
    return resp.text
```

The module must export an `execute(**kwargs) -> str` function. It receives the parameters defined in `plugin.yaml` as keyword arguments.

### Plugin Tiers

Custom plugins specify a `tier` in their manifest:

- `safe` — available to all workers (L1+)
- `standard` — available to L3+ workers
- `privileged` — available to L4+ workers

If `tier` is omitted, the plugin defaults to `safe`.
