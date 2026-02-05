# Test Plan — open-corp

Version: **0.2.0** | Total tests: **117** | Status: **All passing**

---

## Test Infrastructure

- **Framework:** pytest 9.x
- **HTTP mocking:** respx 0.22 (for httpx)
- **Async:** pytest-asyncio 1.3 (strict mode)
- **Fixtures:** `tests/conftest.py` — shared `tmp_project`, `config`, `accountant`, `router`, `hr`, `create_template`, `create_worker` fixtures
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

## test_router.py — 14 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_chat_success | Successful chat returns content, records spending |
| 2 | test_model_fallback_on_error | 503 error → falls back to next model in tier |
| 3 | test_all_models_fail_raises | All models fail → ModelUnavailable raised |
| 4 | test_budget_frozen_raises | Frozen budget → BudgetExceeded before API call |
| 5 | test_explicit_model_tried_first | Explicit model parameter takes priority |
| 6 | test_caution_prefers_cheap | CAUTION budget downgrades premium requests |
| 7 | test_stream_success | Streaming yields content chunks, final has usage, cost recorded |
| 8 | test_stream_budget_frozen | Frozen budget raises BudgetExceeded before streaming |
| 9 | test_stream_empty_content | Empty deltas skipped, final chunk still correct |
| 10 | test_stream_malformed_json | Malformed SSE lines skipped, valid chunks processed |
| 11 | test_fetch_pricing_success | Parses models endpoint, caches pricing to disk |
| 12 | test_fetch_pricing_network_error | Network error falls back to empty dict |
| 13 | test_fetch_pricing_uses_disk_cache | Pre-populated disk cache returned on network error |
| 14 | test_fetch_pricing_overwrites_cache | Fresh fetch replaces old cached data |

---

## test_knowledge.py — 23 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_short_text_no_split | Text under chunk_size returns as single chunk |
| 2 | test_empty_text | Empty/whitespace text returns empty list |
| 3 | test_paragraph_boundaries | Splits on double-newline paragraph boundaries |
| 4 | test_long_text_multiple_chunks | Long text produces multiple chunks within size limit |
| 5 | test_single_huge_paragraph | Single paragraph larger than chunk_size is split |
| 6 | test_overlap_preservation | Overlap text from previous chunk at start of next |
| 7 | test_keyword_match | Entries matching query keywords are returned |
| 8 | test_no_match_fallback | No keywords match → falls back to newest entries |
| 9 | test_budget_enforcement | Results fit within max_chars budget |
| 10 | test_multi_keyword_scoring | More keyword matches ranks higher |
| 11 | test_empty_entries | Empty entries list returns empty |
| 12 | test_zero_budget | Zero budget returns empty |
| 13 | test_empty_content | Flags entries with empty content |
| 14 | test_short_content | Flags entries with <50 chars |
| 15 | test_duplicate_content | Flags duplicate entries |
| 16 | test_repetitive_content | Flags >50% same character |
| 17 | test_clean_pass | Valid entries produce no warnings |
| 18 | test_total_size_warning | Warns when total size exceeds 500KB |
| 19 | test_empty_list | Empty list returns no warnings |
| 20 | test_load_save_roundtrip | Save then load preserves entries |
| 21 | test_load_nonexistent | Nonexistent dir returns empty KnowledgeBase |
| 22 | test_load_corrupt_json | Corrupt JSON returns empty KnowledgeBase |
| 23 | test_add_entries_appends | add_entries appends to existing entries |

---

## test_worker.py — 13 tests

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
| 9 | test_build_system_prompt_with_knowledge | Knowledge entries appear in prompt |
| 10 | test_build_system_prompt_knowledge_with_query | Search narrows knowledge with query |
| 11 | test_build_system_prompt_no_knowledge | Without knowledge_base, prompt works (backward compat) |
| 12 | test_knowledge_and_memory_budget_sharing | Both knowledge and memory fit within budget |
| 13 | test_chat_passes_query_to_prompt | User message flows as query to build_system_prompt |

---

## test_hr.py — 21 tests

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
| 9 | test_train_from_text_file | Trains from .txt file, creates knowledge entries |
| 10 | test_train_from_markdown | Trains from .md file |
| 11 | test_train_from_pdf | Trains from PDF (mocked pypdf) |
| 12 | test_train_from_document_not_found | Missing file → TrainingError |
| 13 | test_train_from_unsupported_extension | Bad extension → TrainingError |
| 14 | test_train_from_document_stores_chunks | Chunks persisted to knowledge.json |
| 15 | test_train_from_url_success | Web page training with mocked HTTP |
| 16 | test_train_from_url_not_html | Non-HTML content type → TrainingError |
| 17 | test_train_from_url_network_error | Network error → TrainingError |
| 18 | test_train_from_url_stores_chunks | URL chunks persisted |
| 19 | test_train_from_youtube_playlist | Playlist extracts video IDs, processes each |
| 20 | test_train_from_youtube_playlist_max_cap | Playlist caps at max_videos |
| 21 | test_train_from_youtube_raises_training_error | YouTube failure raises TrainingError |

---

## test_cli.py — 19 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_status_shows_project_info | exit 0, output has project name + budget |
| 2 | test_status_config_error | exit 1 on missing charter.yaml |
| 3 | test_budget_shows_report | exit 0, output has Spent/Remaining/Status |
| 4 | test_budget_config_error | exit 1 on missing charter.yaml |
| 5 | test_workers_empty | "No workers hired yet" when empty |
| 6 | test_workers_lists_hired | Shows worker name + seniority |
| 7 | test_hire_from_template | Creates worker dir, exit 0 |
| 8 | test_hire_from_scratch | Uses --scratch --role, exit 0 |
| 9 | test_hire_template_not_found | exit 1 when template missing |
| 10 | test_hire_duplicate_worker | exit 1 when worker already exists |
| 11 | test_chat_worker_not_found | exit 1, "not found" |
| 12 | test_chat_quit_command | input="quit", exit 0, "Bye" |
| 13 | test_chat_sends_message | Mocked router, response in output |
| 14 | test_train_no_source | exit 1, "Specify a training source" |
| 15 | test_train_document | --document calls train_from_document |
| 16 | test_train_url | --url calls train_from_url |
| 17 | test_knowledge_command | Shows knowledge entry summary |
| 18 | test_knowledge_search | --search filters knowledge entries |
| 19 | test_knowledge_empty | "no knowledge base entries" when empty |

---

## test_telegram_bot.py — 11 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_start_with_workers | Reply contains worker names |
| 2 | test_start_no_workers | Reply contains "No workers hired yet" |
| 3 | test_workers_lists_all | Reply contains names + seniority |
| 4 | test_workers_empty | "No workers hired yet" when empty |
| 5 | test_chat_selects_worker | Sets _user_workers, reply confirms |
| 6 | test_chat_no_args | Reply contains "Usage:" |
| 7 | test_chat_worker_not_found | Reply contains "not found" |
| 8 | test_status_shows_info | Reply contains project name + budget |
| 9 | test_budget_shows_report | Reply contains Spent/Remaining |
| 10 | test_message_no_active_worker | "No active worker" when unset |
| 11 | test_message_routes_to_worker | Patches Worker, verifies reply |

---

## Coverage Gaps (known, acceptable for v0.2)

- **YouTube training pipeline:** No automated tests for actual download/transcribe (requires yt-dlp + whisper)
- **PDF training:** Uses mocked pypdf in tests (real PDF parsing tested manually)

---

Total tests: **117** | All passing
