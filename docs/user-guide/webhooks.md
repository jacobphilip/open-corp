# Webhooks

The webhook server exposes an HTTP API for triggering tasks externally.

## Setup

1. Generate an API key:
   ```bash
   corp webhook keygen
   ```

2. Add the key to `.env`:
   ```
   WEBHOOK_API_KEY=your-generated-key
   ```

3. Start the server:
   ```bash
   corp webhook start
   corp webhook start --port 9090 --host 0.0.0.0
   ```

## Authentication

All requests require a Bearer token in the `Authorization` header:

```
Authorization: Bearer your-api-key
```

Token comparison uses `hmac.compare_digest` for constant-time security.

## Endpoints

### POST /webhook/chat

Send a message to a worker.

```json
{
  "worker": "alice",
  "message": "Analyze this data"
}
```

Response:

```json
{
  "worker": "alice",
  "response": "Analysis results...",
  "status": "ok"
}
```

### POST /webhook/schedule

Create a scheduled task.

```json
{
  "worker": "bob",
  "message": "Daily report",
  "schedule_type": "cron",
  "schedule_value": "0 9 * * *"
}
```

### GET /webhook/status

Health check and project status.

```json
{
  "project": "My Project",
  "status": "ok",
  "workers": 3,
  "budget_remaining": 2.50
}
```

## Rate Limiting

The webhook server includes a token-bucket rate limiter per client IP. Configure limits in `charter.yaml`:

```yaml
security:
  webhook_rate_limit: 10    # requests/sec per IP
  webhook_rate_burst: 20    # burst capacity
```

When the rate limit is exceeded, the server returns HTTP 429 (Too Many Requests).

## Payload Size

Request bodies over 1MB are rejected with HTTP 400. This prevents denial-of-service via large payloads.

## Worker Name Validation

Worker names in `/trigger/task` are validated against a strict regex whitelist. Names containing path traversal characters (`../`), slashes, or special characters are rejected with HTTP 400.

## Security

- Always use HTTPS in production (put behind a reverse proxy)
- Rotate API keys regularly with `corp webhook keygen`
- Bind to `127.0.0.1` (default) unless external access is needed
- The server uses Flask; for production, deploy with a WSGI server like gunicorn
- Rate limiting is enabled by default — configure via `security:` in charter.yaml
- Payloads over 1MB are automatically rejected
