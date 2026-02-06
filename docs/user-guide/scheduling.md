# Scheduling

Schedule recurring or one-time tasks for workers.

## Adding Tasks

```bash
# Every 30 minutes
corp schedule add alice "Check for updates" --cron "*/30 * * * *"

# Every 3600 seconds (1 hour)
corp schedule add bob "Generate daily report" --interval 3600

# One-time at a specific datetime
corp schedule add carol "Send reminder" --once "2026-03-01T09:00:00"
```

## Managing Tasks

```bash
# List all scheduled tasks
corp schedule list

# Remove a task
corp schedule remove <task_id>
```

## Daemon

The scheduler daemon runs tasks in the background.

### Start

```bash
# Foreground (Ctrl+C to stop)
corp daemon start

# Background (daemonized)
corp daemon start -d
```

### Stop

```bash
corp daemon stop
```

### Check Status

```bash
corp daemon status
```

The daemon writes its PID to `data/daemon.pid`. If the daemon crashes, the stale PID file is automatically cleaned up on the next status check.

## Cron Expressions

Standard 5-field cron syntax:

| Field | Values |
|-------|--------|
| Minute | 0-59 |
| Hour | 0-23 |
| Day of month | 1-31 |
| Month | 1-12 |
| Day of week | 0-6 (0=Sunday) |

Examples:

- `*/5 * * * *` — every 5 minutes
- `0 9 * * 1-5` — 9 AM on weekdays
- `0 0 1 * *` — midnight on the 1st of each month

## Requirements

Scheduling requires APScheduler (`apscheduler>=3.10,<4.0`), which is included in the core dependencies.
