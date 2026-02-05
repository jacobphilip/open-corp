"""Tests for scripts/telegram_bot.py bot handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

import scripts.telegram_bot as bot_module
from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.hr import HR
from framework.router import Router


@pytest.fixture
def bot_setup(tmp_project, config, accountant):
    """Set module-level globals so handlers can work."""
    hr = HR(config, tmp_project)
    router = Router(config, accountant, api_key="test-key")

    bot_module._config = config
    bot_module._accountant = accountant
    bot_module._router = router
    bot_module._hr = hr
    bot_module._project_dir = tmp_project
    bot_module._user_workers.clear()

    yield

    # Cleanup
    bot_module._config = None
    bot_module._accountant = None
    bot_module._router = None
    bot_module._hr = None
    bot_module._project_dir = None
    bot_module._user_workers.clear()


def _make_update(user_id=1, text="", args=None):
    """Create a mock Update with message.reply_text as AsyncMock."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.args = args or []

    return update, context


class TestCmdStart:
    @pytest.mark.asyncio
    async def test_start_with_workers(self, bot_setup, create_worker):
        """Reply contains worker names."""
        create_worker("alice")
        update, context = _make_update()

        await bot_module.cmd_start(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "alice" in reply
        assert "Test Project" in reply

    @pytest.mark.asyncio
    async def test_start_no_workers(self, bot_setup):
        """Reply contains 'No workers hired yet'."""
        update, context = _make_update()

        await bot_module.cmd_start(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "No workers hired yet" in reply


class TestCmdWorkers:
    @pytest.mark.asyncio
    async def test_workers_lists_all(self, bot_setup, create_worker):
        """Reply contains names + seniority."""
        create_worker("bob", level=3, role="analyst")
        update, context = _make_update()

        await bot_module.cmd_workers(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "bob" in reply
        assert "Mid" in reply

    @pytest.mark.asyncio
    async def test_workers_empty(self, bot_setup):
        """'No workers hired yet' when empty."""
        update, context = _make_update()

        await bot_module.cmd_workers(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "No workers hired yet" in reply


class TestCmdChat:
    @pytest.mark.asyncio
    async def test_chat_selects_worker(self, bot_setup, create_worker):
        """Sets _user_workers, reply confirms."""
        create_worker("carol")
        update, context = _make_update(user_id=42, args=["carol"])

        await bot_module.cmd_chat(update, context)

        assert bot_module._user_workers[42] == "carol"
        reply = update.message.reply_text.call_args[0][0]
        assert "carol" in reply

    @pytest.mark.asyncio
    async def test_chat_no_args(self, bot_setup):
        """Reply contains 'Usage:'."""
        update, context = _make_update(args=[])

        await bot_module.cmd_chat(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "Usage:" in reply

    @pytest.mark.asyncio
    async def test_chat_worker_not_found(self, bot_setup):
        """Reply contains 'not found'."""
        update, context = _make_update(args=["ghost"])

        await bot_module.cmd_chat(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "not found" in reply


class TestCmdStatus:
    @pytest.mark.asyncio
    async def test_status_shows_info(self, bot_setup):
        """Reply contains project name + budget."""
        update, context = _make_update()

        await bot_module.cmd_status(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "Test Project" in reply
        assert "Budget:" in reply


class TestCmdBudget:
    @pytest.mark.asyncio
    async def test_budget_shows_report(self, bot_setup):
        """Reply contains Spent/Remaining."""
        update, context = _make_update()

        await bot_module.cmd_budget(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "Spent:" in reply
        assert "Remaining:" in reply


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_message_no_active_worker(self, bot_setup):
        """'No active worker' when user hasn't selected one."""
        update, context = _make_update(user_id=99, text="hello")

        await bot_module.handle_message(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "No active worker" in reply

    @pytest.mark.asyncio
    async def test_message_routes_to_worker(self, bot_setup, create_worker):
        """Patches Worker.chat, verifies reply matches worker response."""
        create_worker("dave")
        bot_module._user_workers[7] = "dave"

        update, context = _make_update(user_id=7, text="what is 2+2?")

        with patch("scripts.telegram_bot.Worker") as MockWorker:
            mock_instance = MockWorker.return_value
            mock_instance.chat.return_value = ("4", [])

            await bot_module.handle_message(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "4" in reply
