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
```

## Worker Configuration

Each worker has a `config.yaml` in their directory:

```yaml
level: 1                      # Seniority (1=Intern, 5=Principal)
max_context_tokens: 2000
model: "deepseek/deepseek-chat"
```

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
