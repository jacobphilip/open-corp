# Architecture

## Component Diagram

```
                    ┌─────────────────────┐
                    │   CLI (corp.py)      │
                    │   Telegram Bot       │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐  ┌─────▼─────┐  ┌──────▼──────┐
     │  HR Manager   │  │  Worker   │  │  Workflow   │
     │  hire/fire/   │  │  chat/    │  │  Engine     │
     │  promote/     │  │  memory/  │  │  DAG exec   │
     │  demote/      │  │  perf     │  │             │
     │  auto_review  │  │           │  │             │
     └───────┬───────┘  └─────┬─────┘  └──────┬──────┘
             │                │                │
             │         ┌──────▼──────┐         │
             │         │   Router    │         │
             │         │ tier-based  │         │
             │         │ model sel.  │         │
             │         └──────┬──────┘         │
             │                │                │
             │         ┌──────▼──────┐         │
             │         │ Accountant  │         │
             │         │ budget ctrl │         │
             │         └──────┬──────┘         │
             │                │                │
             └────────────────┼────────────────┘
                              │
                       ┌──────▼──────┐
                       │   Config    │
                       │ charter.yaml│
                       └──────┬──────┘
                              │
                       ┌──────▼──────┐
                       │ Exceptions  │
                       └─────────────┘
```

## Dependency Chain

```
exceptions → config → accountant → router → worker → hr → CLI
                  ↘ db → events/scheduler/workflow
                  ↘ webhooks/broker → CLI
                  ↘ registry → CLI
                  ↘ marketplace → CLI
                  ↘ task_router → workflow/CLI
```

## Design Decisions

### Dataclasses over Pydantic

All configuration and data structures use Python dataclasses. This avoids adding Pydantic as a dependency and keeps the framework lightweight.

### Dependency Injection

Components receive their dependencies through constructors rather than using singletons. The only singleton is the TinyDB registry in `framework.db`, which ensures thread-safe access.

### Thread Safety

All TinyDB operations are protected by `threading.Lock`. The `get_db()` function returns both a database instance and its associated lock. Workflows execute nodes in parallel using `ThreadPoolExecutor`.

### File-Based State

All state (worker memory, performance, knowledge, budget logs, workflow runs) is stored as JSON/YAML files in the project directory. No external database required.

### Budget as Guardrail

The Accountant runs before every API call and cannot be bypassed. It tracks costs per call and enforces daily limits with graduated threshold responses.

### Tier-Based Routing

Models are organized into tiers (cheap, mid, premium). The router tries models within a tier in order, falling back to cheaper tiers under budget pressure.

### Worker Seniority

Worker level (1-5) maps to model tier access. Higher-level workers get access to more capable (and expensive) models. Performance-based auto-promotion/demotion adjusts levels over time.

## Module Reference

| Module | Responsibility |
|--------|---------------|
| `exceptions.py` | Custom exception types with suggestions |
| `config.py` | charter.yaml parsing, dataclass configs |
| `db.py` | Thread-safe TinyDB registry |
| `accountant.py` | Budget tracking and enforcement |
| `router.py` | Model selection and API calls |
| `knowledge.py` | Knowledge base storage and search |
| `worker.py` | Worker personality, chat, memory, performance |
| `hr.py` | Hire, fire, promote, demote, train, review |
| `task_router.py` | Skill-based worker selection for tasks |
| `events.py` | Event logging and querying |
| `scheduler.py` | APScheduler task scheduling |
| `workflow.py` | DAG workflow engine with parallel execution |
| `webhooks.py` | Flask webhook HTTP server |
| `broker.py` | Paper trading broker |
| `registry.py` | Multi-operation project registry |
| `marketplace.py` | Remote template marketplace client |
