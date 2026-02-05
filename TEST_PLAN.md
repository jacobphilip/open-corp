# Test Plan — open-corp

Version: **0.1.0** | Total tests: **38** | Status: **All passing**

---

## Test Infrastructure

- **Framework:** pytest 9.x
- **HTTP mocking:** respx 0.22 (for httpx)
- **Fixtures:** `tests/conftest.py` — shared `tmp_project`, `config`, `accountant` fixtures
- **Run:** `.venv/bin/pytest tests/ -v`

---

## test_config.py — 7 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_load_valid_charter | Valid charter.yaml loads all fields correctly |
| 2 | test_missing_charter_file | Raises ConfigError when charter.yaml absent |
| 3 | test_missing_project_section | Raises ConfigError when 'project' section missing |
| 4 | test_missing_budget_section | Raises ConfigError when 'budget' section missing |
| 5 | test_missing_required_project_field | Raises ConfigError for missing required field (mission) |
| 6 | test_bad_yaml | Raises ConfigError for unparseable YAML |
| 7 | test_defaults_when_optional_sections_missing | Optional sections get sensible defaults |

---

## test_accountant.py — 9 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_initial_state_green | Fresh accountant is GREEN, $0 spent |
| 2 | test_record_call | Recording a call increases today_spent |
| 3 | test_multiple_calls_accumulate | Multiple calls sum correctly |
| 4 | test_caution_threshold | 60-80% spending → CAUTION |
| 5 | test_austerity_threshold | 80-95% spending → AUSTERITY |
| 6 | test_critical_threshold | 95-100% spending → CRITICAL |
| 7 | test_frozen_at_limit | 100% spending → BudgetExceeded raised |
| 8 | test_frozen_over_limit | Over-limit → BudgetExceeded raised |
| 9 | test_daily_report | Report contains correct breakdowns by worker/model |

---

## test_router.py — 6 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_chat_success | Successful chat returns content, records spending |
| 2 | test_model_fallback_on_error | 503 error → falls back to next model in tier |
| 3 | test_all_models_fail_raises | All models fail → ModelUnavailable raised |
| 4 | test_budget_frozen_raises | Frozen budget → BudgetExceeded before API call |
| 5 | test_explicit_model_tried_first | Explicit model parameter takes priority |
| 6 | test_caution_prefers_cheap | CAUTION budget downgrades premium requests |

---

## test_worker.py — 8 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_load_worker | Worker loads all files from directory |
| 2 | test_worker_not_found | Missing worker → WorkerNotFound raised |
| 3 | test_seniority_tier_mapping | L1-2→cheap, L3→mid, L4-5→premium |
| 4 | test_build_system_prompt | Prompt includes profile, skills, honest AI |
| 5 | test_build_system_prompt_with_memory | Prompt includes recent memory entries |
| 6 | test_update_memory | Memory appends and persists to disk |
| 7 | test_record_performance | Performance records persist to disk |
| 8 | test_chat | Chat calls router and updates memory |

---

## test_hr.py — 8 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_hire_from_template | Copies template, creates worker with memory/performance files |
| 2 | test_hire_from_template_not_found | Missing template → FileNotFoundError |
| 3 | test_hire_duplicate_worker | Duplicate name → FileExistsError |
| 4 | test_hire_from_scratch | Creates all required files with correct content |
| 5 | test_list_workers | Returns all workers with name/level/role |
| 6 | test_fire_worker | Requires confirm=True, removes directory |
| 7 | test_fire_nonexistent | Missing worker → WorkerNotFound |
| 8 | test_promote | Increments level, caps at 5 |

---

## Coverage Gaps (known, acceptable for v0.1)

- **Telegram bot:** No automated tests (requires async + bot API mocking)
- **CLI (corp.py):** No automated tests (tested manually via CLI verification)
- **YouTube training pipeline:** No automated tests (requires yt-dlp + whisper)
- **Router streaming:** No automated tests (SSE stream mocking is complex)
- **Pricing fetch:** No automated tests (external API dependency)

---

Total tests: **38** | All passing
