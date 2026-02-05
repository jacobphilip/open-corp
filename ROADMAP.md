# Roadmap — open-corp

Current version: **0.3.0**

---

## v0.1.0 — Core Framework (current)

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

## v0.4 — Automation

Status: **Planned**

- [ ] Scheduled task execution (cron/systemd timers)
- [ ] Worker coordination (one worker triggers another)
- [ ] Event-driven workflows
- [ ] Chat history truncation for long conversations

---

## v0.5 — Integrations

Status: **Planned**

- [ ] Board of Advisors wiring (Grok, ChatGPT, Claude direct API)
- [ ] Live broker integration (Interactive Brokers) for trading example
- [ ] Webhook endpoints for external triggers

---

## v1.0 — Production Ready

Status: **Planned**

- [ ] Multi-operation management
- [ ] Community worker marketplace
- [ ] Self-optimizing operations (workers learn from performance data)
- [ ] Comprehensive documentation and tutorials
