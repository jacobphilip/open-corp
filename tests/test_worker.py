"""Tests for framework/worker.py."""

import json

import httpx
import pytest
import respx
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.exceptions import WorkerNotFound
from framework.knowledge import KnowledgeBase, KnowledgeEntry
from framework.router import OPENROUTER_API_URL, Router
from framework.worker import LEVEL_TIER_MAP, Worker


def _create_worker_files(worker_dir, level=1):
    """Create minimal worker files in a directory."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text("# Test Worker\nA test worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({
        "role": "tester",
        "skills": ["testing", "validation"],
    }))
    (worker_dir / "config.yaml").write_text(yaml.dump({
        "level": level,
        "max_context_tokens": 2000,
    }))


class TestWorker:
    def test_load_worker(self, tmp_project, config):
        """Worker loads files from its directory."""
        _create_worker_files(tmp_project / "workers" / "alice")
        worker = Worker("alice", tmp_project, config)
        assert worker.name == "alice"
        assert "Test Worker" in worker.profile
        assert worker.level == 1
        assert worker.memory == []

    def test_worker_not_found(self, tmp_project, config):
        """Raises WorkerNotFound for non-existent worker."""
        with pytest.raises(WorkerNotFound, match="ghost"):
            Worker("ghost", tmp_project, config)

    def test_seniority_tier_mapping(self, tmp_project, config):
        """Level maps to correct tier."""
        for level, expected_tier in LEVEL_TIER_MAP.items():
            _create_worker_files(tmp_project / "workers" / f"w{level}", level=level)
            worker = Worker(f"w{level}", tmp_project, config)
            assert worker.get_tier() == expected_tier, f"Level {level} → {expected_tier}"

    def test_build_system_prompt(self, tmp_project, config):
        """System prompt includes profile, skills, and honest AI reminder."""
        _create_worker_files(tmp_project / "workers" / "bob")
        worker = Worker("bob", tmp_project, config)
        prompt = worker.build_system_prompt()
        assert "Test Worker" in prompt
        assert "testing" in prompt
        assert "Never fabricate" in prompt

    def test_build_system_prompt_with_memory(self, tmp_project, config):
        """System prompt includes recent memory."""
        _create_worker_files(tmp_project / "workers" / "carol")
        mem_path = tmp_project / "workers" / "carol" / "memory.json"
        mem_path.write_text(json.dumps([
            {"timestamp": "2026-01-01T00:00:00Z", "type": "note", "content": "Remember this fact"},
        ]))
        worker = Worker("carol", tmp_project, config)
        prompt = worker.build_system_prompt()
        assert "Remember this fact" in prompt

    def test_update_memory(self, tmp_project, config):
        """update_memory appends and persists."""
        _create_worker_files(tmp_project / "workers" / "dave")
        worker = Worker("dave", tmp_project, config)
        worker.update_memory("note", "learned something")
        assert len(worker.memory) == 1
        assert worker.memory[0]["content"] == "learned something"

        # Verify persistence
        saved = json.loads((tmp_project / "workers" / "dave" / "memory.json").read_text())
        assert len(saved) == 1

    def test_record_performance(self, tmp_project, config):
        """record_performance appends and persists."""
        _create_worker_files(tmp_project / "workers" / "eve")
        worker = Worker("eve", tmp_project, config)
        worker.record_performance("research task", "completed", rating=5)
        assert len(worker.performance) == 1

        saved = json.loads((tmp_project / "workers" / "eve" / "performance.json").read_text())
        assert saved[0]["rating"] == 5

    def test_chat(self, tmp_project, config):
        """chat() calls router and updates memory."""
        _create_worker_files(tmp_project / "workers" / "frank")
        worker = Worker("frank", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json={
                    "choices": [{"message": {"content": "I can help!"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                })
            )
            response, history = worker.chat("help me", router)

        assert response == "I can help!"
        assert len(history) == 2  # user msg + assistant response
        assert len(worker.memory) == 2  # user msg + response

    def test_build_system_prompt_with_knowledge(self, tmp_project, config):
        """Knowledge entries appear in system prompt."""
        _create_worker_files(tmp_project / "workers" / "kw1")
        kb_dir = tmp_project / "workers" / "kw1" / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        kb.add_entries([
            KnowledgeEntry(source="doc.txt", type="text", content="Important training knowledge about Python."),
        ])
        worker = Worker("kw1", tmp_project, config)
        prompt = worker.build_system_prompt()
        assert "Important training knowledge about Python" in prompt

    def test_build_system_prompt_knowledge_with_query(self, tmp_project, config):
        """Search narrows knowledge when query is provided."""
        _create_worker_files(tmp_project / "workers" / "kw2")
        kb_dir = tmp_project / "workers" / "kw2" / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        kb.add_entries([
            KnowledgeEntry(source="a", type="text", content="Python is great for data science."),
            KnowledgeEntry(source="b", type="text", content="JavaScript is for web development."),
        ])
        worker = Worker("kw2", tmp_project, config)
        prompt = worker.build_system_prompt(query="Python data")
        assert "Python" in prompt

    def test_build_system_prompt_no_knowledge(self, tmp_project, config):
        """Without knowledge_base dir, prompt still works (backward compat)."""
        _create_worker_files(tmp_project / "workers" / "kw3")
        worker = Worker("kw3", tmp_project, config)
        prompt = worker.build_system_prompt()
        assert "Test Worker" in prompt
        assert "Knowledge base:" not in prompt

    def test_knowledge_and_memory_budget_sharing(self, tmp_project, config):
        """Both knowledge and memory fit within budget."""
        _create_worker_files(tmp_project / "workers" / "kw4")
        # Add knowledge
        kb_dir = tmp_project / "workers" / "kw4" / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        kb.add_entries([
            KnowledgeEntry(source="doc", type="text", content="Knowledge chunk here."),
        ])
        # Add memory
        mem_path = tmp_project / "workers" / "kw4" / "memory.json"
        mem_path.write_text(json.dumps([
            {"timestamp": "2026-01-01T00:00:00Z", "type": "note", "content": "Memory entry here"},
        ]))
        worker = Worker("kw4", tmp_project, config)
        prompt = worker.build_system_prompt()
        assert "Knowledge chunk here" in prompt
        assert "Memory entry here" in prompt

    def test_chat_passes_query_to_prompt(self, tmp_project, config):
        """chat() passes the user message as query to build_system_prompt."""
        _create_worker_files(tmp_project / "workers" / "kw5")
        kb_dir = tmp_project / "workers" / "kw5" / "knowledge_base"
        kb = KnowledgeBase(kb_dir)
        kb.add_entries([
            KnowledgeEntry(source="a", type="text", content="Alpha knowledge about cooking."),
            KnowledgeEntry(source="b", type="text", content="Beta knowledge about coding."),
        ])
        worker = Worker("kw5", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json={
                    "choices": [{"message": {"content": "Here's what I know about cooking."}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                })
            )
            response, _ = worker.chat("tell me about cooking", router)

        assert response == "Here's what I know about cooking."


class TestPerformanceSummary:
    def test_performance_summary_empty(self, tmp_project, config):
        """All zeros when no performance data."""
        _create_worker_files(tmp_project / "workers" / "ps1")
        worker = Worker("ps1", tmp_project, config)
        summary = worker.performance_summary()
        assert summary["task_count"] == 0
        assert summary["avg_rating"] == 0.0
        assert summary["success_rate"] == 0.0
        assert summary["rated_count"] == 0
        assert summary["trend"] == 0.0

    def test_performance_summary_rated(self, tmp_project, config):
        """Correct avg_rating from rated tasks."""
        _create_worker_files(tmp_project / "workers" / "ps2")
        worker = Worker("ps2", tmp_project, config)
        worker.record_performance("t1", "completed", rating=4)
        worker.record_performance("t2", "completed", rating=5)
        summary = worker.performance_summary()
        assert summary["task_count"] == 2
        assert summary["avg_rating"] == 4.5
        assert summary["rated_count"] == 2

    def test_performance_summary_success_rate(self, tmp_project, config):
        """success_rate = completed count / total."""
        _create_worker_files(tmp_project / "workers" / "ps3")
        worker = Worker("ps3", tmp_project, config)
        worker.record_performance("t1", "completed", rating=5)
        worker.record_performance("t2", "failed", rating=2)
        worker.record_performance("t3", "completed", rating=4)
        summary = worker.performance_summary()
        assert summary["success_rate"] == round(2 / 3, 2)

    def test_performance_summary_trend(self, tmp_project, config):
        """Trend = second half avg minus first half avg."""
        _create_worker_files(tmp_project / "workers" / "ps4")
        worker = Worker("ps4", tmp_project, config)
        # First half: ratings 2, 2 → avg 2.0
        # Second half: ratings 4, 5 → avg 4.5
        for r in [2, 2, 4, 5]:
            worker.record_performance(f"t{r}", "completed", rating=r)
        summary = worker.performance_summary()
        assert summary["trend"] == 2.5

    def test_performance_summary_unrated(self, tmp_project, config):
        """rating=None excluded from avg."""
        _create_worker_files(tmp_project / "workers" / "ps5")
        worker = Worker("ps5", tmp_project, config)
        worker.record_performance("t1", "completed", rating=4)
        worker.record_performance("t2", "completed", rating=None)
        summary = worker.performance_summary()
        assert summary["avg_rating"] == 4.0
        assert summary["rated_count"] == 1
        assert summary["task_count"] == 2

    def test_performance_summary_few_tasks_no_trend(self, tmp_project, config):
        """Trend=0 with <4 rated tasks."""
        _create_worker_files(tmp_project / "workers" / "ps6")
        worker = Worker("ps6", tmp_project, config)
        worker.record_performance("t1", "completed", rating=5)
        worker.record_performance("t2", "completed", rating=1)
        summary = worker.performance_summary()
        assert summary["trend"] == 0.0


class TestChatHistoryTruncation:
    """Tests for chat history truncation."""

    def _mock_router_response(self, content="OK"):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def test_chat_history_truncation(self, tmp_project, config):
        """History exceeding max_history_messages is truncated to most recent."""
        config.worker_defaults.max_history_messages = 4
        _create_worker_files(tmp_project / "workers" / "trunc1")
        worker = Worker("trunc1", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        # Build a 10-message history
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(10)
        ]

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("reply"),
            )
            response, new_history = worker.chat("new msg", router, history=history)

        # Only last 4 history messages + new user msg sent (plus system)
        request_body = json.loads(route.calls[0].request.content)
        messages = request_body["messages"]
        # system + 4 truncated history + 1 new user = 6
        assert len(messages) == 6
        assert messages[1]["content"] == "msg6"  # first of last 4

    def test_chat_history_truncation_default(self, tmp_project, config):
        """Default max_history_messages=50 works without truncation for small histories."""
        assert config.worker_defaults.max_history_messages == 50
        _create_worker_files(tmp_project / "workers" / "trunc2")
        worker = Worker("trunc2", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("ok"),
            )
            worker.chat("test", router, history=history)

        request_body = json.loads(route.calls[0].request.content)
        # system + 2 history + 1 new = 4 (no truncation)
        assert len(request_body["messages"]) == 4

    def test_chat_truncation_returned_history(self, tmp_project, config):
        """Returned history reflects truncation plus new exchange."""
        config.worker_defaults.max_history_messages = 4
        _create_worker_files(tmp_project / "workers" / "trunc3")
        worker = Worker("trunc3", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(10)
        ]

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("reply"),
            )
            _, new_history = worker.chat("new", router, history=history)

        # Truncated to 4 + 2 new (user + assistant) = 6
        assert len(new_history) == 6
        assert new_history[0]["content"] == "msg6"
        assert new_history[-2]["content"] == "new"
        assert new_history[-1]["content"] == "reply"


class TestMultiTurnChat:
    """Tests for multi-turn chat and session summarization."""

    def _mock_router_response(self, content="OK"):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def test_chat_returns_tuple(self, tmp_project, config):
        """chat() returns (str, list[dict])."""
        _create_worker_files(tmp_project / "workers" / "mt1")
        worker = Worker("mt1", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=self._mock_router_response("Hi"))
            result = worker.chat("hello", router)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], list)

    def test_chat_with_history(self, tmp_project, config):
        """History messages are included in the API call."""
        _create_worker_files(tmp_project / "workers" / "mt2")
        worker = Worker("mt2", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first reply"},
        ]

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("second reply"),
            )
            response, new_history = worker.chat("second message", router, history=history)

        # Verify history was sent in the request
        request_body = json.loads(route.calls[0].request.content)
        messages = request_body["messages"]
        # system + 2 history + 1 new user = 4 messages
        assert len(messages) == 4
        assert messages[1]["content"] == "first message"
        assert messages[2]["content"] == "first reply"
        assert messages[3]["content"] == "second message"

    def test_chat_history_accumulates(self, tmp_project, config):
        """Two consecutive chats produce a 4-entry history."""
        _create_worker_files(tmp_project / "workers" / "mt3")
        worker = Worker("mt3", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    self._mock_router_response("reply1"),
                    self._mock_router_response("reply2"),
                ],
            )
            _, history = worker.chat("msg1", router)
            _, history = worker.chat("msg2", router, history=history)

        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "msg1"}
        assert history[1] == {"role": "assistant", "content": "reply1"}
        assert history[2] == {"role": "user", "content": "msg2"}
        assert history[3] == {"role": "assistant", "content": "reply2"}

    def test_chat_without_history_backward_compat(self, tmp_project, config):
        """history=None works (backward compat)."""
        _create_worker_files(tmp_project / "workers" / "mt4")
        worker = Worker("mt4", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=self._mock_router_response("OK"))
            response, history = worker.chat("test", router, history=None)

        assert response == "OK"
        assert len(history) == 2

    def test_summarize_session(self, tmp_project, config):
        """summarize_session() calls router and returns summary text."""
        _create_worker_files(tmp_project / "workers" / "mt5")
        worker = Worker("mt5", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user", "content": "What's Python?"},
            {"role": "assistant", "content": "A programming language."},
        ]

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("Discussed Python basics."),
            )
            summary = worker.summarize_session(history, router)

        assert summary == "Discussed Python basics."

    def test_summarize_session_empty_history(self, tmp_project, config):
        """Empty history returns empty string without API call."""
        _create_worker_files(tmp_project / "workers" / "mt6")
        worker = Worker("mt6", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        summary = worker.summarize_session([], router)
        assert summary == ""

    def test_summarize_session_records_memory(self, tmp_project, config):
        """Summary is stored in worker memory as 'session_summary' type."""
        _create_worker_files(tmp_project / "workers" / "mt7")
        worker = Worker("mt7", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("Brief chat."),
            )
            worker.summarize_session(history, router)

        assert len(worker.memory) == 1
        assert worker.memory[0]["type"] == "session_summary"
        assert worker.memory[0]["content"] == "Brief chat."

    def test_summarize_session_api_call(self, tmp_project, config):
        """Router is called with the conversation formatted as a summary prompt."""
        _create_worker_files(tmp_project / "workers" / "mt8")
        worker = Worker("mt8", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("Summary."),
            )
            worker.summarize_session(history, router)

        assert route.call_count == 1
        request_body = json.loads(route.calls[0].request.content)
        # The user message should contain the conversation
        user_msg = request_body["messages"][1]["content"]
        assert "Q1" in user_msg
        assert "A1" in user_msg


class TestWorkerDataIntegrity:
    """Tests for corrupted file handling and atomic writes."""

    def test_corrupted_memory_loads_empty(self, tmp_project, config):
        """Worker with corrupted memory.json loads with empty list."""
        _create_worker_files(tmp_project / "workers" / "corrupt1")
        (tmp_project / "workers" / "corrupt1" / "memory.json").write_text("{broken!!!")
        worker = Worker("corrupt1", tmp_project, config)
        assert worker.memory == []

    def test_corrupted_performance_loads_empty(self, tmp_project, config):
        """Worker with corrupted performance.json loads with empty list."""
        _create_worker_files(tmp_project / "workers" / "corrupt2")
        (tmp_project / "workers" / "corrupt2" / "performance.json").write_text("{also broken")
        worker = Worker("corrupt2", tmp_project, config)
        assert worker.performance == []

    def test_atomic_write_produces_valid_json(self, tmp_project, config):
        """Multiple memory writes produce valid JSON on disk."""
        _create_worker_files(tmp_project / "workers" / "atomic1")
        worker = Worker("atomic1", tmp_project, config)
        for i in range(5):
            worker.update_memory("note", f"entry-{i}")
        # Re-read from disk
        saved = json.loads((tmp_project / "workers" / "atomic1" / "memory.json").read_text())
        assert len(saved) == 5
        assert saved[-1]["content"] == "entry-4"


class TestWorkerTools:
    """Tests for tool integration in Worker.chat()."""

    def _mock_router_response(self, content="OK"):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def test_tools_disabled_uses_plain_chat(self, tmp_project, config):
        """When tools.enabled=False, uses plain router.chat() path."""
        config.tools.enabled = False
        _create_worker_files(tmp_project / "workers" / "t1")
        worker = Worker("t1", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("plain")
            )
            response, _ = worker.chat("hi", router)

        assert response == "plain"
        # Verify no tools in payload
        request_body = json.loads(route.calls[0].request.content)
        assert "tools" not in request_body

    def test_l1_gets_safe_tools_only(self, tmp_project, config):
        """L1 worker only gets safe-tier tools."""
        config.tools.enabled = True
        _create_worker_files(tmp_project / "workers" / "t2", level=1)
        worker = Worker("t2", tmp_project, config)

        from framework.plugins import create_default_registry
        registry = create_default_registry()
        available = registry.resolve_for_worker(worker.level, None)
        tool_names = {t.name for t in available}
        assert "calculator" in tool_names
        assert "current_time" in tool_names
        assert "shell_exec" not in tool_names
        assert "python_eval" not in tool_names
        assert "web_search" not in tool_names

    def test_l4_gets_all_tools(self, tmp_project, config):
        """L4 worker gets all 9 tools."""
        _create_worker_files(tmp_project / "workers" / "t3", level=4)
        worker = Worker("t3", tmp_project, config)

        from framework.plugins import create_default_registry
        registry = create_default_registry()
        available = registry.resolve_for_worker(worker.level, None)
        assert len(available) == 9

    def test_explicit_tool_list(self, tmp_project, config):
        """Worker config.yaml tools list restricts available tools."""
        config.tools.enabled = True
        _create_worker_files(tmp_project / "workers" / "t4", level=3)
        # Override config to only allow calculator
        cfg_path = tmp_project / "workers" / "t4" / "config.yaml"
        cfg_path.write_text(yaml.dump({
            "level": 3,
            "max_context_tokens": 2000,
            "tools": ["calculator", "web_search"],
        }))
        worker = Worker("t4", tmp_project, config)

        from framework.plugins import create_default_registry
        registry = create_default_registry()
        explicit = worker.worker_config.get("tools")
        available = registry.resolve_for_worker(worker.level, explicit)
        tool_names = {t.name for t in available}
        assert tool_names == {"calculator", "web_search"}

    def test_tool_enabled_chat_uses_tool_loop(self, tmp_project, config):
        """With tools enabled and available, chat() uses tool_loop path."""
        config.tools.enabled = True
        _create_worker_files(tmp_project / "workers" / "t5", level=1)
        worker = Worker("t5", tmp_project, config)
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(
                return_value=self._mock_router_response("tool reply")
            )
            response, history = worker.chat("hi", router)

        assert response == "tool reply"
        # Tools should be in the payload (L1 has safe tools)
        request_body = json.loads(route.calls[0].request.content)
        assert "tools" in request_body
