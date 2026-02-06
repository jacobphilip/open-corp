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

## Budget Thresholds

The accountant tracks spending and enforces budget pressure:

- **Normal** (< 60% spent) — all tiers available
- **Caution** (60-80%) — warning logged
- **Austerity** (80-95%) — forces cheaper model tiers
- **Critical** (> 95%) — API calls blocked
