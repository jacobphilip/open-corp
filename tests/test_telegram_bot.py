"""Tests for scripts/telegram_bot.py bot handlers."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

import scripts.telegram_bot as bot_module
from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.hr import HR
from framework.router import Router
from framework.scheduler import Scheduler, ScheduledTask


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


def _make_callback_query(data=""):
    """Create a mock Update with callback_query for inline keyboard tests."""
    update = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    context = MagicMock()
    return update, context


class TestCmdFire:
    @pytest.mark.asyncio
    async def test_fire_no_args(self, bot_setup):
        """Reply contains 'Usage:'."""
        update, context = _make_update(args=[])
        await bot_module.cmd_fire(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "Usage:" in reply

    @pytest.mark.asyncio
    async def test_fire_worker_not_found(self, bot_setup):
        """Reply contains 'not found'."""
        update, context = _make_update(args=["ghost"])
        await bot_module.cmd_fire(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "not found" in reply

    @pytest.mark.asyncio
    async def test_fire_shows_confirm_keyboard(self, bot_setup, create_worker):
        """Shows inline keyboard with Yes/No."""
        create_worker("zara")
        update, context = _make_update(args=["zara"])
        await bot_module.cmd_fire(update, context)
        call_kwargs = update.message.reply_text.call_args
        assert "reply_markup" in call_kwargs[1]
        markup = call_kwargs[1]["reply_markup"]
        buttons = markup.inline_keyboard[0]
        assert any("fire_yes_zara" in b.callback_data for b in buttons)
        assert any("fire_no_zara" in b.callback_data for b in buttons)

    @pytest.mark.asyncio
    async def test_fire_callback_yes(self, bot_setup, create_worker):
        """Callback yes fires the worker."""
        create_worker("zara")
        update, context = _make_callback_query(data="fire_yes_zara")
        await bot_module.handle_fire_callback(update, context)
        reply = update.callback_query.edit_message_text.call_args[0][0]
        assert "Fired" in reply
        assert "zara" in reply

    @pytest.mark.asyncio
    async def test_fire_callback_no(self, bot_setup, create_worker):
        """Callback no cancels the fire."""
        create_worker("zara")
        update, context = _make_callback_query(data="fire_no_zara")
        await bot_module.handle_fire_callback(update, context)
        reply = update.callback_query.edit_message_text.call_args[0][0]
        assert "Cancelled" in reply


class TestCmdReview:
    @pytest.mark.asyncio
    async def test_review_team(self, bot_setup, create_worker):
        """Team review lists workers."""
        create_worker("alice")
        update, context = _make_update()
        await bot_module.cmd_review(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "alice" in reply

    @pytest.mark.asyncio
    async def test_review_individual(self, bot_setup, create_worker):
        """Individual review shows performance summary."""
        create_worker("alice")
        update, context = _make_update(args=["alice"])
        await bot_module.cmd_review(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "alice" in reply
        assert "Tasks:" in reply

    @pytest.mark.asyncio
    async def test_review_worker_not_found(self, bot_setup):
        """Reply contains 'not found'."""
        update, context = _make_update(args=["ghost"])
        await bot_module.cmd_review(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "not found" in reply


class TestCmdDelegate:
    @pytest.mark.asyncio
    async def test_delegate_no_args(self, bot_setup):
        """Reply contains 'Usage:'."""
        update, context = _make_update(args=[])
        await bot_module.cmd_delegate(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "Usage:" in reply

    @pytest.mark.asyncio
    async def test_delegate_routes_message(self, bot_setup, create_worker):
        """Delegates to auto-selected worker."""
        create_worker("alice", role="tester")
        update, context = _make_update(args=["run", "tests"])

        with patch("scripts.telegram_bot.Worker") as MockWorker:
            mock_instance = MockWorker.return_value
            mock_instance.chat.return_value = ("tests passed", [])
            await bot_module.cmd_delegate(update, context)

        reply = update.message.reply_text.call_args[0][0]
        assert "tests passed" in reply


class TestCmdEvents:
    @pytest.mark.asyncio
    async def test_events_empty(self, bot_setup):
        """Reply is 'No events.' when empty."""
        update, context = _make_update()
        await bot_module.cmd_events(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No events" in reply

    @pytest.mark.asyncio
    async def test_events_shows_recent(self, bot_setup):
        """Shows events after emitting one."""
        from framework.events import Event
        event_log = EventLog(bot_module._project_dir / "data" / "events.json")
        event_log.emit(Event(type="test.event", source="test"))

        update, context = _make_update()
        await bot_module.cmd_events(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "test.event" in reply


class TestCmdSchedule:
    @pytest.mark.asyncio
    async def test_schedule_empty(self, bot_setup):
        """Reply is 'No scheduled tasks.' when empty."""
        update, context = _make_update()
        await bot_module.cmd_schedule(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No scheduled tasks" in reply


class TestCmdWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_empty(self, bot_setup):
        """Reply is 'No workflow runs.' when empty."""
        update, context = _make_update()
        await bot_module.cmd_workflow(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "No workflow runs" in reply


class TestCmdInspect:
    @pytest.mark.asyncio
    async def test_inspect_project_overview(self, bot_setup):
        """Project overview shows name and budget."""
        update, context = _make_update()
        await bot_module.cmd_inspect(update, context)
        reply = update.message.reply_text.call_args[0][0]
        assert "Test Project" in reply
        assert "Budget:" in reply
