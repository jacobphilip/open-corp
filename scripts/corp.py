#!/usr/bin/env python3
"""corp — CLI for managing your open-corp project."""

import json
import sys
from pathlib import Path

import click
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.exceptions import (
    BudgetExceeded, ConfigError, ModelUnavailable, SchedulerError,
    TrainingError, WorkerNotFound, WorkflowError,
)
from framework.hr import HR
from framework.router import Router
from framework.scheduler import Scheduler, ScheduledTask
from framework.worker import Worker
from framework.workflow import Workflow, WorkflowEngine


def _load_project(project_dir: Path | None = None) -> tuple[ProjectConfig, Accountant, Router, HR]:
    """Load all project components from the given (or current) directory."""
    if project_dir is None:
        project_dir = Path.cwd()
    config = ProjectConfig.load(project_dir)
    accountant = Accountant(config)
    router = Router(config, accountant)
    hr = HR(config, project_dir)
    return config, accountant, router, hr


@click.group()
@click.option("--project-dir", type=click.Path(exists=True, path_type=Path), default=None,
              help="Project directory (defaults to cwd)")
@click.pass_context
def cli(ctx, project_dir):
    """open-corp — AI-powered operations with specialist workers."""
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = project_dir


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

    click.echo(f"\nProject '{name}' initialized in {project_dir}")
    click.echo("Created: charter.yaml, .env, workers/, templates/, data/")


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


# --- Daemon command ---

@cli.command()
@click.pass_context
def daemon(ctx):
    """Start the scheduler daemon (foreground, Ctrl+C to stop)."""
    try:
        config, accountant, router, _, event_log = _load_project_full(ctx.obj["project_dir"])
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)

    scheduler = Scheduler(config, accountant, router, event_log)
    tasks = scheduler.list_tasks()
    enabled = [t for t in tasks if t.get("enabled", True)]

    if not enabled:
        click.echo("No enabled scheduled tasks. Add tasks with: corp schedule add")
        return

    click.echo(f"Starting daemon with {len(enabled)} task(s)...")
    scheduler.start()

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        scheduler.stop()
        click.echo("Daemon stopped.")


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


if __name__ == "__main__":
    cli()
