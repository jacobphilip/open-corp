# Roadmap — open-corp

Current version: **0.1.0**

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
- [x] Tests — 38 tests, all passing (pytest + respx)

---

## v0.2 — Worker Training & Knowledge

Status: **Planned**

- [ ] Worker training from documents (PDF, markdown, text)
- [ ] Worker training from web pages
- [ ] Knowledge base search and retrieval
- [ ] Multi-video YouTube playlist training
- [ ] Training quality validation

---

## v0.3 — Usability

Status: **Planned**

- [ ] GUI installer (one-click setup for non-technical users)
- [ ] Web dashboard for budget monitoring
- [ ] Improved error messages and onboarding
- [ ] Pre-built operation templates (Job Hunter, Research Team)

---

## v0.4 — Automation

Status: **Planned**

- [ ] Scheduled task execution (cron/systemd timers)
- [ ] Worker coordination (one worker triggers another)
- [ ] Event-driven workflows

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
