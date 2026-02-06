#!/usr/bin/env python3
"""Telegram bot interface for open-corp."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.exceptions import BudgetExceeded, ConfigError, ModelUnavailable, ValidationError, WorkerNotFound
from framework.housekeeping import Housekeeper
from framework.hr import HR
from framework.router import Router
from framework.scheduler import Scheduler
from framework.task_router import TaskRouter
from framework.validation import validate_worker_name
from framework.worker import Worker
from framework.workflow import WorkflowEngine

logger = logging.getLogger(__name__)

# Per-user active worker state (resets on restart)
_user_workers: dict[int, str] = {}


def _load_project(project_dir: Path) -> tuple[ProjectConfig, Accountant, Router, HR]:
    config = ProjectConfig.load(project_dir)
    accountant = Accountant(config)
    router = Router(config, accountant)
    hr = HR(config, project_dir)
    return config, accountant, router, hr


# Store project components at module level (initialized in main)
_config: ProjectConfig | None = None
_accountant: Accountant | None = None
_router: Router | None = None
_hr: HR | None = None
_project_dir: Path | None = None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    worker_list = _hr.list_workers()
    if worker_list:
        names = ", ".join(w["name"] for w in worker_list)
        text = (
            f"Welcome to {_config.name}!\n\n"
            f"Available workers: {names}\n\n"
            f"Use /chat <worker_name> to start chatting.\n"
            f"Use /workers for details.\n"
            f"Use /status for project info."
        )
    else:
        text = (
            f"Welcome to {_config.name}!\n\n"
            f"No workers hired yet. Hire workers via the CLI first:\n"
            f"  corp hire <template> <name>"
        )
    await update.message.reply_text(text)


async def cmd_workers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /workers command."""
    worker_list = _hr.list_workers()
    if not worker_list:
        await update.message.reply_text("No workers hired yet.")
        return

    seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
    lines = []
    for w in worker_list:
        title = seniority.get(w["level"], f"L{w['level']}")
        lines.append(f"• {w['name']} — {title} — {w['role']}")

    await update.message.reply_text("Workers:\n" + "\n".join(lines))


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /chat <worker_name> — set active worker for this user."""
    if not context.args:
        await update.message.reply_text("Usage: /chat <worker_name>")
        return

    worker_name = context.args[0]
    try:
        validate_worker_name(worker_name)
    except ValidationError:
        await update.message.reply_text("Invalid worker name. Use letters, numbers, hyphens, underscores.")
        return

    worker_dir = _project_dir / "workers" / worker_name
    if not worker_dir.exists():
        await update.message.reply_text(
            f"Worker '{worker_name}' not found. Use /workers to see available workers."
        )
        return

    user_id = update.effective_user.id
    _user_workers[user_id] = worker_name
    await update.message.reply_text(f"Now chatting with {worker_name}. Send a message!")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    report = _accountant.daily_report()
    text = (
        f"Project: {_config.name}\n"
        f"Owner: {_config.owner}\n"
        f"Budget: ${report['total_spent']:.4f} / ${report['daily_limit']:.2f} "
        f"({report['usage_ratio']:.0%})\n"
        f"Status: {report['status']}\n"
        f"Calls today: {report['call_count']}"
    )
    await update.message.reply_text(text)


async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /budget command."""
    report = _accountant.daily_report()
    lines = [
        f"Date: {report['date']}",
        f"Spent: ${report['total_spent']:.4f} / ${report['daily_limit']:.2f}",
        f"Remaining: ${report['remaining']:.4f}",
        f"Status: {report['status']}",
        f"Calls: {report['call_count']}",
        f"Tokens: {report['total_tokens_in']} in / {report['total_tokens_out']} out",
    ]
    if report["by_worker"]:
        lines.append("\nBy worker:")
        for w, cost in sorted(report["by_worker"].items()):
            lines.append(f"  {w}: ${cost:.4f}")
    await update.message.reply_text("\n".join(lines))


async def cmd_fire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /fire <worker_name> — confirm via inline keyboard."""
    if not context.args:
        await update.message.reply_text("Usage: /fire <worker_name>")
        return

    worker_name = context.args[0]
    try:
        validate_worker_name(worker_name)
    except ValidationError:
        await update.message.reply_text("Invalid worker name.")
        return

    worker_dir = _project_dir / "workers" / worker_name
    if not worker_dir.exists():
        await update.message.reply_text(f"Worker '{worker_name}' not found.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, fire", callback_data=f"fire_yes_{worker_name}"),
            InlineKeyboardButton("Cancel", callback_data=f"fire_no_{worker_name}"),
        ]
    ])
    await update.message.reply_text(
        f"Fire '{worker_name}'? This deletes all worker data.",
        reply_markup=keyboard,
    )


async def handle_fire_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle fire confirmation callback."""
    query = update.callback_query
    await query.answer()

    data = query.data  # "fire_yes_<name>" or "fire_no_<name>"
    parts = data.split("_", 2)
    action = parts[1]
    worker_name = parts[2]

    if action == "no":
        await query.edit_message_text(f"Cancelled firing '{worker_name}'.")
        return

    event_log = EventLog(_project_dir / "data" / "events.json")
    scheduler = Scheduler(_config, _accountant, _router, event_log)

    try:
        result = _hr.fire(worker_name, confirm=True, scheduler=scheduler)
    except WorkerNotFound:
        await query.edit_message_text(f"Worker '{worker_name}' not found.")
        return

    lines = [f"Fired '{worker_name}'."]
    if result["removed_tasks"] > 0:
        lines.append(f"Removed {result['removed_tasks']} scheduled task(s).")
    for warning in result["warnings"]:
        lines.append(f"Warning: {warning}")
    await query.edit_message_text("\n".join(lines))


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /review [worker_name] — team scorecard or individual."""
    if context.args:
        worker_name = context.args[0]
        try:
            validate_worker_name(worker_name)
        except ValidationError:
            await update.message.reply_text("Invalid worker name.")
            return
        worker_dir = _project_dir / "workers" / worker_name
        if not worker_dir.exists():
            await update.message.reply_text(f"Worker '{worker_name}' not found.")
            return
        worker = Worker(worker_name, _project_dir, _config)
        summary = worker.performance_summary()
        text = (
            f"{worker_name}:\n"
            f"  Tasks: {summary['task_count']}\n"
            f"  Avg rating: {summary['avg_rating']}\n"
            f"  Success rate: {summary['success_rate']:.0%}\n"
            f"  Trend: {summary['trend']:+.2f}"
        )
        await update.message.reply_text(text)
    else:
        results = _hr.team_review()
        if not results:
            await update.message.reply_text("No workers to review.")
            return
        seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
        lines = []
        for r in results[:10]:
            title = seniority.get(r["level"], f"L{r['level']}")
            lines.append(f"  {r['name']} — {title} — avg {r['avg_rating']} ({r['task_count']} tasks)")
        await update.message.reply_text("Team review:\n" + "\n".join(lines))


async def cmd_delegate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delegate <message> — auto-select worker."""
    if not context.args:
        await update.message.reply_text("Usage: /delegate <message>")
        return

    message = " ".join(context.args)
    task_router = TaskRouter(_config, _hr)
    selected = task_router.select_worker(message)
    if selected is None:
        await update.message.reply_text("No workers available.")
        return

    try:
        worker = Worker(selected, _project_dir, _config)
        response, _ = await asyncio.to_thread(worker.chat, message, _router)
        await update.message.reply_text(f"{selected}: {response}")
    except BudgetExceeded as e:
        await update.message.reply_text(f"Budget exceeded: {e}")
    except ModelUnavailable as e:
        await update.message.reply_text(f"Model unavailable: {e}")


async def cmd_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /events [limit] — recent events."""
    limit = 10
    if context.args:
        try:
            limit = int(context.args[0])
        except ValueError:
            pass

    event_log = EventLog(_project_dir / "data" / "events.json")
    results = event_log.query(limit=limit)
    if not results:
        await update.message.reply_text("No events.")
        return

    lines = []
    for e in results[:10]:
        lines.append(f"[{e['timestamp'][:19]}] {e['type']} — {e['source']}")
    await update.message.reply_text("Recent events:\n" + "\n".join(lines))


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /schedule — list scheduled tasks."""
    event_log = EventLog(_project_dir / "data" / "events.json")
    scheduler = Scheduler(_config, _accountant, _router, event_log)
    tasks = scheduler.list_tasks()
    if not tasks:
        await update.message.reply_text("No scheduled tasks.")
        return

    lines = []
    for t in tasks:
        status = "enabled" if t.get("enabled", True) else "disabled"
        lines.append(f"  {t['id']} — {t['worker_name']} — {t['schedule_type']}={t['schedule_value']} ({status})")
    await update.message.reply_text("Scheduled tasks:\n" + "\n".join(lines))


async def cmd_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /workflow — recent workflow runs."""
    event_log = EventLog(_project_dir / "data" / "events.json")
    engine = WorkflowEngine(_config, _accountant, _router, event_log)
    runs = engine.list_runs()
    if not runs:
        await update.message.reply_text("No workflow runs.")
        return

    lines = []
    for r in runs[-10:]:
        lines.append(f"  {r['id']} — {r['workflow_name']} — {r['status']} ({r.get('started_at', '')[:19]})")
    await update.message.reply_text("Recent workflows:\n" + "\n".join(lines))


async def cmd_inspect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /inspect [worker_name] — project overview or worker detail."""
    if context.args:
        worker_name = context.args[0]
        try:
            validate_worker_name(worker_name)
        except ValidationError:
            await update.message.reply_text("Invalid worker name.")
            return
        worker_dir = _project_dir / "workers" / worker_name
        if not worker_dir.exists():
            await update.message.reply_text(f"Worker '{worker_name}' not found.")
            return
        worker = Worker(worker_name, _project_dir, _config)
        seniority = {1: "Intern", 2: "Junior", 3: "Mid", 4: "Senior", 5: "Principal"}
        title = seniority.get(worker.level, f"L{worker.level}")
        text = (
            f"{worker_name}:\n"
            f"  Level: {title} (L{worker.level}, tier={worker.get_tier()})\n"
            f"  Memory: {len(worker.memory)} entries\n"
            f"  Knowledge: {len(worker.knowledge.entries)} entries\n"
            f"  Tasks: {len(worker.performance)}"
        )
        await update.message.reply_text(text)
    else:
        report = _accountant.daily_report()
        worker_list = _hr.list_workers()
        text = (
            f"Project: {_config.name}\n"
            f"Budget: ${report['total_spent']:.4f} / ${report['daily_limit']:.2f} ({report['status']})\n"
            f"Workers: {len(worker_list)}"
        )
        await update.message.reply_text(text)


async def cmd_housekeep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /housekeep — run data cleanup."""
    hk = Housekeeper(_project_dir, _config.retention)
    results = await asyncio.to_thread(hk.run_all)
    total = sum(results.values())
    lines = [f"Housekeeping complete: {total} records removed"]
    for store, count in results.items():
        if count > 0:
            lines.append(f"  {store}: {count} removed")
    await update.message.reply_text("\n".join(lines))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route plain messages to the user's active worker."""
    user_id = update.effective_user.id
    worker_name = _user_workers.get(user_id)

    if not worker_name:
        await update.message.reply_text(
            "No active worker. Use /chat <worker_name> to select one."
        )
        return

    try:
        worker = Worker(worker_name, _project_dir, _config)
    except WorkerNotFound:
        await update.message.reply_text(f"Worker '{worker_name}' no longer exists.")
        _user_workers.pop(user_id, None)
        return

    user_text = update.message.text
    try:
        response, _ = await asyncio.to_thread(worker.chat, user_text, _router)
        await update.message.reply_text(response)
    except BudgetExceeded as e:
        await update.message.reply_text(f"Budget exceeded: {e}")
    except ModelUnavailable as e:
        await update.message.reply_text(f"Model unavailable: {e}")
    except Exception as e:
        logger.exception("Error in worker chat")
        await update.message.reply_text(f"Error: {e}")


def main(project_dir: Path | None = None) -> None:
    """Start the Telegram bot."""
    global _config, _accountant, _router, _hr, _project_dir

    if project_dir is None:
        project_dir = Path.cwd()
    _project_dir = project_dir

    try:
        _config, _accountant, _router, _hr = _load_project(project_dir)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set in .env", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("workers", cmd_workers))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("budget", cmd_budget))
    app.add_handler(CommandHandler("fire", cmd_fire))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("delegate", cmd_delegate))
    app.add_handler(CommandHandler("events", cmd_events))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("workflow", cmd_workflow))
    app.add_handler(CommandHandler("inspect", cmd_inspect))
    app.add_handler(CommandHandler("housekeep", cmd_housekeep))
    app.add_handler(CallbackQueryHandler(handle_fire_callback, pattern="^fire_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Bot starting for project: {_config.name}")
    app.run_polling()


if __name__ == "__main__":
    main()
