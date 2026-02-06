# Migration Guide

## v0.5 to v1.0

### Breaking Changes

None. v1.0 is fully backward-compatible with v0.5 projects.

### Behavioral Change: Project Loading

`_load_project()` now checks the operation registry before falling back to the current working directory:

1. `--project-dir` flag (highest priority, unchanged)
2. Active operation from `~/.open-corp/` registry (new in v1.0)
3. Current working directory (unchanged fallback)

When no registry exists (e.g., fresh install or v0.5 upgrade), behavior is identical to v0.5.

### New charter.yaml Sections

These sections are optional and default to sensible values:

```yaml
# Auto-promotion/demotion rules
promotion_rules:
  min_tasks: 5
  promote_threshold: 4.0
  demote_threshold: 2.0
  review_window: 20

# Template marketplace
marketplace:
  registry_url: ""
```

### New CLI Commands

| Command | Description |
|---------|-------------|
| `corp ops create/list/switch/remove/active` | Multi-operation management |
| `corp review [worker] [--auto]` | Performance review and auto-promotion |
| `corp delegate <message>` | Smart task routing |
| `corp marketplace list/search/info/install` | Template marketplace |

### New Framework Modules

| Module | Description |
|--------|-------------|
| `framework/registry.py` | Operation registry (`~/.open-corp/`) |
| `framework/task_router.py` | Skill-based worker selection |
| `framework/marketplace.py` | Remote template marketplace client |

### New Worker Methods

- `Worker.performance_summary()` — aggregated performance stats

### New HR Methods

- `HR.demote()` — decrement worker seniority level
- `HR.team_review()` — aggregate team performance scorecard
- `HR.auto_review()` — auto-promote/demote based on rules

### New Dependencies

No new runtime dependencies. Optional dev dependencies for documentation:

```bash
pip install "open-corp[docs]"
# mkdocs, mkdocs-material, mkdocstrings[python]
```

### Upgrade Steps

1. Update the package: `pip install -U open-corp`
2. Optionally add `promotion_rules` and `marketplace` sections to `charter.yaml`
3. Register existing projects: `corp ops create myproject --dir /path/to/project`
4. Set active: `corp ops switch myproject`
