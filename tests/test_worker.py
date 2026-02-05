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
            response = worker.chat("help me", router)

        assert response == "I can help!"
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
            response = worker.chat("tell me about cooking", router)

        assert response == "Here's what I know about cooking."
