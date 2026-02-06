# Configuration

All project configuration lives in `charter.yaml` at the project root.

## charter.yaml Reference

```yaml
project:
  name: "My Project"          # Required
  owner: "Your Name"          # Required
  mission: "What this does"   # Required

budget:
  daily_limit: 3.00           # Required — max daily spend (USD)
  currency: "USD"
  thresholds:
    normal: 0.60              # Below 60% = normal
    caution: 0.80             # 60-80% = caution
    austerity: 0.95           # 80-95% = austerity
    critical: 1.00            # 95-100% = critical (frozen)

models:
  tiers:
    cheap:
      models: ["deepseek/deepseek-chat", "mistralai/mistral-tiny"]
      for: "Simple tasks"
    mid:
      models: ["anthropic/claude-sonnet-4-20250514"]
      for: "Complex tasks"
    premium:
      models: ["anthropic/claude-opus-4-5-20251101"]
      for: "Board-level decisions"

worker_defaults:
  starting_level: 1           # 1-5 seniority scale
  max_context_tokens: 2000    # Token budget for system prompts
  model: "deepseek/deepseek-chat"
  honest_ai: true             # Add "never fabricate" reminder
  max_history_messages: 50    # Chat history limit

promotion_rules:
  min_tasks: 5                # Minimum rated tasks before review
  promote_threshold: 4.0      # Avg rating >= this → promote
  demote_threshold: 2.0       # Avg rating <= this → demote
  review_window: 20           # Last N tasks to consider

marketplace:
  registry_url: ""            # URL to remote template registry YAML

logging:
  level: "INFO"               # DEBUG | INFO | WARNING | ERROR
  file: "data/open-corp.log"  # Relative to project dir; empty = stderr only

retention:
  events_days: 90             # Days to keep events
  spending_days: 90           # Days to keep spending records
  workflows_days: 90          # Days to keep workflow run history
  performance_max: 100        # Max performance records per worker

security:
  webhook_rate_limit: 10      # Requests/sec per IP (webhook server)
  webhook_rate_burst: 20      # Burst capacity
  dashboard_rate_limit: 30    # Requests/sec per IP (dashboard)
  dashboard_rate_burst: 60    # Burst capacity

tools:
  enabled: true               # Enable/disable tool calling globally
  max_tool_iterations: 10     # Max tool-calling rounds per chat
  tool_result_max_chars: 4000 # Truncate tool results to this length
  shell_timeout: 30           # Shell exec timeout (seconds)
  http_timeout: 15            # HTTP request timeout (seconds)

git:
  auto_commit: false
  auto_push: false
  remote: "origin"
  branch: "main"

board:
  enabled: false              # Enable Board of Advisors
```

## Environment Variables

Store secrets in `.env` at the project root:

```
OPENROUTER_API_KEY=sk-or-your-key-here
WEBHOOK_API_KEY=your-webhook-secret
DASHBOARD_TOKEN=your-dashboard-auth-token
```

!!! warning ".env file permissions"
    The `.env` file should be readable only by the owner (`chmod 600 .env`). If group or other permissions are set, a warning is emitted on startup. `corp init` automatically sets secure permissions.

## Worker Configuration

Each worker has a `config.yaml` in their directory:

```yaml
level: 1                      # Seniority (1=Intern, 5=Principal)
max_context_tokens: 2000
model: "deepseek/deepseek-chat"
```

Workers can also have an optional `tools` list to restrict which tools are available:

```yaml
level: 3
tools: [calculator, web_search]   # Only these tools (must qualify by level)
```

Without an explicit `tools` list, workers get all tools their seniority level qualifies for.

## Seniority Levels

| Level | Title     | Model Tier |
|-------|-----------|------------|
| 1     | Intern    | cheap      |
| 2     | Junior    | cheap      |
| 3     | Mid       | mid        |
| 4     | Senior    | premium    |
| 5     | Principal | premium    |

## Logging

Configure logging output level and optional file logging:

```yaml
logging:
  level: "INFO"               # DEBUG, INFO, WARNING, or ERROR
  file: "data/open-corp.log"  # Optional — leave empty for stderr only
```

Use `--verbose` / `-v` on any CLI command to override level to DEBUG.

Both fields are optional. Defaults: level=INFO, no log file.

## Retention

Control how long data is kept before `corp housekeep` removes it:

```yaml
retention:
  events_days: 90        # Remove events older than N days
  spending_days: 90      # Remove spending records older than N days
  workflows_days: 90     # Remove workflow runs older than N days
  performance_max: 100   # Keep only the newest N performance records per worker
```

All fields are optional with the defaults shown above. Run `corp housekeep --dry-run` to preview what would be removed.

## Budget Thresholds

The accountant tracks spending and enforces budget pressure:

- **Normal** (< 60% spent) — all tiers available
- **Caution** (60-80%) — warning logged
- **Austerity** (80-95%) — forces cheaper model tiers
- **Critical** (> 95%) — API calls blocked

## Security

Configure rate limiting for webhooks and dashboard:

```yaml
security:
  webhook_rate_limit: 10    # Requests/sec per IP
  webhook_rate_burst: 20    # Burst capacity (allows short spikes)
  dashboard_rate_limit: 30  # Requests/sec per IP
  dashboard_rate_burst: 60  # Burst capacity
```

All fields are optional with the defaults shown above.

**Dashboard authentication:** Set `DASHBOARD_TOKEN` in `.env` to require authentication. Without it, the dashboard is open (bind to localhost only). With a token set:

- Browser: visit `/login?token=your-token` to get an httponly session cookie
- API: include `Authorization: Bearer your-token` header

**Worker name validation:** All worker names are validated against `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`. Names with path traversal characters, slashes, or special characters are rejected.

**Secret redaction:** API keys and tokens are automatically redacted from log output. Patterns matched: `sk-or-*`, `sk-*`, `Bearer *`, and `API_KEY=*` style assignments.

**Router retry:** Transient API errors (HTTP 429, 502, 503, 504) are retried with exponential backoff before falling back to the next model. Configure via Router constructor:

- `max_retries` — retries per model (default: 2)
- `retry_base_delay` — initial delay in seconds (default: 1.0)
- `retry_max_delay` — maximum delay cap (default: 8.0)

## Tools

Configure worker tool calling:

```yaml
tools:
  enabled: true               # Set to false to disable all tool calling
  max_tool_iterations: 10     # Max tool-calling rounds per chat message
  tool_result_max_chars: 4000 # Truncate tool results to this length
  shell_timeout: 30           # Timeout for shell_exec tool (seconds)
  http_timeout: 15            # Timeout for http_request and web_search (seconds)
```

All fields are optional with the defaults shown above. Set `enabled: false` to disable tool calling globally.

See [Plugins & Tools](plugins.md) for details on built-in tools, safety tiers, and custom plugins.
