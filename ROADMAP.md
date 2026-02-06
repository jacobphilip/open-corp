# Roadmap — open-corp

Current version: **1.2.0**

---

## v0.1.0 — Core Framework

Status: **Complete**

- [x] Project scaffolding and configuration (charter.yaml, .env, pyproject.toml)
- [x] Exception hierarchy (BudgetExceeded, ModelUnavailable, WorkerNotFound, ConfigError)
- [x] Config loader (charter.yaml + .env → ProjectConfig dataclass)
- [x] Accountant — TinyDB budget tracking, 5 status levels, daily reports
- [x] Router — OpenRouter integration, tier fallback, budget-aware model selection
- [x] Worker — profile/memory/skills loading, chat, memory persistence, performance tracking
- [x] HR — hire from template/scratch, list/fire/promote, YouTube training pipeline
- [x] CLI (Click) — status, budget, workers, hire, chat, train
- [x] Telegram bot — /start, /workers, /chat, /status, /budget
- [x] Templates — researcher, content-repurposer
- [x] Tests — 71 tests, all passing (pytest + respx + pytest-asyncio)

---

## v0.2.0 — Worker Training & Knowledge

Status: **Complete**

- [x] Worker training from documents (PDF, markdown, text) via `train_from_document()`
- [x] Worker training from web pages via `train_from_url()`
- [x] Knowledge base search and retrieval (keyword matching, budget-aware)
- [x] Multi-video YouTube playlist training (up to 20 videos)
- [x] Training quality validation (empty, short, duplicate, repetitive, size limit)
- [x] Knowledge integrated into worker system prompts with query-based search
- [x] CLI: `train --document`, `train --url`, `knowledge` command with `--search`
- [x] Tests — 117 tests, all passing

---

## v0.3.0 — Usability

Status: **Complete**

- [x] `corp init` interactive project wizard (charter.yaml, .env, directories)
- [x] `corp inspect` project overview and worker detail view
- [x] Multi-turn chat with conversation history and session summaries
- [x] Improved error messages with contextual suggestions on all exceptions
- [x] 3 new templates: job-hunter, data-analyst, content-writer
- [x] Tests — 145 tests, all passing

---

## v0.4.0 — Automation

Status: **Complete**

- [x] Chat history truncation with configurable `max_history_messages` (default 50)
- [x] Event system — TinyDB-backed persistent log with in-memory pub/sub
- [x] Scheduled task execution — APScheduler daemon with cron, interval, one-time tasks
- [x] DAG workflow engine — YAML-defined workflows with topological sort, template substitution, conditions
- [x] CLI: `schedule add/list/remove`, `workflow run/list/status`, `daemon`, `events`
- [x] SchedulerError and WorkflowError exception classes
- [x] Tests — 185 tests, all passing

---

## v0.5.0 — Stability & Integrations

Status: **Complete**

- [x] Thread-safe TinyDB wrapper — singleton registry with per-path locking
- [x] Parallel workflow execution — depth-based fan-out via ThreadPoolExecutor
- [x] Daemon start/stop/status — PID file, background mode, SIGTERM handler
- [x] Flask webhook server — bearer token auth, workflow/task triggers, event emission
- [x] Paper trading broker — TinyDB ledger, position tracking, optional yfinance
- [x] Trader template and example trading workflow
- [x] BrokerError and WebhookError exceptions
- [x] CLI: `daemon start/stop/status`, `webhook start/keygen`, `broker account/positions/buy/sell/price/trades`
- [x] Tests — 252 tests, all passing

---

## v1.0.0 — Production Ready

Status: **Complete**

- [x] Multi-operation management — `~/.open-corp/` registry, `corp ops create/list/switch/remove/active`
- [x] Template marketplace — remote YAML registry, `corp marketplace list/search/info/install`
- [x] Self-optimizing operations — performance analytics, auto-promote/demote, smart task routing
- [x] Smart task routing — skill match + performance + seniority scoring, `worker: auto` in workflows
- [x] Performance review CLI — `corp review [worker] [--auto]`, `corp delegate <message>`
- [x] Full MkDocs documentation site — 14 pages with Material theme
- [x] Tests — 321 tests, all passing

---

## v1.1.0 — Operational Hardening

Status: **Complete**

- [x] Webhook bug fixes — schedule_type always "once", path traversal vulnerability
- [x] Project validation CLI — `corp validate` checks config, worker refs, workflow YAML
- [x] Structured logging — `framework/log.py` with `setup_logging()` / `get_logger()`, `--verbose` flag
- [x] Logging config — `LoggingConfig` and `RetentionConfig` dataclasses in charter.yaml
- [x] Framework log calls — router, accountant, scheduler, events, webhooks, workflow (~20 targeted calls)
- [x] Data retention — `Housekeeper` class, `corp housekeep` with `--dry-run`
- [x] Workflow timeouts — per-node `timeout` (300s default) and `retries` (0 default), workflow-level `timeout`
- [x] Worker fire with cleanup — scheduler task removal, workflow reference warnings, `corp fire` command
- [x] Tests — 388 tests, all passing

---

## v1.2.0 — Telegram Enhancement + Web Dashboard

Status: **Complete**

- [x] Telegram bot parity with v1.1 CLI — 8 new commands: /fire (inline keyboard), /review, /delegate, /events, /schedule, /workflow, /inspect, /housekeep
- [x] CallbackQueryHandler for fire confirmation with inline keyboard buttons
- [x] Local web dashboard — Flask app factory, 7 HTML pages + JSON API, read-only monitoring
- [x] Dashboard templates — Jinja2 with budget gauge, status badges, worker detail, event filtering
- [x] Dashboard CSS — minimal system-ui style with gauge bars and workflow status badges
- [x] CLI dashboard command — `corp dashboard` with `--port` and `--host` options
- [x] Package data — templates and static files included in setuptools build
- [x] Tests — 423 tests, all passing
