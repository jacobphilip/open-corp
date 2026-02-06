# Contributing

## Development Setup

```bash
git clone https://github.com/open-corp/open-corp
cd open-corp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_worker.py -v

# With coverage
pytest tests/ --cov=framework --cov=scripts
```

The test suite uses pytest with respx for HTTP mocking. All API calls are mocked — no real API keys needed for testing.

## Code Style

- Python 3.10+ type hints
- Dataclasses (no Pydantic)
- Dependency injection (constructors, no singletons except db registry)
- All exceptions include a `.suggestion` field for user-facing messages

## Adding a New Module

1. Create `framework/your_module.py`
2. Add tests in `tests/test_your_module.py`
3. Wire into CLI in `scripts/corp.py`
4. Update `TEST_PLAN.md` with new test counts
5. Add documentation in `docs/`

## Creating Templates

Templates live in `templates/<name>/`:

```
templates/my-template/
  profile.md      # Worker personality (required)
  skills.yaml     # Role and skill list (required)
  config.yaml     # Level, model, context budget (required)
```

### Publishing to Marketplace

1. Host your template files at a public URL
2. Add an entry to a registry YAML file:
   ```yaml
   templates:
     - name: my-template
       description: "What this template does"
       author: "your-name"
       tags: [tag1, tag2]
       url: "https://your-host.com/templates/my-template"
   ```
3. Share the registry URL

## Commit Convention

```
feat: add new feature
fix: fix a bug
refactor: code restructure without behavior change
docs: documentation only
test: add or update tests
chore: build, deps, tooling
```

## Pull Request Guidelines

1. All tests must pass
2. New features need tests
3. Update docs for user-facing changes
4. One logical change per PR
5. Keep PRs focused — avoid mixing features with refactors

## Architecture Notes

- All state is file-based (JSON/YAML in project directory)
- TinyDB operations are thread-safe via `get_db()` locks
- Budget enforcement is automatic and cannot be bypassed
- Worker seniority maps to model tier access
- Workflows execute in parallel by depth layer
