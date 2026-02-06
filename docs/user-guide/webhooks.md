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

## Security

- Always use HTTPS in production (put behind a reverse proxy)
- Rotate API keys regularly with `corp webhook keygen`
- Bind to `127.0.0.1` (default) unless external access is needed
- The server uses Flask; for production, deploy with a WSGI server like gunicorn
