# Test Plan — open-corp

Version: **1.1.0** | Total tests: **388** | Status: **All passing**

---

## Test Infrastructure

- **Framework:** pytest 9.x
- **HTTP mocking:** respx 0.22 (for httpx)
- **Async:** pytest-asyncio 1.3 (strict mode)
- **Fixtures:** `tests/conftest.py` — shared `tmp_project`, `config`, `accountant`, `router`, `hr`, `event_log`, `create_template`, `create_worker` fixtures
- **Run:** `.venv/bin/pytest tests/ -v`

---

## test_config.py — 17 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_load_valid_charter | Valid charter.yaml loads all fields correctly |
| 2 | test_missing_charter_file | Raises ConfigError when charter.yaml absent |
| 3 | test_missing_project_section | Raises ConfigError when 'project' section missing |
| 4 | test_missing_budget_section | Raises ConfigError when 'budget' section missing |
| 5 | test_missing_required_project_field | Raises ConfigError for missing required field (mission) |
| 6 | test_bad_yaml | Raises ConfigError for unparseable YAML |
| 7 | test_defaults_when_optional_sections_missing | Optional sections get sensible defaults |
| 8 | test_max_history_messages_from_charter | max_history_messages parsed from charter.yaml |
| 9 | test_promotion_rules_from_charter | PromotionRules parsed from charter.yaml |
| 10 | test_marketplace_url_from_charter | marketplace.registry_url parsed from charter.yaml |
| 11 | test_logging_config_defaults | LoggingConfig() default values (INFO, empty file) |
| 12 | test_logging_config_from_charter | Logging section parsed from charter.yaml |
| 13 | test_retention_config_defaults | RetentionConfig() defaults (90 days, 100 perf max) |
| 14 | test_retention_config_from_charter | Retention section parsed from charter.yaml |
| 15 | test_logging_config_dataclass_defaults | LoggingConfig default field values |
| 16 | test_retention_config_dataclass_defaults | RetentionConfig default field values |
| 17 | test_logging_config_custom_values | LoggingConfig with custom level and file |

---

## test_accountant.py — 12 tests

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
| 10 | test_concurrent_writes | 10 threads recording calls — no corruption |
| 11 | test_concurrent_reads_during_writes | Readers get consistent data during writes |
| 12 | test_lock_prevents_corruption | After concurrent ops, call count matches expected |

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

## test_exceptions.py — 9 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_config_error_with_suggestion | Suggestion text appears in str() output |
| 2 | test_worker_not_found_has_default_suggestion | Default suggestion present |
| 3 | test_exceptions_backward_compat | All exceptions work without explicit suggestion |
| 4 | test_scheduler_error | SchedulerError fields and string output |
| 5 | test_workflow_error | WorkflowError with/without node and suggestion |
| 6 | test_broker_error | BrokerError reason and suggestion |
| 7 | test_webhook_error | WebhookError reason and suggestion |
| 8 | test_registry_error | RegistryError reason and suggestion |
| 9 | test_marketplace_error | MarketplaceError reason and suggestion |

---

## test_templates.py — 5 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_all_templates_have_required_files | All template dirs have profile.md, skills.yaml, config.yaml |
| 2 | test_template_config_valid_yaml | config.yaml parses, has "level" |
| 3 | test_template_skills_valid_yaml | skills.yaml parses, has "role" and "skills" |
| 4 | test_template_profile_nonempty | profile.md is non-empty |
| 5 | test_hire_from_each_template | HR can hire from every template (including trader) |

---

## test_worker.py — 30 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_load_worker | Worker loads all files from directory |
| 2 | test_worker_not_found | Missing worker → WorkerNotFound raised |
| 3 | test_seniority_tier_mapping | L1-2→cheap, L3→mid, L4-5→premium |
| 4 | test_build_system_prompt | Prompt includes profile, skills, honest AI |
| 5 | test_build_system_prompt_with_memory | Prompt includes recent memory entries |
| 6 | test_update_memory | Memory appends and persists to disk |
| 7 | test_record_performance | Performance records persist to disk |
| 8 | test_chat | Chat calls router, returns tuple, updates memory |
| 9 | test_build_system_prompt_with_knowledge | Knowledge entries appear in prompt |
| 10 | test_build_system_prompt_knowledge_with_query | Search narrows knowledge with query |
| 11 | test_build_system_prompt_no_knowledge | Without knowledge_base, prompt works (backward compat) |
| 12 | test_knowledge_and_memory_budget_sharing | Both knowledge and memory fit within budget |
| 13 | test_chat_passes_query_to_prompt | User message flows as query to build_system_prompt |
| 14 | test_performance_summary_empty | All zeros when no data |
| 15 | test_performance_summary_rated | Correct avg_rating |
| 16 | test_performance_summary_success_rate | success count / total |
| 17 | test_performance_summary_trend | Second half vs first half |
| 18 | test_performance_summary_unrated | rating=None excluded from avg |
| 19 | test_performance_summary_few_tasks_no_trend | Trend=0 with <4 rated |
| 20 | test_chat_history_truncation | History exceeding max truncated to most recent |
| 21 | test_chat_history_truncation_default | Default 50 works without truncation |
| 22 | test_chat_truncation_returned_history | Returned history reflects truncation + new exchange |
| 23 | test_chat_returns_tuple | chat() returns (str, list) |
| 24 | test_chat_with_history | History included in API messages |
| 25 | test_chat_history_accumulates | Two calls → 4-entry history |
| 26 | test_chat_without_history_backward_compat | history=None works |
| 27 | test_summarize_session | Summary returned from API call |
| 28 | test_summarize_session_empty_history | Empty → returns "" |
| 29 | test_summarize_session_records_memory | Memory entry type "session_summary" |
| 30 | test_summarize_session_api_call | Router called with conversation |

---

## test_hr.py — 36 tests

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
| 9 | test_demote_success | Level decremented |
| 10 | test_demote_minimum_level | Level stays at 1 |
| 11 | test_demote_worker_not_found | WorkerNotFound raised |
| 12 | test_team_review_ranked | Workers sorted by avg_rating desc |
| 13 | test_team_review_empty | Empty list when no workers |
| 14 | test_auto_review_promotes | High performer promoted |
| 15 | test_auto_review_demotes | Low performer demoted |
| 16 | test_auto_review_skips_few_tasks | Worker with too few tasks skipped |
| 17 | test_train_from_text_file | Trains from .txt file, creates knowledge entries |
| 18 | test_train_from_markdown | Trains from .md file |
| 19 | test_train_from_pdf | Trains from PDF (mocked pypdf) |
| 20 | test_train_from_document_not_found | Missing file → TrainingError |
| 21 | test_train_from_unsupported_extension | Bad extension → TrainingError |
| 22 | test_train_from_document_stores_chunks | Chunks persisted to knowledge.json |
| 23 | test_train_from_url_success | Web page training with mocked HTTP |
| 24 | test_train_from_url_not_html | Non-HTML content type → TrainingError |
| 25 | test_train_from_url_network_error | Network error → TrainingError |
| 26 | test_train_from_url_stores_chunks | URL chunks persisted |
| 27 | test_train_from_youtube_playlist | Playlist extracts video IDs, processes each |
| 28 | test_train_from_youtube_playlist_max_cap | Playlist caps at max_videos |
| 29 | test_train_from_youtube_raises_training_error | YouTube failure raises TrainingError |
| 30 | test_fire_removes_scheduled_tasks | Tasks for fired worker removed from scheduler |
| 31 | test_fire_keeps_other_worker_tasks | Other workers' tasks untouched |
| 32 | test_fire_warns_about_workflows | Warnings include workflow file references |
| 33 | test_fire_no_scheduler | Works without scheduler (backward compat) |
| 34 | test_fire_returns_result_dict | Return is dict with expected keys |
| 35 | test_fire_nonexistent_worker_cleanup | WorkerNotFound raised with cleanup args |
| 36 | test_fire_requires_confirm_cleanup | ValueError without confirm=True |

---

## test_cli.py — 65 tests

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
| 13 | test_chat_sends_message | Mocked router, response + summary in output |
| 14 | test_train_no_source | exit 1, "Specify a training source" |
| 15 | test_train_document | --document calls train_from_document |
| 16 | test_train_url | --url calls train_from_url |
| 17 | test_knowledge_command | Shows knowledge entry summary |
| 18 | test_knowledge_search | --search filters knowledge entries |
| 19 | test_knowledge_empty | "no knowledge base entries" when empty |
| 20 | test_init_creates_charter_and_env | All inputs → files created with correct values |
| 21 | test_init_creates_directories | workers/, templates/, data/ exist |
| 22 | test_init_warns_on_existing_charter | input "n" → abort |
| 23 | test_init_overwrites_on_confirm | input "y" → overwrite |
| 24 | test_init_validates_budget | Negative then valid → prompt repeats |
| 25 | test_inspect_project_overview | No args → project + budget + workers |
| 26 | test_inspect_project_no_workers | "none" shown |
| 27 | test_inspect_worker_detail | Profile + skills + counts |
| 28 | test_inspect_worker_not_found | exit 1 |
| 29 | test_chat_multi_turn_history | Two messages, 3 API calls (2 chat + 1 summary) |
| 30 | test_chat_summarizes_on_quit | "Session summary saved" in output |
| 31 | test_chat_summary_failure_graceful | API error → fallback message |
| 32 | test_marketplace_list | Lists templates from registry |
| 33 | test_marketplace_search | Searches templates |
| 34 | test_marketplace_info | Shows template details |
| 35 | test_marketplace_install | Installs template files |
| 36 | test_review_team | Team scorecard shows workers |
| 37 | test_review_single_worker | Individual performance summary |
| 38 | test_review_auto | --auto runs auto_review |
| 39 | test_delegate | Auto-selects worker and chats |
| 40 | test_ops_list_empty | No operations registered |
| 41 | test_ops_create_and_list | Create shows in list |
| 42 | test_ops_switch | Sets active operation |
| 43 | test_ops_active | Shows current active |
| 44 | test_ops_remove | Unregisters operation |
| 45 | test_ops_switch_unknown | Error for unknown name |
| 46 | test_ops_remove_unknown | Error for unknown name |
| 47 | test_init_auto_registers | corp init adds to registry |
| 48 | test_daemon_status_not_running | "not running" when no PID file |
| 49 | test_daemon_stop_not_running | exit 1 when not running |
| 50 | test_daemon_start_already_running | exit 1 when PID file with live process |
| 51 | test_webhook_keygen | Outputs a key |
| 52 | test_webhook_start_missing_key | exit 1 without WEBHOOK_API_KEY |
| 53 | test_broker_account | Shows cash, equity, P&L |
| 54 | test_broker_buy_sell | Paper trade round trip |
| 55 | test_fire_command_success | Worker removed, success message |
| 56 | test_fire_command_with_yes | -y skips confirmation prompt |
| 57 | test_fire_command_nonexistent | Error message, exit code 1 |
| 58 | test_fire_command_shows_task_count | Shows removed tasks count |
| 59 | test_fire_command_shows_warnings | Shows workflow warnings |
| 60 | test_fire_command_aborted | User declines, worker still exists |
| 61 | test_fire_command_no_workers | Error when worker not found |
| 62 | test_cli_verbose_flag | --verbose sets DEBUG level |
| 63 | test_cli_validate_success | Valid project passes validation |
| 64 | test_cli_validate_missing_charter | Missing charter shows error |
| 65 | test_cli_validate_checks_workers | Orphaned task references flagged |

---

## test_events.py — 13 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_event_auto_timestamp | Empty timestamp auto-filled |
| 2 | test_event_explicit_timestamp | Explicit timestamp preserved |
| 3 | test_emit_persists | Event found in TinyDB after emit |
| 4 | test_emit_dispatches_handler | Handler called with correct Event |
| 5 | test_handler_exception_swallowed | Bad handler doesn't prevent persistence |
| 6 | test_wildcard_handler | "*" handler receives all event types |
| 7 | test_off_removes_handler | Removed handler not called |
| 8 | test_query_by_type | Filter by event type |
| 9 | test_query_by_source | Filter by source |
| 10 | test_query_limit | Limit caps results, newest first |
| 11 | test_concurrent_emits | 10 threads emitting — no corruption |
| 12 | test_concurrent_reads_during_emits | Readers consistent during writes |
| 13 | test_lock_prevents_corruption | Event count matches after concurrent ops |

---

## test_scheduler.py — 13 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_add_task | Task persisted to TinyDB with ID |
| 2 | test_add_task_invalid_type | Invalid schedule_type → SchedulerError |
| 3 | test_add_task_worker_not_found | Missing worker → SchedulerError |
| 4 | test_remove_task | Task removed from TinyDB |
| 5 | test_remove_task_not_found | Missing task_id → SchedulerError |
| 6 | test_list_tasks | Returns all tasks |
| 7 | test_get_task | Returns single task by ID |
| 8 | test_execute_task | Mocked router, response returned + events emitted |
| 9 | test_execute_task_failure | Chat error → task.failed event, returns None |
| 10 | test_execute_task_not_found | Missing task → returns None |
| 11 | test_concurrent_writes | 10 threads adding tasks — no corruption |
| 12 | test_concurrent_reads_during_writes | Readers consistent during writes |
| 13 | test_lock_prevents_corruption | Task count matches after concurrent ops |

---

## test_workflow.py — 34 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_load_workflow_yaml | Valid YAML → Workflow dataclass |
| 2 | test_load_workflow_missing_file | Missing file → WorkflowError |
| 3 | test_load_workflow_no_nodes | Empty nodes → WorkflowError |
| 4 | test_load_workflow_missing_worker | Node without worker → WorkflowError |
| 5 | test_topological_sort_linear | A→B→C sorts correctly |
| 6 | test_topological_sort_diamond | Fan-out/fan-in (A→B,C→D) |
| 7 | test_topological_sort_cycle | Cycle → WorkflowError |
| 8 | test_substitute_outputs | `{a.output}` replaced correctly |
| 9 | test_check_condition_success | All deps completed → True |
| 10 | test_check_condition_contains | Keyword in output → True |
| 11 | test_run_simple_workflow | Two nodes, mocked router, both complete |
| 12 | test_run_with_dependency | Node B uses {A.output}, verify substitution |
| 13 | test_run_node_failure_skips_downstream | A fails → B skipped |
| 14 | test_run_persists_result | WorkflowRun stored in TinyDB |
| 15 | test_compute_depths_single | Single node → depth 0 |
| 16 | test_compute_depths_chain | A→B→C → depths 0,1,2 |
| 17 | test_compute_depths_diamond | A→(B,C)→D → depths 0,1,1,2 |
| 18 | test_parallel_two_independent | Two independent nodes both complete |
| 19 | test_parallel_diamond_dag | A→(B,C)→D all complete |
| 20 | test_parallel_with_failure | Failed node skips downstream |
| 21 | test_parallel_max_workers | max_workers=1 forces sequential |
| 22 | test_node_timeout_default | Default timeout is 300 seconds |
| 23 | test_node_timeout_from_yaml | Timeout parsed from YAML |
| 24 | test_node_retries_default | Default retries is 0 |
| 25 | test_node_retries_from_yaml | Retries parsed from YAML |
| 26 | test_workflow_timeout_default | Default workflow timeout is 0 (unlimited) |
| 27 | test_workflow_timeout_from_yaml | Workflow timeout parsed from YAML |
| 28 | test_node_timeout_triggers | Slow worker times out → node failed with error |
| 29 | test_node_retry_success | First attempt fails, second succeeds |
| 30 | test_node_retry_exhausted | All retries fail → final result failed |
| 31 | test_workflow_timeout_marks_remaining | Remaining nodes marked failed on workflow timeout |
| 32 | test_workflow_timeout_zero_unlimited | timeout=0 does not limit execution |
| 33 | test_node_timeout_unblocks_layer | Timed-out node doesn't block depth layer |
| 34 | test_retry_logs_attempts | Logger captures retry warning messages |

---

## test_db.py — 12 tests (NEW in v0.5)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_get_db_returns_tinydb_and_lock | Returns (TinyDB, Lock) tuple |
| 2 | test_get_db_same_path_same_instance | Same path → same TinyDB object |
| 3 | test_get_db_different_paths | Different paths → different instances |
| 4 | test_get_db_creates_parent_dirs | Parent directories auto-created |
| 5 | test_close_all | All instances closed, registry empty |
| 6 | test_get_db_after_close_all | Fresh instance after close_all |
| 7 | test_close_all_idempotent | Calling twice doesn't error |
| 8 | test_concurrent_get_db_same_path | 10 threads → same instance |
| 9 | test_concurrent_writes | 10 threads writing → no corruption |
| 10 | test_concurrent_read_write | Readers + writers → consistent |
| 11 | test_lock_is_per_db | Lock on A doesn't block B |
| 12 | test_reset_registry | _reset_registry clears without close |

---

## test_webhooks.py — 22 tests

| # | Test | Validates |
|---|------|-----------|
| 1 | test_health_no_auth | /health returns 200 without auth |
| 2 | test_trigger_workflow_no_auth | 401 without bearer token |
| 3 | test_trigger_workflow_bad_auth | 401 with wrong token |
| 4 | test_auth_timing_safe | hmac.compare_digest used |
| 5 | test_trigger_workflow_success | Valid auth + workflow → 200 + run_id |
| 6 | test_trigger_workflow_missing_file | 400 for missing workflow file |
| 7 | test_trigger_workflow_missing_body | 400 for empty body |
| 8 | test_trigger_workflow_budget_exceeded | Error when budget frozen |
| 9 | test_trigger_task_success | Valid task creation → 200 + task_id |
| 10 | test_trigger_task_missing_worker | 400 for missing worker field |
| 11 | test_trigger_task_invalid_worker | 400 for nonexistent worker |
| 12 | test_trigger_task_with_run_at | Scheduled task with future timestamp |
| 13 | test_emit_event_success | Event persisted to event log |
| 14 | test_emit_event_missing_type | 400 for missing type |
| 15 | test_webhook_schedule_immediate | No run_at uses valid ISO timestamp |
| 16 | test_webhook_schedule_with_run_at | Provided run_at is used as schedule_value |
| 17 | test_webhook_schedule_value_is_iso | Schedule value is valid ISO format |
| 18 | test_webhook_path_traversal_absolute | Absolute path outside project → 400 |
| 19 | test_webhook_path_traversal_relative | Relative `../../etc/passwd` → 400 |
| 20 | test_webhook_path_within_project_relative | Relative path within project works |
| 21 | test_webhook_path_within_project_absolute | Absolute path within project works |
| 22 | test_webhook_path_traversal_dot_dot | Nested `../` traversal → 400 |

---

## test_broker.py — 16 tests (NEW in v0.5)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_initial_account | $10,000 cash on init |
| 2 | test_get_positions_empty | Empty list when no positions |
| 3 | test_buy_success | Cash decreases, position created |
| 4 | test_buy_insufficient_cash | BrokerError raised |
| 5 | test_buy_zero_quantity | BrokerError raised |
| 6 | test_multiple_buys_avg_entry | Weighted average entry price |
| 7 | test_sell_success | Cash increases, position reduced |
| 8 | test_sell_insufficient_shares | BrokerError raised |
| 9 | test_sell_all_removes_position | Full sell removes position entry |
| 10 | test_partial_sell | Position quantity reduced, avg unchanged |
| 11 | test_get_positions_with_data | Returns all positions |
| 12 | test_get_account_after_trades | Equity = cash + positions |
| 13 | test_get_trades_all | Returns all trades newest first |
| 14 | test_get_trades_by_symbol | Filtered by symbol |
| 15 | test_get_price_without_yfinance | BrokerError with install suggestion |
| 16 | test_concurrent_trades | 5 threads buying → consistent |

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

## test_registry.py — 15 tests (NEW in v1.0)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_register_creates_entry | Name→path stored in JSON |
| 2 | test_register_multiple | Multiple operations coexist |
| 3 | test_unregister_removes_entry | Entry removed from JSON |
| 4 | test_unregister_not_found | RegistryError raised |
| 5 | test_unregister_clears_active | Active cleared when unregistered |
| 6 | test_list_operations_empty | Empty dict when no registry |
| 7 | test_list_operations_with_data | Returns all registered |
| 8 | test_get_path_exists | Returns resolved Path |
| 9 | test_get_path_not_found | Returns None |
| 10 | test_set_active_success | Active file written |
| 11 | test_set_active_not_registered | RegistryError raised |
| 12 | test_get_active_none | None when no active file |
| 13 | test_get_active_path_round_trip | set_active → get_active_path round trip |
| 14 | test_corrupt_registry_json | Returns empty dict gracefully |
| 15 | test_registry_dir_created_on_write | Parent dirs auto-created |

---

## test_task_router.py — 8 tests (NEW in v1.0)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_select_best_skill_match | Worker with matching skills wins |
| 2 | test_select_no_workers | Returns None |
| 3 | test_select_performance_factor | Higher-rated worker preferred |
| 4 | test_select_seniority_factor | Higher-level worker gets bonus |
| 5 | test_select_specified_workers | Only considers given list |
| 6 | test_select_handles_worker_error | Gracefully skips broken worker |
| 7 | test_select_empty_description | Returns a worker (doesn't crash) |
| 8 | test_select_equal_workers | Deterministic pick |

---

## test_marketplace.py — 12 tests (NEW in v1.0)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_list_templates | Parsed from YAML registry |
| 2 | test_search_by_name | Name match |
| 3 | test_search_by_tag | Tag match |
| 4 | test_search_case_insensitive | Case doesn't matter |
| 5 | test_search_no_results | Empty list |
| 6 | test_info_found | Returns template dict |
| 7 | test_info_not_found | Returns None |
| 8 | test_install_success | Files downloaded to templates/ |
| 9 | test_install_already_exists | MarketplaceError raised |
| 10 | test_install_not_in_registry | MarketplaceError raised |
| 11 | test_install_network_error | MarketplaceError + cleanup |
| 12 | test_corrupt_registry_yaml | MarketplaceError raised |

---

## test_logging.py — 8 tests (NEW in v1.1)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_setup_logging_default | Returns logger with INFO level |
| 2 | test_setup_logging_debug_level | DEBUG level works |
| 3 | test_setup_logging_with_file | Creates log file on disk |
| 4 | test_setup_logging_idempotent | No duplicate handlers on repeat calls |
| 5 | test_get_logger_naming | Returns open-corp.{module} logger |
| 6 | test_router_logs_fallback | caplog captures router tier fallback |
| 7 | test_accountant_logs_warning | caplog captures budget warning |
| 8 | test_workflow_logs_lifecycle | caplog captures workflow start/complete |

---

## test_housekeeping.py — 14 tests (NEW in v1.1)

| # | Test | Validates |
|---|------|-----------|
| 1 | test_clean_events_removes_old | Events older than cutoff removed |
| 2 | test_clean_events_keeps_recent | Events within window kept |
| 3 | test_clean_events_empty | No crash on missing DB file |
| 4 | test_clean_spending_removes_old | Spending records cleaned by date |
| 5 | test_clean_spending_keeps_recent | Recent spending kept |
| 6 | test_clean_spending_empty | No crash on missing DB |
| 7 | test_clean_workflows_removes_old | Old workflow runs removed |
| 8 | test_clean_workflows_keeps_recent | Recent runs kept |
| 9 | test_clean_performance_trims | Trims to max, keeps newest |
| 10 | test_clean_performance_under_limit | No trim when under limit |
| 11 | test_clean_performance_missing_file | No crash on missing file |
| 12 | test_run_all_returns_summary | Returns dict with all counts |
| 13 | test_run_all_logs_total | Logger captures summary message |
| 14 | test_cli_housekeep | CLI command runs and prints results |

---

## Coverage Gaps (known, acceptable for v1.1)

- **YouTube training pipeline:** No automated tests for actual download/transcribe (requires yt-dlp + whisper)
- **PDF training:** Uses mocked pypdf in tests (real PDF parsing tested manually)
- **APScheduler integration:** Tests validate CRUD and `_execute_task()` directly; `start()`/`stop()` with live APScheduler not tested (would require timing-sensitive assertions)
- **Daemon background mode:** `os.fork()` not testable in pytest; manual verification required
- **yfinance price fetching:** Tests mock yfinance entirely; live API tested manually
- **Flask dev server:** Tests use Flask test client; production deployment (gunicorn) not tested

---

Total tests: **388** | All passing
