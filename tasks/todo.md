## In Progress


## Backlog
- [ ] Thread-safe TinyDB access for scheduler [v0.5]
- [ ] Parallel workflow fan-out (threaded node execution) [v0.5]
- [ ] Daemon systemd/nohup support [v0.5]
- [ ] Board of Advisors wiring (Grok, ChatGPT, Claude) [v0.5]
- [ ] Webhook endpoints for external triggers [v0.5]

## Done

### v0.4 — Automation
- [x] Add `max_history_messages` to WorkerDefaults + chat truncation ✓ verified
- [x] Add SchedulerError and WorkflowError exceptions ✓ verified
- [x] Create event system (framework/events.py) — TinyDB log + pub/sub ✓ verified
- [x] Create scheduler (framework/scheduler.py) — APScheduler wrapper ✓ verified
- [x] Create workflow engine (framework/workflow.py) — DAG executor ✓ verified
- [x] Add CLI commands: schedule, workflow, daemon, events ✓ verified
- [x] Add 40 new tests (10 events, 10 scheduler, 14 workflow, 3 truncation, 2 exceptions, 1 config) ✓ verified
- [x] Update docs: CHANGELOG, ROADMAP, README, TEST_PLAN, pyproject.toml ✓ verified

### v0.3 — Usability
- [x] Add `corp init` interactive project wizard ✓ verified
- [x] Add `corp inspect` project/worker detail view ✓ verified
- [x] Add multi-turn chat with session summaries ✓ verified
- [x] Add suggestion field to all exceptions ✓ verified
- [x] Add 3 new templates: job-hunter, data-analyst, content-writer ✓ verified

### v0.2 — Worker Training & Knowledge
- [x] Add knowledge base module with chunking and search ✓ verified
- [x] Add document/web/YouTube training pipelines ✓ verified
- [x] Integrate knowledge into worker system prompts ✓ verified

### v0.1 — Foundation
- [x] Add `asyncio_mode = "strict"` to pyproject.toml ✓ verified
- [x] Add shared fixtures (router, hr, create_template, create_worker) to conftest.py ✓ verified
- [x] Add 8 router tests (4 streaming, 4 pricing) to test_router.py ✓ verified
- [x] Create test_cli.py with 14 CLI tests via CliRunner ✓ verified
- [x] Create test_telegram_bot.py with 11 bot handler tests ✓ verified
- [x] Update TEST_PLAN.md with new test counts and sections ✓ verified
