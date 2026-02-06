# Changelog — open-corp

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [1.3.0] — 2026-02-05

### Added
- **framework/validation.py** — Input validation module: `validate_worker_name()` (regex whitelist), `validate_path_within()` (path traversal guard), `validate_payload_size()` (1MB default), `RateLimiter` (token bucket, thread-safe, per-IP), `safe_load_json()` (corruption detection + `.corrupt` backup), `safe_write_json()` (atomic write via tempfile + rename)
- **framework/config.py** — `SecurityConfig` dataclass with `webhook_rate_limit`, `webhook_rate_burst`, `dashboard_rate_limit`, `dashboard_rate_burst`; `.env` file permission warning when group/other readable; `default_max_tokens` on `WorkerDefaults`
- **framework/log.py** — `SecretFilter(logging.Filter)` redacts API keys (`sk-or-*`, `sk-*`), Bearer tokens, and env var assignments from log output; applied automatically in `setup_logging(redact_secrets=True)`
- **framework/exceptions.py** — `ValidationError(reason, suggestion)` exception class
- **framework/dashboard.py** — Authentication via Bearer header or httponly cookie; `/login` route with `hmac.compare_digest`; rate limiting via `RateLimiter`; worker name validation
- **framework/webhooks.py** — Rate limiting per IP, payload size validation (1MB max), worker name validation in `/trigger/task`
- **framework/router.py** — Retry with exponential backoff for transient errors (429/502/503/504, `ConnectError`, `TimeoutException`); `max_retries`, `retry_base_delay`, `retry_max_delay` params; `max_tokens` support in API calls
- **tests/test_validation.py** — 35 tests for validation module
- **tests/test_integration.py** — 15 tests for concurrency, error recovery, security, and data integrity
- **tests/test_dashboard.py** — +10 auth tests (bearer, cookie, login, rate limit, httponly flag, worker name validation)
- **tests/test_router.py** — +9 retry/max_tokens tests (503, 429, timeout, 400/401 no-retry, exponential delay, max_retries=0, max_tokens payload)
- **tests/test_config.py** — +3 tests (SecurityConfig defaults, SecurityConfig from charter, .env permission warning)
- **tests/test_logging.py** — +7 tests (SecretFilter redacts API keys, bearer tokens, env vars, args; leaves normal messages; setup adds filter)
- **tests/test_webhooks.py** — +3 tests (rate limit blocks, payload size rejected, worker name validated)
- **tests/test_worker.py** — +3 tests (corrupted memory/performance loads empty, atomic write valid JSON)
- **charter.yaml** — `security:` section with rate limit defaults

### Changed
- `framework/worker.py` — JSON I/O uses `safe_load_json()` / `safe_write_json()` for corruption resilience and atomic writes
- `framework/hr.py` — `validate_worker_name()` in hire, fire, promote, demote
- `framework/scheduler.py` — `validate_worker_name()` in `add_task()`
- `scripts/corp.py` — Worker name validation in chat, fire, inspect, review; `.env` created with `chmod 600`; non-local dashboard host warning
- `scripts/telegram_bot.py` — Worker name validation in /chat, /fire, /review, /inspect
- Total test count: 423 → 509

---

## [1.2.0] — 2026-02-05

### Added
- **framework/dashboard.py** — Read-only Flask web dashboard with app factory pattern; HTML pages (home, workers, worker detail, budget, events, workflows, schedule) + JSON API (`/api/status`, `/api/budget`, `/api/workers`, `/api/events`, `/api/workflows`, `/api/schedule`)
- **framework/templates/dashboard/** — 8 Jinja2 templates (base + 7 pages + error) with budget gauge, status badges, navigation
- **framework/static/style.css** — Minimal dashboard CSS (~80 lines): system-ui font, gauge bars, status badges, responsive tables
- **scripts/telegram_bot.py** — 8 new command handlers: `/fire` (inline keyboard confirm), `/review`, `/delegate`, `/events`, `/schedule`, `/workflow`, `/inspect`, `/housekeep`; `CallbackQueryHandler` for fire confirmation
- **scripts/corp.py** — New `dashboard` command with `--port` and `--host` options
- **tests/test_dashboard.py** — 20 tests for dashboard HTML pages and JSON API endpoints
- **tests/test_telegram_bot.py** — +15 tests for new bot commands (fire with callback, review, delegate, events, schedule, workflow, inspect)

### Changed
- `pyproject.toml` — Added `[tool.setuptools.package-data]` for dashboard templates and static files
- Total test count: 388 → 423

---

## [1.1.0] — 2026-02-05

### Added
- **framework/log.py** — Structured logging with `setup_logging()` and `get_logger()` using stdlib logging (no new deps)
- **framework/housekeeping.py** — `Housekeeper` class for data retention: clean events, spending, workflows by age; trim performance records
- **framework/config.py** — `LoggingConfig` and `RetentionConfig` dataclasses with charter.yaml parsing (optional sections, sensible defaults)
- **scripts/corp.py** — New CLI commands: `fire`, `housekeep` (with `--dry-run`), `validate`; `--verbose/-v` global flag
- **Workflow timeouts** — Per-node `timeout` (default 300s) and `retries` (default 0) fields; workflow-level `timeout` (0 = unlimited)
- **Worker fire with cleanup** — `HR.fire()` accepts optional `scheduler` for task cleanup, scans workflows for references, returns `{removed_tasks, warnings}`
- **Logging across framework** — Targeted log calls in router, accountant, scheduler, events, webhooks, workflow (2-3 per module, ~20 total)
- **tests/test_logging.py** — 8 tests for logging module
- **tests/test_housekeeping.py** — 14 tests for data retention
- **tests/test_workflow.py** — +13 tests for timeouts and retries
- **tests/test_hr.py** — +7 tests for enhanced fire with cleanup
- **tests/test_cli.py** — +11 tests for fire, housekeep, validate, verbose
- **tests/test_config.py** — +7 tests for LoggingConfig and RetentionConfig
- **tests/test_webhooks.py** — +8 tests for schedule_type fix and path traversal

### Fixed
- **Webhook schedule_type bug** — `schedule_type` was always `"once"` regardless of `run_at`; `schedule_value` defaulted to `"1970-01-01T00:00:00"` instead of current UTC time
- **Webhook path traversal** — Workflow file paths are now resolved and validated to be within the project directory

### Changed
- `HR.fire()` returns `dict` with `removed_tasks` and `warnings` instead of `None` (backward-compatible — no callers depended on return value)
- Total test count: 321 → 388

---

## [1.0.0] — 2026-02-05

### Added
- **Multi-Operation Management** — `~/.open-corp/` registry for managing multiple projects; `corp ops create/list/switch/remove/active` commands
- **Template Marketplace** — httpx client for fetching/searching/installing templates from a remote YAML registry; `corp marketplace list/search/info/install` commands
- **Self-Optimizing Operations** — `Worker.performance_summary()` aggregation, `HR.demote()`/`team_review()`/`auto_review()` with configurable `PromotionRules`
- **Smart Task Routing** — `TaskRouter.select_worker()` scoring (skill match 50% + performance 35% + seniority 15%); `worker: auto` in workflow nodes
- **framework/registry.py** — `OperationRegistry` class with JSON-backed name→path mapping
- **framework/task_router.py** — `TaskRouter` class for skill/performance/seniority-based worker selection
- **framework/marketplace.py** — `Marketplace` class for remote template registry browsing and installation
- **framework/config.py** — `PromotionRules` dataclass, `marketplace_url` field on `ProjectConfig`
- **framework/exceptions.py** — `RegistryError` and `MarketplaceError` exception classes
- **scripts/corp.py** — New CLI commands: `ops create/list/switch/remove/active`, `review [worker] [--auto]`, `delegate <message>`, `marketplace list/search/info/install`
- **docs/** — Full MkDocs documentation site with 14 pages (quickstart, CLI reference, configuration, architecture, API, migration, troubleshooting, contributing)
- **mkdocs.yml** — MkDocs Material theme configuration
- **tests/test_registry.py** — 15 tests for OperationRegistry
- **tests/test_task_router.py** — 8 tests for TaskRouter
- **tests/test_marketplace.py** — 12 tests for Marketplace
- **tests/test_exceptions.py** — +2 tests for RegistryError and MarketplaceError
- **tests/test_config.py** — +2 tests for PromotionRules and marketplace_url parsing
- **tests/test_worker.py** — +6 tests for performance_summary
- **tests/test_hr.py** — +8 tests for demote/team_review/auto_review
- **tests/test_cli.py** — +16 tests for ops/marketplace/review/delegate commands
- **pyproject.toml** — `docs` optional dependency group (mkdocs, mkdocs-material, mkdocstrings)

### Changed
- `_load_project()` now checks active operation from registry before falling back to cwd (backward-compatible)
- `corp init` auto-registers new projects in the operation registry
- `framework/workflow.py` supports `worker: auto` in node definitions for smart task routing
- Total test count: 252 → 321

---

## [0.5.0] — 2026-02-05

### Added
- **framework/db.py** — Thread-safe TinyDB wrapper with singleton registry and per-path `threading.Lock`
- **framework/webhooks.py** — Flask webhook server with bearer token auth (`/health`, `/trigger/workflow`, `/trigger/task`, `/events`)
- **framework/broker.py** — Paper trading broker with TinyDB ledger, position tracking, and optional yfinance price fetching
- **framework/exceptions.py** — `BrokerError` and `WebhookError` exception classes
- **framework/workflow.py** — Parallel workflow execution via `ThreadPoolExecutor` with depth-based node grouping (`_compute_depths`)
- **scripts/corp.py** — New CLI commands: `daemon start/stop/status`, `webhook start/keygen`, `broker account/positions/buy/sell/price/trades`
- **templates/trader/** — Trading specialist template (risk management, position sizing)
- **workflows/example_trading.yaml** — Diamond DAG demonstrating parallel scan + recommendation
- **tests/test_db.py** — 12 tests for thread-safe wrapper
- **tests/test_webhooks.py** — 14 tests for webhook server
- **tests/test_broker.py** — 16 tests for paper trading
- **tests/test_accountant.py** — +3 thread-safety tests
- **tests/test_events.py** — +3 thread-safety tests
- **tests/test_scheduler.py** — +3 thread-safety tests
- **tests/test_workflow.py** — +7 parallel execution and depth computation tests
- **tests/test_cli.py** — +7 daemon/webhook/broker CLI tests
- **tests/test_exceptions.py** — +2 tests for BrokerError and WebhookError
- **pyproject.toml** — `flask>=3.0` added to dependencies, `yfinance>=0.2` as optional broker dependency
- **.env.example** — `WEBHOOK_API_KEY` added

### Changed
- **Breaking:** `corp daemon` is now `corp daemon start` (group with start/stop/status subcommands)
- All TinyDB usage now thread-safe via `framework.db.get_db()` with per-path locks
- Accountant, EventLog, Scheduler, WorkflowEngine migrated from direct `TinyDB()` to `get_db()`
- Workflow execution is parallel by depth layer (independent nodes run concurrently)
- Daemon supports PID file, background mode (`-d`), SIGTERM handler, and `stop`/`status` subcommands
- Total test count: 185 → 252

---

## [0.4.0] — 2026-02-05

### Added
- **framework/config.py** — `max_history_messages` field on WorkerDefaults (default 50) for chat history truncation
- **framework/worker.py** — Automatic chat history truncation in `chat()` based on `max_history_messages`
- **framework/exceptions.py** — `SchedulerError` and `WorkflowError` exception classes with suggestion support
- **framework/events.py** — Event system with TinyDB-backed persistent log and in-memory pub/sub (`EventLog`, `Event`)
- **framework/scheduler.py** — Scheduled task execution with APScheduler (`Scheduler`, `ScheduledTask`) supporting cron, interval, and one-time tasks
- **framework/workflow.py** — DAG workflow engine with YAML definitions, topological sort, template substitution, and condition checking (`WorkflowEngine`, `Workflow`, `WorkflowNode`)
- **scripts/corp.py** — New CLI commands: `schedule add/list/remove`, `workflow run/list/status`, `daemon`, `events`
- **tests/test_events.py** — 10 tests for event system
- **tests/test_scheduler.py** — 10 tests for scheduler
- **tests/test_workflow.py** — 14 tests for workflow engine
- **tests/test_config.py** — +1 test for max_history_messages parsing
- **tests/test_exceptions.py** — +2 tests for SchedulerError and WorkflowError
- **tests/test_worker.py** — +3 tests for chat history truncation
- **pyproject.toml** — `apscheduler>=3.10,<4.0` added to dependencies

### Changed
- Worker chat history is automatically truncated to `max_history_messages` (configurable in charter.yaml)
- Total test count: 145 → 185

---

## [0.3.0] — 2026-02-05

### Added
- **framework/exceptions.py** — `suggestion` field on all 5 exception classes with default suggestions for WorkerNotFound, BudgetExceeded, ModelUnavailable
- **framework/config.py** — Contextual suggestions passed to ConfigError raises (missing charter, missing fields)
- **framework/worker.py** — Multi-turn `chat()` with conversation history, `summarize_session()` for auto-summarizing chat sessions to worker memory
- **scripts/corp.py** — `init` command (interactive project wizard), `inspect` command (project/worker detail view), multi-turn chat with session summaries
- **templates/job-hunter/** — Career assistant template (resume, cover letters, interview prep)
- **templates/data-analyst/** — Data analysis template (statistics, reports, hypothesis testing)
- **templates/content-writer/** — Content writing template (blog, social, SEO, email)
- **tests/test_exceptions.py** — 3 tests for suggestion field and backward compatibility
- **tests/test_templates.py** — 5 tests for template file validation and hiring
- **tests/test_worker.py** — +8 multi-turn chat and session summary tests
- **tests/test_cli.py** — +12 tests for init, inspect, and updated chat commands

### Changed
- **Breaking:** `Worker.chat()` returns `tuple[str, list[dict]]` instead of `str` (response text + conversation history)
- **scripts/telegram_bot.py** — Updated to unpack `chat()` tuple return
- **scripts/corp.py** — Chat command now maintains conversation history across messages and summarizes on exit
- **README.md** — Claude Code repositioned as optional; CLI is the primary interface; only requirement is OpenRouter + Python

---

## [0.2.0] — 2026-02-05

### Added
- **framework/knowledge.py** — KnowledgeBase module: chunking, keyword search, validation, persistent storage
- **framework/exceptions.py** — TrainingError exception for training pipeline failures
- **framework/worker.py** — Knowledge integration into system prompts with query-based search and 60/40 knowledge/memory budget split
- **framework/hr.py** — `train_from_document()` for PDF/markdown/text files, `train_from_url()` for web pages, YouTube playlist support
- **scripts/corp.py** — `--document` and `--url` options on train command, new `knowledge` command with `--search`
- **tests/test_knowledge.py** — 23 tests for chunking, search, validation, KnowledgeBase CRUD
- **tests/test_worker.py** — +5 knowledge integration tests (prompt with/without knowledge, query search, budget sharing, chat passthrough)
- **tests/test_hr.py** — +13 training tests (document: 6, web: 4, playlist: 3)
- **tests/test_cli.py** — +5 CLI tests (train --document, train --url, knowledge command, knowledge --search, empty knowledge)
- **pyproject.toml** — pypdf and html2text added to [training] optional dependencies

### Changed
- `train_from_youtube()` now raises `TrainingError` instead of returning error strings
- `train_from_youtube()` uses chunked KnowledgeBase storage instead of raw JSON
- `build_system_prompt()` accepts optional `query` parameter for knowledge search
- `chat()` passes user message as query to `build_system_prompt()` for relevant knowledge retrieval

---

## [0.1.0] — 2026-02-05

### Added
- **framework/exceptions.py** — Shared exceptions: BudgetExceeded, ModelUnavailable, WorkerNotFound, ConfigError
- **framework/config.py** — ProjectConfig loader with dataclasses, loads charter.yaml + .env
- **framework/accountant.py** — Budget guardrail with TinyDB; tracks spending, enforces daily limits, 5 status levels (GREEN → FROZEN)
- **framework/router.py** — OpenRouter integration with tier-based model selection, automatic fallback (premium → mid → cheap), budget-aware downgrading
- **framework/worker.py** — Worker class with profile/memory/skills loading, system prompt construction, chat, memory persistence, performance tracking
- **framework/hr.py** — HR class: hire from template, hire from scratch, list/fire/promote workers, YouTube training pipeline (optional deps)
- **scripts/corp.py** — Click CLI with commands: status, budget, workers, hire, chat, train
- **scripts/telegram_bot.py** — Async Telegram bot (python-telegram-bot v21) with /start, /workers, /chat, /status, /budget
- **templates/researcher/** — Research specialist template (profile, skills, config)
- **templates/content-repurposer/** — Content transformation specialist template (profile, skills, config)
- **tests/** — 38 tests across 5 modules (config, accountant, router, worker, hr) using pytest + respx
- **pyproject.toml** — Editable install with [dev] and [training] optional dependencies
- **requirements.txt** — Runtime dependencies
- **.env.example** — Template for OPENROUTER_API_KEY and TELEGRAM_BOT_TOKEN
- **charter.yaml** — Project configuration template with budget, model tiers, worker defaults
- **CLAUDE.md** — LLM operating instructions for agentic workflow
- **README.md** — Project documentation

### Not Yet Implemented
- Trading desk example (deferred to future version)
- Board of Advisors integration (framework supports config, not yet wired)
- GUI installer / dashboard
- Automated scheduling (systemd timers)
