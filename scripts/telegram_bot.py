#!/usr/bin/env python3
"""Telegram bot interface for open-corp."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.exceptions import BudgetExceeded, ConfigError, ModelUnavailable, WorkerNotFound
from framework.hr import HR
from framework.router import Router
from framework.worker import Worker

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Bot starting for project: {_config.name}")
    app.run_polling()


if __name__ == "__main__":
    main()
