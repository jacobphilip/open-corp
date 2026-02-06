#!/usr/bin/env python3
"""corp — CLI for managing your open-corp project."""

import json
import signal
import sys
from pathlib import Path

import click
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.log import setup_logging
from framework.exceptions import (
    BrokerError, BudgetExceeded, ConfigError, MarketplaceError, ModelUnavailable,
    RegistryError, SchedulerError, TrainingError, WebhookError, WorkerNotFound,
    WorkflowError,
)
from framework.hr import HR
from framework.registry import OperationRegistry
from framework.router import Router
from framework.scheduler import Scheduler, ScheduledTask
from framework.worker import Worker
from framework.workflow import Workflow, WorkflowEngine


def _load_project(project_dir: Path | None = None) -> tuple[ProjectConfig, Accountant, Router, HR]:
    """Load all project components from the given (or current) directory.

    Lookup chain: --project-dir > active operation from registry > cwd.
    """
    if project_dir is None:
        # Check registry for active operation
        registry = OperationRegistry()
        active_path = registry.get_active_path()
        if active_path is not None:
            project_dir = active_path
        else:
            project_dir = Path.cwd()
    config = ProjectConfig.load(project_dir)
    accountant = Accountant(config)
    router = Router(config, accountant)
    hr = HR(config, project_dir)
    return config, accountant, router, hr


@click.group()
@click.option("--project-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Project directory (defaults to cwd)")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, project_dir, verbose):
    """open-corp — AI-powered operations with specialist workers."""
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = project_dir
    ctx.obj["verbose"] = verbose
    setup_logging(level="DEBUG" if verbose else "INFO")


@cli.command()
@click.pass_context
def status(ctx):
    """Show project configuration and budget status."""
    try:
        config, accountant, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Project: {config.name}")
    click.echo(f"Owner:   {config.owner}")
    click.echo(f"Mission: {config.mission}")
    click.echo()

    report = accountant.daily_report()
    click.echo(f"Budget:  ${report['total_spent']:.4f} / ${report['daily_limit']:.2f} "
               f"({report['usage_ratio']:.0%})")
    click.echo(f"Status:  {report['status']}")
    click.echo(f"Calls:   {report['call_count']}")


@cli.command()
@click.pass_context
def budget(ctx):
    """Show detailed spending report."""
    try:
        _, accountant, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    report = accountant.daily_report()
    click.echo(f"Date: {report['date']}")
    click.echo(f"Spent: ${report['total_spent']:.4f} / ${report['daily_limit']:.2f}")
    click.echo(f"Remaining: ${report['remaining']:.4f}")
    click.echo(f"Status: {report['status']}")
    click.echo(f"Calls: {report['call_count']}")
    click.echo(f"Tokens: {report['total_tokens_in']} in / {report['total_tokens_out']} out")

    if report["by_worker"]:
        click.echo("\nBy worker:")
        for w, cost in sorted(report["by_worker"].items()):
            click.echo(f"  {w}: ${cost:.4f}")

    if report["by_model"]:
        click.echo("\nBy model:")
        for m, cost in sorted(report["by_model"].items()):
            click.echo(f"  {m}: ${cost:.4f}")


@cli.command()
@click.pass_context
def workers(ctx):
    """List all workers."""
    try:
        _, _, _, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    worker_list = hr.list_workers()
    if not worker_list:
        click.echo("No workers hired yet. Use: corp hire <template> <name>")
        return

    seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
    for w in worker_list:
        level = w["level"]
        title = seniority.get(level, f"L{level}")
        click.echo(f"  {w['name']} — {title} (L{level}) — {w['role']}")


@cli.command()
@click.argument("template")
@click.argument("name")
@click.option("--scratch", is_flag=True, help="Create from scratch instead of template")
@click.option("--role", default="general", help="Role when hiring from scratch")
@click.pass_context
def hire(ctx, template, name, scratch, role):
    """Hire a new worker from a template or from scratch."""
    try:
        config, _, _, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    try:
        if scratch:
            worker = hr.hire_from_scratch(name, role=role)
            click.echo(f"Hired {name} from scratch as {role}")
        else:
            worker = hr.hire_from_template(template, name)
            click.echo(f"Hired {name} from template '{template}'")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("worker_name")
@click.pass_context
def chat(ctx, worker_name):
    """Interactive chat with a worker. Ctrl+C or 'quit' to exit."""
    try:
        config, accountant, router, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    try:
        worker = Worker(worker_name, config.project_dir, config)
    except WorkerNotFound:
        click.echo(f"Worker '{worker_name}' not found. Use: corp workers", err=True)
        sys.exit(1)

    seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
    title = seniority.get(worker.level, f"L{worker.level}")
    click.echo(f"Chatting with {worker_name} ({title}, tier={worker.get_tier()})")
    click.echo("Type 'quit' or Ctrl+C to exit.\n")

    history: list[dict] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            click.echo()
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        try:
            response, history = worker.chat(user_input, router, history=history)
            click.echo(f"\n{worker_name}: {response}\n")
        except BudgetExceeded as e:
            click.echo(f"\nBudget exceeded: {e}\n", err=True)
        except ModelUnavailable as e:
            click.echo(f"\nModel unavailable: {e}\n", err=True)
        except Exception as e:
            click.echo(f"\nError: {e}\n", err=True)

    # Summarize session on exit
    if history:
        try:
            worker.summarize_session(history, router)
            click.echo("Session summary saved.")
        except Exception:
            click.echo("Could not save session summary.")
    click.echo("Bye.")


@cli.command()
@click.argument("worker_name")
@click.option("--youtube", help="YouTube URL to train from")
@click.option("--document", help="Local file path to train from (PDF, markdown, text)")
@click.option("--url", help="Web page URL to train from")
@click.pass_context
def train(ctx, worker_name, youtube, document, url):
    """Train a worker from external sources."""
    try:
        config, _, _, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    try:
        if youtube:
            result = hr.train_from_youtube(worker_name, youtube)
            click.echo(result)
        elif document:
            result = hr.train_from_document(worker_name, document)
            click.echo(result)
        elif url:
            result = hr.train_from_url(worker_name, url)
            click.echo(result)
        else:
            click.echo("Specify a training source: --youtube URL, --document PATH, or --url URL", err=True)
            sys.exit(1)
    except TrainingError as e:
        click.echo(f"Training error: {e}", err=True)
        sys.exit(1)
    except WorkerNotFound as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("worker_name")
@click.option("--search", default=None, help="Search knowledge base with keywords")
@click.pass_context
def knowledge(ctx, worker_name, search):
    """View or search a worker's knowledge base."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    try:
        worker = Worker(worker_name, config.project_dir, config)
    except WorkerNotFound:
        click.echo(f"Worker '{worker_name}' not found.", err=True)
        sys.exit(1)

    entries = worker.knowledge.entries
    if not entries:
        click.echo(f"{worker_name} has no knowledge base entries.")
        return

    if search:
        from framework.knowledge import search_knowledge
        results = search_knowledge(entries, search, max_chars=10000)
        click.echo(f"Found {len(results)} matching entries for '{search}':")
        for entry in results:
            click.echo(f"  [{entry.type}] {entry.source} (chunk {entry.chunk_index})")
            click.echo(f"    {entry.content[:120]}...")
    else:
        click.echo(f"{worker_name} has {len(entries)} knowledge entries:")
        sources = set(e.source for e in entries)
        for source in sorted(sources):
            source_entries = [e for e in entries if e.source == source]
            click.echo(f"  {source} — {len(source_entries)} chunks")


@cli.command()
@click.pass_context
def init(ctx):
    """Initialize a new open-corp project in the current directory."""
    project_dir = ctx.obj["project_dir"] or Path.cwd()
    charter_path = project_dir / "charter.yaml"

    if charter_path.exists():
        if not click.confirm("charter.yaml already exists. Overwrite?"):
            click.echo("Aborted.")
            sys.exit(1)

    # Gather project info
    name = click.prompt("Project name")
    owner = click.prompt("Owner name")
    mission = click.prompt("Mission statement")

    while True:
        budget_str = click.prompt("Daily budget (USD)", default="3.00")
        try:
            daily_budget = float(budget_str)
            if daily_budget <= 0:
                click.echo("Budget must be positive.")
                continue
            break
        except ValueError:
            click.echo("Enter a valid number.")

    api_key = click.prompt("OpenRouter API key (sk-or-...)", default="", show_default=False)
    if api_key and not api_key.startswith("sk-or-"):
        click.echo("Warning: Key doesn't start with 'sk-or-'. Continuing anyway.")

    # Generate charter.yaml
    charter = {
        "project": {
            "name": name,
            "owner": owner,
            "mission": mission,
        },
        "budget": {
            "daily_limit": daily_budget,
            "currency": "USD",
            "thresholds": {
                "normal": 0.60,
                "caution": 0.80,
                "austerity": 0.95,
                "critical": 1.00,
            },
        },
        "models": {
            "tiers": {
                "cheap": {
                    "models": ["deepseek/deepseek-chat", "mistralai/mistral-tiny"],
                    "for": "Simple tasks",
                },
                "mid": {
                    "models": ["anthropic/claude-sonnet-4-20250514"],
                    "for": "Complex tasks",
                },
                "premium": {
                    "models": ["anthropic/claude-opus-4-5-20251101"],
                    "for": "Board-level decisions",
                },
            },
        },
        "git": {"auto_commit": False, "auto_push": False},
        "worker_defaults": {
            "starting_level": 1,
            "max_context_tokens": 2000,
            "model": "deepseek/deepseek-chat",
            "honest_ai": True,
        },
    }

    charter_path.write_text(yaml.dump(charter, default_flow_style=False, sort_keys=False))

    # Write .env
    env_path = project_dir / ".env"
    env_lines = [f"OPENROUTER_API_KEY={api_key}"]
    env_path.write_text("\n".join(env_lines) + "\n")

    # Create directories
    for dirname in ("workers", "templates", "data"):
        (project_dir / dirname).mkdir(exist_ok=True)

    # Auto-register in operation registry
    try:
        registry = OperationRegistry()
        registry.register(name, project_dir)
    except Exception:
        pass  # Non-critical — registry is optional

    click.echo(f"\nProject '{name}' initialized in {project_dir}")
    click.echo("Created: charter.yaml, .env, workers/, templates/, data/")


# --- Operations management commands ---

@cli.group()
def ops():
    """Manage multiple open-corp operations."""
    pass


@ops.command("create")
@click.argument("name")
@click.option("--dir", "directory", type=click.Path(path_type=Path), default=None,
              help="Use an existing directory instead of creating one")
@click.pass_context
def ops_create(ctx, name, directory):
    """Register a new operation."""
    registry = OperationRegistry()
    if directory is None:
        directory = Path.cwd() / name
        directory.mkdir(parents=True, exist_ok=True)
    directory = Path(directory).resolve()
    registry.register(name, directory)
    click.echo(f"Registered operation '{name}' at {directory}")


@ops.command("list")
def ops_list():
    """List all registered operations."""
    registry = OperationRegistry()
    operations = registry.list_operations()
    active = registry.get_active()
    if not operations:
        click.echo("No operations registered. Use: corp ops create <name>")
        return
    for op_name, op_path in sorted(operations.items()):
        marker = " *" if op_name == active else ""
        click.echo(f"  {op_name}: {op_path}{marker}")


@ops.command("switch")
@click.argument("name")
def ops_switch(name):
    """Switch to a different operation."""
    registry = OperationRegistry()
    try:
        registry.set_active(name)
        click.echo(f"Switched to '{name}'")
    except RegistryError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@ops.command("remove")
@click.argument("name")
def ops_remove(name):
    """Unregister an operation (does not delete files)."""
    registry = OperationRegistry()
    try:
        registry.unregister(name)
        click.echo(f"Removed '{name}' from registry")
    except RegistryError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@ops.command("active")
def ops_active():
    """Show the currently active operation."""
    registry = OperationRegistry()
    active = registry.get_active()
    if active:
        path = registry.get_active_path()
        click.echo(f"{active}: {path}")
    else:
        click.echo("No active operation. Use: corp ops switch <name>")


@cli.command()
@click.argument("worker_name", required=False, default=None)
@click.pass_context
def inspect(ctx, worker_name):
    """Inspect project overview or a specific worker."""
    try:
        config, accountant, _, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    if worker_name is None:
        # Project overview
        report = accountant.daily_report()
        click.echo(f"Project: {config.name}")
        click.echo(f"Owner:   {config.owner}")
        click.echo(f"Mission: {config.mission}")
        click.echo(f"Budget:  ${report['total_spent']:.4f} / ${report['daily_limit']:.2f} ({report['status']})")
        click.echo()

        worker_list = hr.list_workers()
        if not worker_list:
            click.echo("Workers: none")
        else:
            click.echo("Workers:")
            seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
            for w in worker_list:
                title = seniority.get(w["level"], f"L{w['level']}")
                # Count memory, knowledge, performance
                wdir = config.project_dir / "workers" / w["name"]
                mem_count = 0
                kb_count = 0
                perf_count = 0
                mem_path = wdir / "memory.json"
                if mem_path.exists():
                    try:
                        mem_count = len(json.loads(mem_path.read_text()))
                    except (json.JSONDecodeError, OSError):
                        pass
                kb_path = wdir / "knowledge_base" / "knowledge.json"
                if kb_path.exists():
                    try:
                        kb_count = len(json.loads(kb_path.read_text()))
                    except (json.JSONDecodeError, OSError):
                        pass
                perf_path = wdir / "performance.json"
                if perf_path.exists():
                    try:
                        perf_count = len(json.loads(perf_path.read_text()))
                    except (json.JSONDecodeError, OSError):
                        pass
                click.echo(
                    f"  {w['name']} — {title} — {w['role']} "
                    f"(memory: {mem_count}, knowledge: {kb_count}, tasks: {perf_count})"
                )
    else:
        # Worker detail
        try:
            worker = Worker(worker_name, config.project_dir, config)
        except WorkerNotFound:
            click.echo(f"Worker '{worker_name}' not found.", err=True)
            sys.exit(1)

        # Profile (first 5 lines)
        profile_lines = worker.profile.strip().split("\n")[:5]
        click.echo("Profile:")
        for line in profile_lines:
            click.echo(f"  {line}")
        click.echo()

        # Skills
        skills_list = worker.skills.get("skills", [])
        if skills_list:
            skills_text = ", ".join(
                s if isinstance(s, str) else s.get("name", str(s))
                for s in skills_list
            )
            click.echo(f"Skills: {skills_text}")

        # Level/tier
        seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
        title = seniority.get(worker.level, f"L{worker.level}")
        click.echo(f"Level:  {title} (L{worker.level}, tier={worker.get_tier()})")

        # Counts
        click.echo(f"Memory: {len(worker.memory)} entries")
        click.echo(f"Knowledge: {len(worker.knowledge.entries)} entries")

        # Knowledge sources
        if worker.knowledge.entries:
            sources = sorted(set(e.source for e in worker.knowledge.entries))
            click.echo(f"Sources: {', '.join(sources)}")

        # Performance
        click.echo(f"Tasks: {len(worker.performance)}")
        if worker.performance:
            ratings = [p["rating"] for p in worker.performance if p.get("rating") is not None]
            if ratings:
                avg = sum(ratings) / len(ratings)
                click.echo(f"Avg rating: {avg:.1f}")


def _load_project_full(project_dir=None):
    """Load all components including event log."""
    config, accountant, router, hr = _load_project(project_dir)
    event_log = EventLog(config.project_dir / "data" / "events.json")
    return config, accountant, router, hr, event_log


# --- Review + Delegate commands ---

@cli.command()
@click.argument("worker_name", required=False, default=None)
@click.option("--auto", "auto_review", is_flag=True, help="Auto-promote/demote based on rules")
@click.pass_context
def review(ctx, worker_name, auto_review):
    """Review worker performance. No args = team scorecard."""
    try:
        config, _, _, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    if auto_review:
        actions = hr.auto_review()
        if not actions:
            click.echo("No promotions or demotions needed.")
        else:
            for a in actions:
                click.echo(f"  {a['worker']}: {a['action']} to L{a['to_level']} (avg {a['avg_rating']})")
        return

    if worker_name:
        try:
            worker = Worker(worker_name, config.project_dir, config)
        except WorkerNotFound:
            click.echo(f"Worker '{worker_name}' not found.", err=True)
            sys.exit(1)
        summary = worker.performance_summary()
        click.echo(f"{worker_name}:")
        click.echo(f"  Tasks:        {summary['task_count']}")
        click.echo(f"  Avg rating:   {summary['avg_rating']}")
        click.echo(f"  Success rate: {summary['success_rate']:.0%}")
        click.echo(f"  Trend:        {summary['trend']:+.2f}")
    else:
        results = hr.team_review()
        if not results:
            click.echo("No workers to review.")
            return
        seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
        for r in results:
            title = seniority.get(r["level"], f"L{r['level']}")
            click.echo(f"  {r['name']} — {title} — avg {r['avg_rating']} ({r['task_count']} tasks)")


@cli.command()
@click.argument("message")
@click.pass_context
def delegate(ctx, message):
    """Auto-select a worker and send a message."""
    try:
        config, accountant, router, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.task_router import TaskRouter
    task_router = TaskRouter(config, hr)
    selected = task_router.select_worker(message)
    if selected is None:
        click.echo("No workers available. Hire workers first.", err=True)
        sys.exit(1)

    try:
        worker = Worker(selected, config.project_dir, config)
    except WorkerNotFound:
        click.echo(f"Selected worker '{selected}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Delegating to {selected}...")
    try:
        response, _ = worker.chat(message, router)
        click.echo(f"\n{selected}: {response}")
    except (BudgetExceeded, ModelUnavailable) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# --- Marketplace commands ---

@cli.group()
def marketplace():
    """Browse and install templates from the marketplace."""
    pass


@marketplace.command("list")
@click.pass_context
def marketplace_list(ctx):
    """List available templates."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.marketplace import Marketplace
    mp = Marketplace(config.marketplace_url, config.project_dir / "templates")

    try:
        templates = mp.list_templates()
    except MarketplaceError as e:
        click.echo(f"Marketplace error: {e}", err=True)
        sys.exit(1)

    if not templates:
        click.echo("No templates available.")
        return

    for tpl in templates:
        tags = ", ".join(tpl.get("tags", []))
        click.echo(f"  {tpl['name']} — {tpl.get('description', '')} [{tags}]")


@marketplace.command("search")
@click.argument("query")
@click.pass_context
def marketplace_search(ctx, query):
    """Search templates by name, description, or tags."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.marketplace import Marketplace
    mp = Marketplace(config.marketplace_url, config.project_dir / "templates")

    try:
        results = mp.search(query)
    except MarketplaceError as e:
        click.echo(f"Marketplace error: {e}", err=True)
        sys.exit(1)

    if not results:
        click.echo(f"No templates matching '{query}'.")
        return

    for tpl in results:
        click.echo(f"  {tpl['name']} — {tpl.get('description', '')}")


@marketplace.command("info")
@click.argument("name")
@click.pass_context
def marketplace_info(ctx, name):
    """Show details for a template."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.marketplace import Marketplace
    mp = Marketplace(config.marketplace_url, config.project_dir / "templates")

    try:
        info = mp.info(name)
    except MarketplaceError as e:
        click.echo(f"Marketplace error: {e}", err=True)
        sys.exit(1)

    if info is None:
        click.echo(f"Template '{name}' not found.")
        sys.exit(1)

    click.echo(f"Name:        {info.get('name', '')}")
    click.echo(f"Description: {info.get('description', '')}")
    click.echo(f"Author:      {info.get('author', '')}")
    click.echo(f"Tags:        {', '.join(info.get('tags', []))}")
    click.echo(f"URL:         {info.get('url', '')}")


@marketplace.command("install")
@click.argument("name")
@click.pass_context
def marketplace_install(ctx, name):
    """Install a template from the marketplace."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.marketplace import Marketplace
    mp = Marketplace(config.marketplace_url, config.project_dir / "templates")

    try:
        path = mp.install(name)
        click.echo(f"Installed '{name}' to {path}")
    except MarketplaceError as e:
        click.echo(f"Marketplace error: {e}", err=True)
        sys.exit(1)


# --- Schedule commands ---

@cli.group()
def schedule():
    """Manage scheduled tasks."""
    pass


@schedule.command("add")
@click.argument("worker_name")
@click.argument("message")
@click.option("--cron", default=None, help="Cron expression (e.g. '*/30 * * * *')")
@click.option("--interval", default=None, type=int, help="Interval in seconds")
@click.option("--once", default=None, help="ISO datetime for one-time execution")
@click.option("--description", default="", help="Task description")
@click.pass_context
def schedule_add(ctx, worker_name, message, cron, interval, once, description):
    """Add a scheduled task for a worker."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)

    if cron:
        schedule_type, schedule_value = "cron", cron
    elif interval:
        schedule_type, schedule_value = "interval", str(interval)
    elif once:
        schedule_type, schedule_value = "once", once
    else:
        click.echo("Specify --cron, --interval, or --once", err=True)
        sys.exit(1)

    try:
        task = scheduler.add_task(ScheduledTask(
            worker_name=worker_name,
            message=message,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            description=description,
        ))
        click.echo(f"Scheduled task {task.id}: {worker_name} ({schedule_type}={schedule_value})")
    except SchedulerError as e:
        click.echo(f"Scheduler error: {e}", err=True)
        sys.exit(1)


@schedule.command("list")
@click.pass_context
def schedule_list(ctx):
    """List all scheduled tasks."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)
    tasks = scheduler.list_tasks()
    if not tasks:
        click.echo("No scheduled tasks.")
        return

    for t in tasks:
        status = "enabled" if t.get("enabled", True) else "disabled"
        click.echo(f"  {t['id']} — {t['worker_name']} — {t['schedule_type']}={t['schedule_value']} ({status})")


@schedule.command("remove")
@click.argument("task_id")
@click.pass_context
def schedule_remove(ctx, task_id):
    """Remove a scheduled task."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)
    try:
        scheduler.remove_task(task_id)
        click.echo(f"Removed task {task_id}")
    except SchedulerError as e:
        click.echo(f"Scheduler error: {e}", err=True)
        sys.exit(1)


# --- Workflow commands ---

@cli.group()
def workflow():
    """Manage and run DAG workflows."""
    pass


@workflow.command("run")
@click.argument("workflow_file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def workflow_run(ctx, workflow_file):
    """Run a workflow from a YAML file."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    try:
        wf = Workflow.load(workflow_file)
    except WorkflowError as e:
        click.echo(f"Workflow error: {e}", err=True)
        sys.exit(1)

    engine = WorkflowEngine(config, accountant, router, event_log)
    click.echo(f"Running workflow '{wf.name}' ({len(wf.nodes)} nodes)...")

    try:
        run = engine.run(wf)
    except (WorkflowError, BudgetExceeded, ModelUnavailable) as e:
        click.echo(f"Workflow failed: {e}", err=True)
        sys.exit(1)

    for node_id, result in run.node_results.items():
        status = result["status"]
        click.echo(f"  {node_id}: {status}")

    click.echo(f"\nWorkflow {run.status} (run {run.id})")


@workflow.command("list")
@click.option("--name", default=None, help="Filter by workflow name")
@click.pass_context
def workflow_list(ctx, name):
    """List workflow runs."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    engine = WorkflowEngine(config, accountant, router, event_log)
    runs = engine.list_runs(workflow_name=name)
    if not runs:
        click.echo("No workflow runs.")
        return

    for r in runs:
        click.echo(f"  {r['id']} — {r['workflow_name']} — {r['status']} ({r.get('started_at', '')})")


@workflow.command("status")
@click.argument("run_id")
@click.pass_context
def workflow_status(ctx, run_id):
    """Show status of a workflow run."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    engine = WorkflowEngine(config, accountant, router, event_log)
    run = engine.get_run(run_id)
    if not run:
        click.echo(f"Run '{run_id}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Workflow: {run['workflow_name']}")
    click.echo(f"Status:   {run['status']}")
    click.echo(f"Started:  {run.get('started_at', '')}")
    click.echo(f"Completed: {run.get('completed_at', '')}")
    if run.get("node_results"):
        click.echo("\nNodes:")
        for node_id, result in run["node_results"].items():
            click.echo(f"  {node_id}: {result['status']}")


# --- Daemon commands ---

def _pid_file_path(project_dir: Path) -> Path:
    """Return the daemon PID file path."""
    return project_dir / "data" / "daemon.pid"


def _read_pid(pid_path: Path) -> int | None:
    """Read PID from file. Returns None if missing or invalid."""
    if not pid_path.exists():
        return None
    try:
        return int(pid_path.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is alive."""
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@cli.group()
def daemon():
    """Manage the scheduler daemon."""
    pass


@daemon.command("start")
@click.option("--background", "-d", is_flag=True, help="Run in background (daemonize)")
@click.pass_context
def daemon_start(ctx, background):
    """Start the scheduler daemon."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    project_dir = config.project_dir
    pid_path = _pid_file_path(project_dir)

    # Check if already running
    existing_pid = _read_pid(pid_path)
    if existing_pid and _is_pid_alive(existing_pid):
        click.echo(f"Daemon already running (PID {existing_pid}).", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)
    tasks = scheduler.list_tasks()
    enabled = [t for t in tasks if t.get("enabled", True)]

    if not enabled:
        click.echo("No enabled scheduled tasks. Add tasks with: corp schedule add")
        return

    if background:
        import os
        from framework.db import close_all
        close_all()  # close DB handles before fork
        child_pid = os.fork()
        if child_pid > 0:
            # Parent
            click.echo(f"Daemon started in background (PID {child_pid}).")
            return
        # Child — detach
        os.setsid()
        # Re-load components in child process
        config, accountant, router, _, event_log = _load_project_full(project_dir)
        scheduler = Scheduler(config, accountant, router, event_log)
        pid_path.write_text(str(os.getpid()))
    else:
        import os
        pid_path.write_text(str(os.getpid()))

    click.echo(f"Starting daemon with {len(enabled)} task(s)...")
    scheduler.start()

    import signal
    def _shutdown(signum, frame):
        scheduler.stop()
        pid_path.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        scheduler.stop()
        pid_path.unlink(missing_ok=True)
        click.echo("Daemon stopped.")


@daemon.command("stop")
@click.pass_context
def daemon_stop(ctx):
    """Stop the scheduler daemon."""
    project_dir = ctx.obj["project_dir"] or Path.cwd()
    pid_path = _pid_file_path(project_dir)
    pid = _read_pid(pid_path)

    if pid is None or not _is_pid_alive(pid):
        click.echo("Daemon is not running.", err=True)
        pid_path.unlink(missing_ok=True)
        sys.exit(1)

    import os
    os.kill(pid, signal.SIGTERM)
    # Wait briefly for shutdown
    import time
    for _ in range(10):
        if not _is_pid_alive(pid):
            break
        time.sleep(0.5)

    pid_path.unlink(missing_ok=True)
    click.echo(f"Daemon stopped (PID {pid}).")


@daemon.command("status")
@click.pass_context
def daemon_status(ctx):
    """Check if the daemon is running."""
    project_dir = ctx.obj["project_dir"] or Path.cwd()
    pid_path = _pid_file_path(project_dir)
    pid = _read_pid(pid_path)

    if pid is None:
        click.echo("Daemon is not running.")
        return

    if _is_pid_alive(pid):
        click.echo(f"Daemon is running (PID {pid}).")
    else:
        click.echo("Daemon is not running (stale PID file).")
        pid_path.unlink(missing_ok=True)


# --- Events command ---

@cli.command()
@click.option("--type", "event_type", default=None, help="Filter by event type")
@click.option("--limit", default=20, help="Number of events to show")
@click.pass_context
def events(ctx, event_type, limit):
    """Show recent events."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    results = event_log.query(event_type=event_type, limit=limit)
    if not results:
        click.echo("No events.")
        return

    for e in results:
        click.echo(f"  [{e['timestamp']}] {e['type']} — {e['source']}")
        if e.get("data"):
            for k, v in e["data"].items():
                val = str(v)[:100]
                click.echo(f"    {k}: {val}")


# --- Webhook commands ---

@cli.group()
def webhook():
    """Manage the webhook server."""
    pass


@webhook.command("start")
@click.option("--port", default=8080, help="Port to listen on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.pass_context
def webhook_start(ctx, port, host):
    """Start the webhook server."""
    import os
    api_key = os.getenv("WEBHOOK_API_KEY", "")
    if not api_key:
        click.echo("WEBHOOK_API_KEY not set. Run 'corp webhook keygen' and add to .env", err=True)
        sys.exit(1)

    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)

    from framework.webhooks import create_webhook_app
    app = create_webhook_app(config, accountant, router, event_log, scheduler)

    click.echo(f"Starting webhook server on {host}:{port}...")
    app.run(host=host, port=port)


@webhook.command("keygen")
def webhook_keygen():
    """Generate a random API key for webhook auth."""
    import secrets
    key = secrets.token_urlsafe(32)
    click.echo(f"WEBHOOK_API_KEY={key}")
    click.echo("\nAdd this to your .env file.")


# --- Broker commands ---

@cli.group()
def broker():
    """Paper trading broker."""
    pass


@broker.command("account")
@click.pass_context
def broker_account(ctx):
    """Show account summary."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")
    account = b.get_account()

    click.echo(f"Cash:      ${account['cash']:.2f}")
    click.echo(f"Positions: ${account['positions_value']:.2f}")
    click.echo(f"Equity:    ${account['equity']:.2f}")
    click.echo(f"P&L:       ${account['pnl']:+.2f}")


@broker.command("positions")
@click.pass_context
def broker_positions(ctx):
    """Show current positions."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")
    positions = b.get_positions()

    if not positions:
        click.echo("No positions.")
        return

    for p in positions:
        click.echo(f"  {p['symbol']}: {p['quantity']} shares @ ${p['avg_price']:.2f}")


@broker.command("buy")
@click.argument("symbol")
@click.argument("quantity", type=float)
@click.option("--price", type=float, default=None, help="Price per share (uses yfinance if omitted)")
@click.pass_context
def broker_buy(ctx, symbol, quantity, price):
    """Paper buy a stock."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")

    try:
        trade = b.place_trade(symbol, "buy", quantity, price=price)
        click.echo(f"Bought {trade.quantity} {trade.symbol} @ ${trade.price:.2f} = ${trade.total:.2f}")
    except BrokerError as e:
        click.echo(f"Broker error: {e}", err=True)
        sys.exit(1)


@broker.command("sell")
@click.argument("symbol")
@click.argument("quantity", type=float)
@click.option("--price", type=float, default=None, help="Price per share (uses yfinance if omitted)")
@click.pass_context
def broker_sell(ctx, symbol, quantity, price):
    """Paper sell a stock."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")

    try:
        trade = b.place_trade(symbol, "sell", quantity, price=price)
        click.echo(f"Sold {trade.quantity} {trade.symbol} @ ${trade.price:.2f} = ${trade.total:.2f}")
    except BrokerError as e:
        click.echo(f"Broker error: {e}", err=True)
        sys.exit(1)


@broker.command("price")
@click.argument("symbol")
@click.pass_context
def broker_price(ctx, symbol):
    """Get current price for a symbol (requires yfinance)."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")

    try:
        p = b.get_price(symbol)
        click.echo(f"{symbol.upper()}: ${p:.2f}")
    except BrokerError as e:
        click.echo(f"Broker error: {e}", err=True)
        sys.exit(1)


@broker.command("trades")
@click.option("--symbol", default=None, help="Filter by symbol")
@click.option("--limit", default=20, help="Number of trades to show")
@click.pass_context
def broker_trades(ctx, symbol, limit):
    """Show trade history."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.broker import Broker
    b = Broker(config.project_dir / "data" / "broker.json")
    trades = b.get_trades(symbol=symbol, limit=limit)

    if not trades:
        click.echo("No trades.")
        return

    for t in trades:
        click.echo(f"  [{t['timestamp'][:19]}] {t['side'].upper()} {t['quantity']} {t['symbol']} @ ${t['price']:.2f}")


@cli.command()
@click.argument("worker_name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def fire(ctx, worker_name, yes):
    """Fire a worker and clean up references."""
    try:
        config, accountant, router, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    if not yes:
        if not click.confirm(f"Fire '{worker_name}'? This deletes all worker data"):
            click.echo("Aborted.")
            return

    event_log = EventLog(config.project_dir / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log)

    try:
        result = hr.fire(worker_name, confirm=True, scheduler=scheduler)
    except WorkerNotFound:
        click.echo(f"Worker '{worker_name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Fired '{worker_name}'.")
    if result["removed_tasks"] > 0:
        click.echo(f"  Removed {result['removed_tasks']} scheduled task(s).")
    for warning in result["warnings"]:
        click.echo(f"  Warning: {warning}")


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be removed")
@click.pass_context
def housekeep(ctx, dry_run):
    """Clean up old data based on retention policies."""
    try:
        config, _, _, _ = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    from framework.housekeeping import Housekeeper
    hk = Housekeeper(config.project_dir, config.retention)

    if dry_run:
        click.echo("Dry run — retention policies:")
        click.echo(f"  Events:      keep {config.retention.events_days} days")
        click.echo(f"  Spending:    keep {config.retention.spending_days} days")
        click.echo(f"  Workflows:   keep {config.retention.workflows_days} days")
        click.echo(f"  Performance: keep {config.retention.performance_max} records per worker")
        return

    results = hk.run_all()
    total = sum(results.values())
    click.echo(f"Housekeeping complete: {total} records removed")
    for store, count in results.items():
        if count > 0:
            click.echo(f"  {store}: {count} removed")


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate project configuration and references."""
    try:
        config, accountant, router, hr = _load_project(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    errors = []
    warnings = []

    # Check workers referenced in scheduled tasks
    event_log = EventLog(config.project_dir / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log)
    for task in scheduler.list_tasks():
        worker_name = task.get("worker_name", "")
        worker_dir = config.project_dir / "workers" / worker_name
        if not worker_dir.exists():
            errors.append(f"Scheduled task '{task.get('id', '?')}' references missing worker '{worker_name}'")

    # Check workflow YAML files parse correctly
    workflows_dir = config.project_dir / "workflows"
    if workflows_dir.exists():
        for wf_file in sorted(workflows_dir.glob("*.yaml")):
            try:
                Workflow.load(wf_file)
            except WorkflowError as e:
                errors.append(f"Workflow '{wf_file.name}': {e}")

    if errors:
        click.echo("Errors:")
        for e in errors:
            click.echo(f"  {e}")
    if warnings:
        click.echo("Warnings:")
        for w in warnings:
            click.echo(f"  {w}")
    if not errors and not warnings:
        click.echo("Validation passed. No issues found.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    cli()
