"""Tests for framework/workflow.py — DAG workflow engine."""

import json
import logging
import time
from unittest.mock import patch

import httpx
import pytest
import respx
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.exceptions import WorkflowError
from framework.router import OPENROUTER_API_URL, Router
from framework.workflow import (
    Workflow, WorkflowEngine, WorkflowNode,
    _check_condition, _compute_depths, _substitute_outputs, topological_sort,
)


def _create_worker_files(worker_dir, level=1):
    """Create minimal worker files."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text("# Test Worker\nA test worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({"role": "tester", "skills": ["testing"]}))
    (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))


def _mock_response(content="OK"):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })


@pytest.fixture
def workflow_env(tmp_project, config):
    """Set up workflow engine with all dependencies."""
    accountant = Accountant(config)
    router = Router(config, accountant, api_key="test-key")
    event_log = EventLog(tmp_project / "data" / "events.json")
    engine = WorkflowEngine(config, accountant, router, event_log,
                            db_path=tmp_project / "data" / "workflows.json")
    _create_worker_files(tmp_project / "workers" / "researcher")
    _create_worker_files(tmp_project / "workers" / "writer")
    return engine, event_log, tmp_project


class TestWorkflowLoad:
    def test_load_workflow_yaml(self, tmp_path):
        """Valid YAML produces a Workflow with correct nodes."""
        wf_path = tmp_path / "pipeline.yaml"
        wf_path.write_text(yaml.dump({
            "name": "test-pipeline",
            "description": "A test",
            "nodes": {
                "step1": {"worker": "researcher", "message": "research"},
                "step2": {"worker": "writer", "message": "write", "depends_on": ["step1"]},
            },
        }))
        wf = Workflow.load(wf_path)
        assert wf.name == "test-pipeline"
        assert len(wf.nodes) == 2
        assert wf.nodes[1].depends_on == ["step1"]

    def test_load_workflow_missing_file(self, tmp_path):
        """Missing file raises WorkflowError."""
        with pytest.raises(WorkflowError, match="not found"):
            Workflow.load(tmp_path / "nope.yaml")

    def test_load_workflow_no_nodes(self, tmp_path):
        """Empty nodes raises WorkflowError."""
        wf_path = tmp_path / "empty.yaml"
        wf_path.write_text(yaml.dump({"name": "empty", "nodes": {}}))
        with pytest.raises(WorkflowError, match="no nodes"):
            Workflow.load(wf_path)

    def test_load_workflow_missing_worker(self, tmp_path):
        """Node without worker field raises WorkflowError."""
        wf_path = tmp_path / "bad.yaml"
        wf_path.write_text(yaml.dump({
            "name": "bad",
            "nodes": {"step1": {"message": "no worker"}},
        }))
        with pytest.raises(WorkflowError, match="worker"):
            Workflow.load(wf_path)


class TestTopologicalSort:
    def test_topological_sort_linear(self):
        """A→B→C sorts correctly."""
        nodes = [
            WorkflowNode(id="c", worker="w", message="", depends_on=["b"]),
            WorkflowNode(id="b", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="a", worker="w", message=""),
        ]
        sorted_ids = [n.id for n in topological_sort(nodes)]
        assert sorted_ids.index("a") < sorted_ids.index("b")
        assert sorted_ids.index("b") < sorted_ids.index("c")

    def test_topological_sort_diamond(self):
        """Fan-out/fan-in: A→(B,C)→D."""
        nodes = [
            WorkflowNode(id="a", worker="w", message=""),
            WorkflowNode(id="b", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="c", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="d", worker="w", message="", depends_on=["b", "c"]),
        ]
        sorted_ids = [n.id for n in topological_sort(nodes)]
        assert sorted_ids.index("a") < sorted_ids.index("b")
        assert sorted_ids.index("a") < sorted_ids.index("c")
        assert sorted_ids.index("b") < sorted_ids.index("d")
        assert sorted_ids.index("c") < sorted_ids.index("d")

    def test_topological_sort_cycle(self):
        """Cycle raises WorkflowError."""
        nodes = [
            WorkflowNode(id="a", worker="w", message="", depends_on=["b"]),
            WorkflowNode(id="b", worker="w", message="", depends_on=["a"]),
        ]
        with pytest.raises(WorkflowError, match="Cycle"):
            topological_sort(nodes)


class TestHelpers:
    def test_substitute_outputs(self):
        """{node_id.output} replaced with actual output."""
        node_results = {"research": {"status": "completed", "output": "AI safety findings"}}
        msg = "Write about: {research.output}"
        result = _substitute_outputs(msg, node_results)
        assert result == "Write about: AI safety findings"

    def test_check_condition_success(self):
        """All deps completed → True."""
        node_results = {
            "a": {"status": "completed", "output": "ok"},
            "b": {"status": "completed", "output": "ok"},
        }
        assert _check_condition("success", ["a", "b"], node_results) is True

    def test_check_condition_contains(self):
        """Keyword in dep output → True."""
        node_results = {"a": {"status": "completed", "output": "AI safety is important"}}
        assert _check_condition("contains:AI safety", ["a"], node_results) is True
        assert _check_condition("contains:blockchain", ["a"], node_results) is False


class TestWorkflowEngine:
    def test_run_simple_workflow(self, workflow_env):
        """Two independent nodes, both complete."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="simple", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="do A"),
            WorkflowNode(id="b", worker="writer", message="do B"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(side_effect=[
                _mock_response("result A"),
                _mock_response("result B"),
            ])
            run = engine.run(wf)

        assert run.status == "completed"
        assert run.node_results["a"]["status"] == "completed"
        assert run.node_results["b"]["status"] == "completed"

    def test_run_with_dependency(self, workflow_env):
        """Node B uses {A.output}, substitution verified."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="chain", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="research"),
            WorkflowNode(id="b", worker="writer", message="Write about: {a.output}",
                         depends_on=["a"]),
        ])

        with respx.mock:
            route = respx.post(OPENROUTER_API_URL).mock(side_effect=[
                _mock_response("findings about AI"),
                _mock_response("article draft"),
            ])
            run = engine.run(wf)

        assert run.status == "completed"
        # Verify second call received substituted message
        second_call_body = json.loads(route.calls[1].request.content)
        user_msg = second_call_body["messages"][-1]["content"]
        assert "findings about AI" in user_msg

    def test_run_node_failure_skips_downstream(self, workflow_env):
        """A fails → B (depends_on A, condition=success) is skipped."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="fail", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="fail"),
            WorkflowNode(id="b", worker="writer", message="write",
                         depends_on=["a"], condition="success"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(500, json={"error": "boom"})
            )
            run = engine.run(wf)

        assert run.status == "failed"
        assert run.node_results["a"]["status"] == "failed"
        assert run.node_results["b"]["status"] == "skipped"

    def test_run_persists_result(self, workflow_env):
        """WorkflowRun is stored in TinyDB."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="persist", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="go"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            run = engine.run(wf)

        stored = engine.get_run(run.id)
        assert stored is not None
        assert stored["workflow_name"] == "persist"
        assert stored["status"] == "completed"

        # list_runs also works
        all_runs = engine.list_runs()
        assert len(all_runs) == 1
        filtered = engine.list_runs(workflow_name="persist")
        assert len(filtered) == 1


class TestComputeDepths:
    def test_compute_depths_single(self):
        """Single node gets depth 0."""
        nodes = [WorkflowNode(id="a", worker="w", message="")]
        depths = _compute_depths(nodes)
        assert depths == {"a": 0}

    def test_compute_depths_chain(self):
        """A→B→C → depths 0, 1, 2."""
        nodes = [
            WorkflowNode(id="a", worker="w", message=""),
            WorkflowNode(id="b", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="c", worker="w", message="", depends_on=["b"]),
        ]
        depths = _compute_depths(nodes)
        assert depths == {"a": 0, "b": 1, "c": 2}

    def test_compute_depths_diamond(self):
        """A→(B,C)→D → B,C at depth 1, D at depth 2."""
        nodes = [
            WorkflowNode(id="a", worker="w", message=""),
            WorkflowNode(id="b", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="c", worker="w", message="", depends_on=["a"]),
            WorkflowNode(id="d", worker="w", message="", depends_on=["b", "c"]),
        ]
        depths = _compute_depths(nodes)
        assert depths["a"] == 0
        assert depths["b"] == 1
        assert depths["c"] == 1
        assert depths["d"] == 2


class TestParallelExecution:
    def test_parallel_two_independent(self, workflow_env):
        """A, B (no deps) run, both complete."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="parallel", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="do A"),
            WorkflowNode(id="b", worker="writer", message="do B"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(side_effect=[
                _mock_response("result A"),
                _mock_response("result B"),
            ])
            run = engine.run(wf)

        assert run.status == "completed"
        assert run.node_results["a"]["status"] == "completed"
        assert run.node_results["b"]["status"] == "completed"

    def test_parallel_diamond_dag(self, workflow_env):
        """A→(B,C)→D: B and C same depth, run in parallel."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="diamond", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="start"),
            WorkflowNode(id="b", worker="researcher", message="use {a.output}", depends_on=["a"]),
            WorkflowNode(id="c", worker="writer", message="use {a.output}", depends_on=["a"]),
            WorkflowNode(id="d", worker="researcher", message="combine {b.output} {c.output}",
                         depends_on=["b", "c"]),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(side_effect=[
                _mock_response("A result"),
                _mock_response("B result"),
                _mock_response("C result"),
                _mock_response("D result"),
            ])
            run = engine.run(wf)

        assert run.status == "completed"
        for nid in ("a", "b", "c", "d"):
            assert run.node_results[nid]["status"] == "completed"

    def test_parallel_with_failure(self, workflow_env):
        """Failed node skips downstream (same as sequential)."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="fail", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="fail"),
            WorkflowNode(id="b", worker="writer", message="write",
                         depends_on=["a"], condition="success"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(500, json={"error": "boom"})
            )
            run = engine.run(wf)

        assert run.status == "failed"
        assert run.node_results["a"]["status"] == "failed"
        assert run.node_results["b"]["status"] == "skipped"

    def test_parallel_max_workers(self, workflow_env):
        """max_workers=1 forces sequential execution (same result)."""
        engine, event_log, tmp_project = workflow_env
        wf = Workflow(name="serial", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="do A"),
            WorkflowNode(id="b", worker="writer", message="do B"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(side_effect=[
                _mock_response("result A"),
                _mock_response("result B"),
            ])
            run = engine.run(wf, max_workers=1)

        assert run.status == "completed"
        assert len(run.node_results) == 2


class TestWorkflowNodeTimeoutRetries:
    def test_node_timeout_default(self):
        """Default timeout is 300."""
        node = WorkflowNode(id="a", worker="w", message="hi")
        assert node.timeout == 300

    def test_node_timeout_from_yaml(self, tmp_path):
        """Parsed from YAML."""
        wf_path = tmp_path / "wf.yaml"
        wf_path.write_text(yaml.dump({
            "name": "timeout-test",
            "nodes": {"step1": {"worker": "w", "message": "hi", "timeout": 120}},
        }))
        wf = Workflow.load(wf_path)
        assert wf.nodes[0].timeout == 120

    def test_node_retries_default(self):
        """Default retries is 0."""
        node = WorkflowNode(id="a", worker="w", message="hi")
        assert node.retries == 0

    def test_node_retries_from_yaml(self, tmp_path):
        """Parsed from YAML."""
        wf_path = tmp_path / "wf.yaml"
        wf_path.write_text(yaml.dump({
            "name": "retry-test",
            "nodes": {"step1": {"worker": "w", "message": "hi", "retries": 3}},
        }))
        wf = Workflow.load(wf_path)
        assert wf.nodes[0].retries == 3

    def test_workflow_timeout_default(self):
        """Default workflow timeout is 0 (unlimited)."""
        wf = Workflow(name="test", description="", nodes=[])
        assert wf.timeout == 0

    def test_workflow_timeout_from_yaml(self, tmp_path):
        """Parsed from YAML."""
        wf_path = tmp_path / "wf.yaml"
        wf_path.write_text(yaml.dump({
            "name": "wf-timeout",
            "timeout": 600,
            "nodes": {"step1": {"worker": "w", "message": "hi"}},
        }))
        wf = Workflow.load(wf_path)
        assert wf.timeout == 600

    def test_node_timeout_triggers(self, workflow_env):
        """Slow worker times out → failed."""
        engine, event_log, tmp_project = workflow_env

        def slow_chat(*args, **kwargs):
            time.sleep(5)
            return ("result", [])

        wf = Workflow(name="timeout", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="slow",
                         timeout=1, retries=0),
        ])

        with patch("framework.worker.Worker.chat", side_effect=slow_chat):
            run = engine.run(wf)

        assert run.status == "failed"
        assert run.node_results["a"]["status"] == "failed"
        assert "timed out" in run.node_results["a"]["error"]

    def test_node_retry_success(self, workflow_env):
        """First attempt fails, second succeeds."""
        engine, event_log, tmp_project = workflow_env
        call_count = [0]

        wf = Workflow(name="retry-ok", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="retry me",
                         timeout=300, retries=1),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(side_effect=[
                httpx.Response(500, json={"error": "temporary"}),
                _mock_response("success"),
            ])
            run = engine.run(wf)

        assert run.status == "completed"
        assert run.node_results["a"]["status"] == "completed"

    def test_node_retry_exhausted(self, workflow_env):
        """All retries fail → final result failed."""
        engine, event_log, tmp_project = workflow_env

        wf = Workflow(name="retry-fail", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="keep failing",
                         timeout=300, retries=2),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(500, json={"error": "persistent"})
            )
            run = engine.run(wf)

        assert run.status == "failed"
        assert run.node_results["a"]["status"] == "failed"

    def test_workflow_timeout_marks_remaining(self, workflow_env):
        """Remaining nodes marked failed on workflow timeout."""
        engine, event_log, tmp_project = workflow_env

        def slow_chat(*args, **kwargs):
            time.sleep(2)
            return ("result", [])

        # A→B chain, workflow timeout of 1s. A will take 2s, so B never starts.
        wf = Workflow(name="wf-timeout", description="test", timeout=1, nodes=[
            WorkflowNode(id="a", worker="researcher", message="slow", timeout=10),
            WorkflowNode(id="b", worker="writer", message="wait",
                         depends_on=["a"], timeout=10),
        ])

        with patch("framework.worker.Worker.chat", side_effect=slow_chat):
            run = engine.run(wf)

        assert run.status == "failed"
        # B should be failed with timeout message
        assert run.node_results["b"]["status"] == "failed"
        assert "timeout" in run.node_results["b"]["error"].lower()

    def test_workflow_timeout_zero_unlimited(self, workflow_env):
        """timeout=0 does not limit."""
        engine, event_log, tmp_project = workflow_env

        wf = Workflow(name="unlimited", description="test", timeout=0, nodes=[
            WorkflowNode(id="a", worker="researcher", message="go"),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            run = engine.run(wf)

        assert run.status == "completed"

    def test_node_timeout_unblocks_layer(self, workflow_env):
        """Timed-out node doesn't block depth layer."""
        engine, event_log, tmp_project = workflow_env

        def slow_chat(*args, **kwargs):
            time.sleep(5)
            return ("result", [])

        # Two nodes at same depth: a (slow, 1s timeout) and b (fast)
        wf = Workflow(name="unblock", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="slow", timeout=1),
            WorkflowNode(id="b", worker="writer", message="fast", timeout=300),
        ])

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            with patch("framework.worker.Worker.chat") as mock_chat:
                def side_effect(msg, router, **kwargs):
                    if "slow" in msg:
                        time.sleep(5)
                    return ("done", [])
                mock_chat.side_effect = side_effect
                run = engine.run(wf)

        assert run.node_results["a"]["status"] == "failed"
        assert run.node_results["b"]["status"] == "completed"

    def test_retry_logs_attempts(self, workflow_env, caplog):
        """Logger captures retry warnings."""
        engine, event_log, tmp_project = workflow_env

        wf = Workflow(name="retry-log", description="test", nodes=[
            WorkflowNode(id="a", worker="researcher", message="retry",
                         timeout=300, retries=1),
        ])

        with caplog.at_level(logging.DEBUG):
            with respx.mock:
                respx.post(OPENROUTER_API_URL).mock(side_effect=[
                    httpx.Response(500, json={"error": "temp"}),
                    _mock_response("ok"),
                ])
                engine.run(wf)

        assert any("retry" in r.message.lower() for r in caplog.records)
