# CLI Reference

All commands accept `--project-dir PATH` to specify the project directory. Without it, open-corp checks the active operation from the registry, then falls back to the current working directory.

Global flags:

- `--verbose / -v` — enable DEBUG-level logging (default: INFO)

## Core Commands

### `corp init`

Initialize a new project. Creates `charter.yaml`, `.env`, and project directories. Auto-registers the project in the operation registry.

### `corp status`

Show project name, owner, mission, and budget usage.

### `corp budget`

Detailed spending report: date, spent/remaining, status, token counts, breakdown by worker and model.

### `corp workers`

List all hired workers with seniority level and role.

### `corp hire <template> <name>`

Hire a new worker from a template.

Options:

- `--scratch` — create from scratch instead of copying a template
- `--role ROLE` — role when hiring from scratch (default: "general")

### `corp chat <worker>`

Interactive multi-turn chat. Type `quit` to exit. Session is summarized on exit.

### `corp train <worker>`

Train a worker from external sources.

Options:

- `--youtube URL` — YouTube video or playlist
- `--document PATH` — local file (PDF, markdown, text)
- `--url URL` — web page

### `corp knowledge <worker>`

View or search a worker's knowledge base.

Options:

- `--search QUERY` — filter entries by keyword

### `corp fire <worker>`

Fire a worker and clean up references. Removes scheduled tasks referencing the worker and warns about workflow files that reference them.

Options:

- `--yes / -y` — skip confirmation prompt

### `corp inspect [worker]`

Without args: project overview with all workers. With a worker name: detailed worker profile, skills, memory count, knowledge count, performance stats.

## Operations Management

### `corp ops create <name>`

Register a new operation.

Options:

- `--dir PATH` — use an existing directory instead of creating one

### `corp ops list`

List all registered operations. Active operation is marked with `*`.

### `corp ops switch <name>`

Set the active operation. Subsequent commands without `--project-dir` will use this project.

### `corp ops remove <name>`

Unregister an operation (does not delete files).

### `corp ops active`

Show the currently active operation and its path.

## Performance Review

### `corp review [worker] [--auto]`

Without args: team scorecard sorted by rating. With worker name: individual performance summary. With `--auto`: auto-promote/demote based on `promotion_rules` in charter.yaml.

### `corp delegate <message>`

Auto-select the best worker using TaskRouter and send a message. Selection is based on skill match (50%), performance (35%), and seniority (15%).

## Marketplace

### `corp marketplace list`

List all templates available in the configured registry.

### `corp marketplace search <query>`

Search templates by name, description, or tags.

### `corp marketplace info <name>`

Show details for a specific template.

### `corp marketplace install <name>`

Download and install a template to `templates/`.

## Housekeeping

### `corp housekeep`

Clean up old data based on retention policies configured in charter.yaml. Removes old events, spending records, workflow runs, and trims worker performance histories.

Options:

- `--dry-run` — show what would be removed without deleting

### `corp validate`

Validate project configuration and references. Checks that:

- charter.yaml exists and parses correctly
- Scheduled task worker references exist
- Workflow YAML files parse correctly

## Scheduling

### `corp schedule add <worker> <message>`

Add a scheduled task.

Options:

- `--cron EXPR` — cron expression (e.g., `*/30 * * * *`)
- `--interval SECONDS` — repeat every N seconds
- `--once DATETIME` — one-time execution (ISO format)
- `--description TEXT` — task description

### `corp schedule list`

List all scheduled tasks.

### `corp schedule remove <task_id>`

Remove a scheduled task.

## Daemon

### `corp daemon start`

Start the scheduler daemon.

Options:

- `-d, --background` — run in background (daemonize)

### `corp daemon stop`

Stop the running daemon.

### `corp daemon status`

Check if the daemon is running.

## Events

### `corp events`

Show recent events.

Options:

- `--type TYPE` — filter by event type
- `--limit N` — number of events (default: 20)

## Webhooks

### `corp webhook start`

Start the webhook HTTP server.

Options:

- `--port PORT` — port to listen on (default: 8080)
- `--host HOST` — host to bind to (default: 127.0.0.1)

### `corp webhook keygen`

Generate a random API key for webhook authentication.

## Broker

### `corp broker account`

Show paper trading account summary (cash, positions, equity, P&L).

### `corp broker positions`

Show current stock positions.

### `corp broker buy <symbol> <quantity>`

Paper buy shares.

Options:

- `--price PRICE` — price per share (uses yfinance if omitted)

### `corp broker sell <symbol> <quantity>`

Paper sell shares.

Options:

- `--price PRICE` — price per share (uses yfinance if omitted)

### `corp broker price <symbol>`

Get current price for a symbol (requires yfinance).

### `corp broker trades`

Show trade history.

Options:

- `--symbol SYMBOL` — filter by symbol
- `--limit N` — number of trades (default: 20)
