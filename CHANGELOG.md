# Changelog — open-corp

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
