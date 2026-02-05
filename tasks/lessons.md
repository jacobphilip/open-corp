[2026-02-05] Click 8.3 CliRunner → `mix_stderr` parameter was removed. Stderr goes to `result.output` by default. Don't use `mix_stderr=False` or `result.stderr`.

[2026-02-05] APScheduler 3.x vs 4.x → 4.x has completely different async-first API. Pin `<4.0` to avoid breaking changes. Lazy-import APScheduler so the module stays importable without it installed.

[2026-02-05] TinyDB is not thread-safe → APScheduler runs tasks in a thread pool. For v0.4 this is acceptable (tasks run seconds apart), but v0.5 needs locks or a thread-safe storage layer.

[2026-02-05] Event handler isolation → Always swallow exceptions in event handlers. A broken handler must never break the emitter. Tested this explicitly in test_handler_exception_swallowed.

[2026-02-05] Workflow output injection → `{node_id.output}` substitution can inject huge strings into next node's message. Truncate node outputs to 2000 chars during storage to prevent context blowup.

[2026-02-05] Topological sort cycle detection → Use in-stack set (not just visited) to detect back edges. Simple visited-only approach misses cycles in DAGs with multiple entry points.

[2026-02-05] Test isolation for scheduler/workflow → These need respx mocking context, so fixtures live in their own test files rather than conftest.py. The event_log fixture (no HTTP) can go in conftest.
