#!/usr/bin/env python3
"""corp — CLI for managing your open-corp project."""

import sys
from pathlib import Path

import click

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.exceptions import BudgetExceeded, ConfigError, ModelUnavailable, TrainingError, WorkerNotFound
from framework.hr import HR
from framework.router import Router
from framework.worker import Worker


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

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            click.echo("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            click.echo("Bye.")
            break

        try:
            response = worker.chat(user_input, router)
            click.echo(f"\n{worker_name}: {response}\n")
        except BudgetExceeded as e:
            click.echo(f"\nBudget exceeded: {e}\n", err=True)
        except ModelUnavailable as e:
            click.echo(f"\nModel unavailable: {e}\n", err=True)
        except Exception as e:
            click.echo(f"\nError: {e}\n", err=True)


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


if __name__ == "__main__":
    cli()
