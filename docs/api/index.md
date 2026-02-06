# API Reference

Auto-generated from source code docstrings.

## Core

::: framework.config.ProjectConfig
    options:
      show_source: false

::: framework.config.BudgetConfig
    options:
      show_source: false

::: framework.config.PromotionRules
    options:
      show_source: false

::: framework.config.SecurityConfig
    options:
      show_source: false

## Validation

::: framework.validation.validate_worker_name
    options:
      show_source: false

::: framework.validation.validate_path_within
    options:
      show_source: false

::: framework.validation.validate_payload_size
    options:
      show_source: false

::: framework.validation.RateLimiter
    options:
      show_source: false

::: framework.validation.safe_load_json
    options:
      show_source: false

::: framework.validation.safe_write_json
    options:
      show_source: false

## Worker

::: framework.worker.Worker
    options:
      show_source: false
      members:
        - chat
        - build_system_prompt
        - summarize_session
        - update_memory
        - record_performance
        - performance_summary
        - get_tier

## HR

::: framework.hr.HR
    options:
      show_source: false
      members:
        - hire_from_template
        - hire_from_scratch
        - list_workers
        - fire
        - promote
        - demote
        - team_review
        - auto_review
        - train_from_document
        - train_from_url
        - train_from_youtube

## Task Router

::: framework.task_router.TaskRouter
    options:
      show_source: false

## Workflow

::: framework.workflow.WorkflowEngine
    options:
      show_source: false
      members:
        - run
        - list_runs
        - get_run

::: framework.workflow.Workflow
    options:
      show_source: false

## Registry

::: framework.registry.OperationRegistry
    options:
      show_source: false

## Marketplace

::: framework.marketplace.Marketplace
    options:
      show_source: false

## Exceptions

::: framework.exceptions
    options:
      show_source: false
