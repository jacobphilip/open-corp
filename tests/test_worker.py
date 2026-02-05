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
