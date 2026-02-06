# Architecture

## Component Diagram

```
                    ┌─────────────────────┐
                    │   CLI (corp.py)      │
                    │   Telegram Bot       │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐  ┌─────▼─────┐  ┌──────▼──────┐
     │  HR Manager   │  │  Worker   │  │  Workflow   │
     │  hire/fire/   │  │  chat/    │  │  Engine     │
     │  promote/     │  │  memory/  │  │  DAG exec   │
     │  demote/      │  │  perf     │  │             │
     │  auto_review  │  │           │  │             │
     └───────┬───────┘  └─────┬─────┘  └──────┬──────┘
             │                │                │
             │         ┌──────▼──────┐         │
             │         │   Router    │         │
             │         │ tier-based  │         │
             │         │ model sel.  │         │
             │         └──────┬──────┘         │
             │                │                │
             │         ┌──────▼──────┐         │
             │         │ Accountant  │         │
             │         │ budget ctrl │         │
             │         └──────┬──────┘         │
             │                │                │
             └────────────────┼────────────────┘
                              │
                       ┌──────▼──────┐
                       │   Config    │
                       │ charter.yaml│
                       └──────┬──────┘
                              │
                       ┌──────▼──────┐
                       │ Exceptions  │
                       └─────────────┘
```

## Dependency Chain

```
exceptions → config → accountant → router → worker → hr → CLI
                  ↘ db → events/scheduler/workflow
                  ↘ validation → webhooks/dashboard/hr/scheduler/CLI/bot
                  ↘ webhooks/broker → CLI
                  ↘ registry → CLI
                  ↘ marketplace → CLI
                  ↘ plugins → worker
                  ↘ task_router → workflow/CLI
```

## Design Decisions

### Dataclasses over Pydantic

All configuration and data structures use Python dataclasses. This avoids adding Pydantic as a dependency and keeps the framework lightweight.

### Dependency Injection

Components receive their dependencies through constructors rather than using singletons. The only singleton is the TinyDB registry in `framework.db`, which ensures thread-safe access.

### Thread Safety

All TinyDB operations are protected by `threading.Lock`. The `get_db()` function returns both a database instance and its associated lock. Workflows execute nodes in parallel using `ThreadPoolExecutor`.

### File-Based State

All state (worker memory, performance, knowledge, budget logs, workflow runs) is stored as JSON/YAML files in the project directory. No external database required.

### Budget as Guardrail

The Accountant runs before every API call and cannot be bypassed. It tracks costs per call and enforces daily limits with graduated threshold responses.

### Tier-Based Routing

Models are organized into tiers (cheap, mid, premium). The router tries models within a tier in order, falling back to cheaper tiers under budget pressure.

### Worker Seniority

Worker level (1-5) maps to model tier access. Higher-level workers get access to more capable (and expensive) models. Performance-based auto-promotion/demotion adjusts levels over time.

### Tool Calling

Workers can call tools during conversations via OpenRouter's OpenAI-compatible tool calling API. The tool loop sends messages with a `tools` schema, detects `tool_calls` in the response, executes them locally, appends results, and re-sends until the model returns a content-only response. Tools are seniority-gated: L1-2 get safe tools (calculator, current_time, knowledge_search, json_transform), L3+ adds standard tools (web_search, http_request, file_reader), and L4+ gets privileged tools (shell_exec, python_eval). Custom plugins in `plugins/` are auto-loaded. Safety measures include AST-only evaluation, SSRF prevention, path traversal guards, output truncation, and iteration caps.

### Input Validation

All external input (worker names, file paths, payload sizes) is validated at the boundary. Worker names use a regex whitelist (`^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`). File paths are resolved and checked against the project root. The `validation.py` module is imported by all entry points: HR, scheduler, dashboard, webhooks, CLI, and Telegram bot.

### Rate Limiting

Webhooks and dashboard use an in-process token bucket rate limiter, keyed by client IP. Limits are configurable via `SecurityConfig` in charter.yaml. This prevents abuse without external dependencies.

### Secret Redaction

A `SecretFilter` logging filter automatically redacts API keys, Bearer tokens, and environment variable assignments from log output. Applied by default in `setup_logging()`.

### Atomic Writes

Worker memory and performance JSON files use `safe_write_json()` which writes to a tempfile then atomically renames. This prevents corruption on crash. `safe_load_json()` detects corrupted files, backs them up as `.corrupt`, and returns defaults.

### Router Retry

The router retries transient HTTP errors (429, 502, 503, 504) and connection/timeout exceptions with exponential backoff before falling back to the next model in the tier.

## Module Reference

| Module | Responsibility |
|--------|---------------|
| `exceptions.py` | Custom exception types with suggestions |
| `config.py` | charter.yaml parsing, dataclass configs |
| `db.py` | Thread-safe TinyDB registry |
| `accountant.py` | Budget tracking and enforcement |
| `router.py` | Model selection and API calls |
| `knowledge.py` | Knowledge base storage and search |
| `worker.py` | Worker personality, chat, memory, performance |
| `hr.py` | Hire, fire, promote, demote, train, review |
| `task_router.py` | Skill-based worker selection for tasks |
| `events.py` | Event logging and querying |
| `scheduler.py` | APScheduler task scheduling |
| `workflow.py` | DAG workflow engine with parallel execution |
| `webhooks.py` | Flask webhook HTTP server with rate limiting |
| `broker.py` | Paper trading broker |
| `registry.py` | Multi-operation project registry |
| `marketplace.py` | Remote template marketplace client |
| `plugins.py` | Tool registry, 9 built-in tools, tool loop, custom plugins |
| `validation.py` | Input validation, rate limiting, safe JSON I/O |
| `dashboard.py` | Web dashboard with auth and rate limiting |
| `housekeeping.py` | Data retention and cleanup |
| `log.py` | Structured logging with secret redaction |
