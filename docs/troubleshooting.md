# Troubleshooting

## Common Issues

### "charter.yaml not found"

**Cause:** Running `corp` commands outside a project directory without `--project-dir`.

**Fix:**
```bash
# Navigate to project directory
cd /path/to/project
corp status

# Or use --project-dir
corp --project-dir /path/to/project status

# Or register and switch to a project
corp ops create myproject --dir /path/to/project
corp ops switch myproject
```

### "Budget frozen"

**Cause:** Daily spending limit reached.

**Fix:**
- Wait until the next day (budget resets daily)
- Increase `daily_limit` in `charter.yaml`
- Check spending breakdown: `corp budget`

### "Model unavailable"

**Cause:** All models in the requested tier failed.

**Fix:**
- Check your `OPENROUTER_API_KEY` in `.env`
- Verify model names in `charter.yaml` model tiers
- Check OpenRouter status at openrouter.ai

### Worker not found

**Cause:** Worker directory doesn't exist in `workers/`.

**Fix:**
```bash
corp workers          # List available workers
corp hire researcher alice  # Hire a new one
```

### Training errors

**PDF:** Install pypdf: `pip install pypdf`

**YouTube:** Install yt-dlp and whisper:
```bash
pip install yt-dlp openai-whisper
```

**URL:** Install html2text: `pip install html2text`

### Daemon won't start

**"Already running":** Check if a stale PID file exists:
```bash
corp daemon status    # Will clean up stale PID
corp daemon start
```

**"No enabled tasks":** Add tasks first:
```bash
corp schedule add alice "Check status" --interval 3600
corp daemon start
```

### Webhook "WEBHOOK_API_KEY not set"

Generate and configure a key:
```bash
corp webhook keygen
# Add the output to .env
echo "WEBHOOK_API_KEY=your-key" >> .env
```

### Marketplace "No registry URL configured"

Add the registry URL to `charter.yaml`:
```yaml
marketplace:
  registry_url: "https://example.com/registry.yaml"
```

### Broker "yfinance not installed"

Install the optional broker dependency:
```bash
pip install "open-corp[broker]"
```

Or specify prices manually: `corp broker buy AAPL 10 --price 150`

### Dashboard "401 Unauthorized"

**Cause:** `DASHBOARD_TOKEN` is set but no valid token provided.

**Fix:**

- Browser: visit `http://localhost:5000/login?token=your-token`
- API: include `Authorization: Bearer your-token` header
- Or remove `DASHBOARD_TOKEN` from `.env` to disable auth (localhost only)

### "Validation error: Invalid worker name"

**Cause:** Worker name contains invalid characters (slashes, spaces, special chars, or starts with hyphen/underscore).

**Fix:** Use only letters, numbers, hyphens, and underscores. Must start with a letter or number. Maximum 64 characters.

```bash
# Valid names
corp chat alice
corp chat my-worker-1

# Invalid names
corp chat ../evil       # path traversal
corp chat "my worker"   # spaces
corp chat _private      # leading underscore
```

### "429 Too Many Requests"

**Cause:** Rate limit exceeded on webhook or dashboard.

**Fix:**

- Wait a moment and retry
- Increase limits in `charter.yaml`:
  ```yaml
  security:
    webhook_rate_limit: 20
    webhook_rate_burst: 40
  ```

### ".env file is group/other readable" warning

**Cause:** `.env` has permissions allowing other users to read it.

**Fix:**
```bash
chmod 600 .env
```

## Getting Help

- Check [CLI Reference](user-guide/cli.md) for command syntax
- Check [Configuration](user-guide/configuration.md) for charter.yaml options
- File issues at the project repository
