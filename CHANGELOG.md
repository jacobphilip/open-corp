# Changelog — open-corp

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
