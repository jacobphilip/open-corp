"""Tests for framework/log.py — structured logging."""

import logging

import httpx
import pytest
import respx

from framework.log import get_logger, setup_logging
from framework.router import OPENROUTER_API_URL


class TestSetupLogging:
    def test_setup_logging_default(self):
        """Returns logger at INFO level."""
        logger = setup_logging()
        assert logger.name == "open-corp"
        assert logger.level == logging.INFO

    def test_setup_logging_debug_level(self):
        """DEBUG level works."""
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG
        # Reset
        logger.setLevel(logging.INFO)

    def test_setup_logging_with_file(self, tmp_path):
        """Creates log file and adds file handler."""
        log_file = tmp_path / "logs" / "test.log"
        # Clear handlers from prior tests
        root = logging.getLogger("open-corp")
        root.handlers.clear()

        logger = setup_logging(log_file=log_file)
        assert log_file.parent.exists()
        # Should have console + file handler
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "FileHandler" in handler_types
        assert "StreamHandler" in handler_types

        # Clean up
        for h in logger.handlers[:]:
            h.close()
        root.handlers.clear()

    def test_setup_logging_idempotent(self):
        """Multiple calls don't duplicate handlers."""
        root = logging.getLogger("open-corp")
        root.handlers.clear()

        setup_logging()
        count_1 = len(root.handlers)
        setup_logging()
        count_2 = len(root.handlers)
        assert count_1 == count_2
        root.handlers.clear()


class TestGetLogger:
    def test_get_logger_naming(self):
        """Returns open-corp.{module} logger."""
        child = get_logger("framework.router")
        assert child.name == "open-corp.framework.router"


class TestIntegrationLogging:
    def test_router_logs_fallback(self, config, accountant, router, caplog):
        """Router logs when model falls back."""
        with caplog.at_level(logging.INFO, logger="open-corp"):
            with respx.mock:
                respx.post(OPENROUTER_API_URL).mock(
                    side_effect=[
                        httpx.Response(500, json={"error": "down"}),
                        httpx.Response(200, json={
                            "choices": [{"message": {"content": "ok"}}],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                        }),
                    ]
                )
                router.chat([{"role": "user", "content": "hi"}], tier="cheap")
        assert any("fallback" in r.message.lower() for r in caplog.records)

    def test_accountant_logs_warning(self, config, caplog):
        """Accountant logs when budget is non-green."""
        from framework.accountant import Accountant
        acc = Accountant(config)
        # Push to caution zone (60-80% of $3.00 = $1.80-$2.40)
        acc.record_call("m", 0, 0, 2.0, "w")
        with caplog.at_level(logging.INFO, logger="open-corp"):
            acc.pre_check()
        assert any("budget" in r.message.lower() for r in caplog.records)

    def test_workflow_logs_lifecycle(self, tmp_project, config, caplog):
        """Workflow engine logs start and completion."""
        import yaml
        from framework.accountant import Accountant
        from framework.events import EventLog
        from framework.router import Router
        from framework.workflow import Workflow, WorkflowEngine

        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        engine = WorkflowEngine(config, accountant, router, event_log,
                                db_path=tmp_project / "data" / "workflows.json")

        # Create worker
        worker_dir = tmp_project / "workers" / "alice"
        worker_dir.mkdir(parents=True, exist_ok=True)
        (worker_dir / "profile.md").write_text("# alice\nA tester.")
        (worker_dir / "memory.json").write_text("[]")
        (worker_dir / "performance.json").write_text("[]")
        (worker_dir / "skills.yaml").write_text(yaml.dump({"role": "tester", "skills": ["testing"]}))
        (worker_dir / "config.yaml").write_text(yaml.dump({"level": 1, "max_context_tokens": 2000}))

        wf = Workflow(name="log-test", description="test", nodes=[
            __import__("framework.workflow", fromlist=["WorkflowNode"]).WorkflowNode(
                id="a", worker="alice", message="hi"),
        ])

        with caplog.at_level(logging.INFO, logger="open-corp"):
            with respx.mock:
                respx.post(OPENROUTER_API_URL).mock(return_value=httpx.Response(200, json={
                    "choices": [{"message": {"content": "done"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }))
                engine.run(wf)

        messages = [r.message.lower() for r in caplog.records]
        assert any("workflow started" in m for m in messages)
        assert any("workflow completed" in m for m in messages)
