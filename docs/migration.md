# Migration Guide

## v1.2 to v1.3

### Breaking Changes

None. v1.3 is fully backward-compatible with v1.2 projects.

### Security Hardening

v1.3 adds defense-in-depth security with no new dependencies:

- **Input validation** — Worker names are validated with a regex whitelist at all entry points. Invalid names (path traversal, special characters) are rejected with `ValidationError`.
- **Dashboard authentication** — Optional `DASHBOARD_TOKEN` env var or `auth_token` parameter. When set, all requests require a Bearer header or login cookie.
- **Rate limiting** — Webhooks and dashboard have configurable token-bucket rate limiters per IP.
- **Router retry** — Transient HTTP errors (429/502/503/504) are retried with exponential backoff before falling back to the next model.
- **Secret redaction** — API keys, Bearer tokens, and env var assignments are automatically redacted from log output.
- **Atomic JSON writes** — Worker memory and performance files use tempfile+rename to prevent corruption.
- **Payload size limits** — Webhook requests over 1MB are rejected.

### New charter.yaml Section

Optional, with sensible defaults:

```yaml
security:
  webhook_rate_limit: 10    # requests/sec per IP
  webhook_rate_burst: 20    # burst capacity
  dashboard_rate_limit: 30  # requests/sec per IP
  dashboard_rate_burst: 60  # burst capacity
```

### New Environment Variables

| Variable | Purpose |
|----------|---------|
| `DASHBOARD_TOKEN` | Dashboard auth token (optional — no token = no auth) |

### New Framework Module

| Module | Description |
|--------|-------------|
| `framework/validation.py` | Input validation, rate limiting, safe JSON I/O |

### New worker_defaults Field

```yaml
worker_defaults:
  default_max_tokens: null  # Optional max_tokens for API calls
```

### Upgrade Steps

1. Update the package: `pip install -U open-corp`
2. Optionally add `security:` section to `charter.yaml`
3. Set `DASHBOARD_TOKEN` in `.env` if exposing the dashboard beyond localhost
4. Existing `.env` files with group/other-readable permissions will emit a warning — run `chmod 600 .env`

---

## v1.1 to v1.2

### Breaking Changes

None. v1.2 is fully backward-compatible with v1.1 projects.

### New Features

- **Telegram bot parity** — 8 new bot commands: `/fire` (inline keyboard confirm), `/review`, `/delegate`, `/events`, `/schedule`, `/workflow`, `/inspect`, `/housekeep`
- **Web dashboard** — Flask app factory with 7 HTML pages + 6 JSON API endpoints, read-only monitoring
- **CLI dashboard command** — `corp dashboard` with `--port` and `--host` options

### Upgrade Steps

1. Update the package: `pip install -U open-corp`
2. Start the dashboard: `corp dashboard`

---

## v0.5 to v1.0

### Breaking Changes

None. v1.0 is fully backward-compatible with v0.5 projects.

### Behavioral Change: Project Loading

`_load_project()` now checks the operation registry before falling back to the current working directory:

1. `--project-dir` flag (highest priority, unchanged)
2. Active operation from `~/.open-corp/` registry (new in v1.0)
3. Current working directory (unchanged fallback)

When no registry exists (e.g., fresh install or v0.5 upgrade), behavior is identical to v0.5.

### New charter.yaml Sections

These sections are optional and default to sensible values:

```yaml
# Auto-promotion/demotion rules
promotion_rules:
  min_tasks: 5
  promote_threshold: 4.0
  demote_threshold: 2.0
  review_window: 20

# Template marketplace
marketplace:
  registry_url: ""
```

### New CLI Commands

| Command | Description |
|---------|-------------|
| `corp ops create/list/switch/remove/active` | Multi-operation management |
| `corp review [worker] [--auto]` | Performance review and auto-promotion |
| `corp delegate <message>` | Smart task routing |
| `corp marketplace list/search/info/install` | Template marketplace |

### New Framework Modules

| Module | Description |
|--------|-------------|
| `framework/registry.py` | Operation registry (`~/.open-corp/`) |
| `framework/task_router.py` | Skill-based worker selection |
| `framework/marketplace.py` | Remote template marketplace client |

### New Worker Methods

- `Worker.performance_summary()` — aggregated performance stats

### New HR Methods

- `HR.demote()` — decrement worker seniority level
- `HR.team_review()` — aggregate team performance scorecard
- `HR.auto_review()` — auto-promote/demote based on rules

### New Dependencies

No new runtime dependencies. Optional dev dependencies for documentation:

```bash
pip install "open-corp[docs]"
# mkdocs, mkdocs-material, mkdocstrings[python]
```

### Upgrade Steps

1. Update the package: `pip install -U open-corp`
2. Optionally add `promotion_rules` and `marketplace` sections to `charter.yaml`
3. Register existing projects: `corp ops create myproject --dir /path/to/project`
4. Set active: `corp ops switch myproject`
