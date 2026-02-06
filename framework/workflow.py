"""DAG workflow engine — YAML-defined, parallel execution by depth layer."""

import re
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from tinydb import Query

from framework.db import get_db

from framework.config import ProjectConfig
from framework.events import Event, EventLog
from framework.exceptions import WorkflowError
from framework.hr import HR
from framework.log import get_logger
from framework.router import Router
from framework.task_router import TaskRouter
from framework.worker import Worker

logger = get_logger(__name__)


@dataclass
class WorkflowNode:
    id: str
    worker: str
    message: str
    depends_on: list[str] = field(default_factory=list)
    condition: str = "success"  # "success" | "contains:keyword"
    timeout: int = 300      # seconds per node (default 5 min)
    retries: int = 0        # max retry attempts (0 = no retries)


@dataclass
class Workflow:
    name: str
    description: str
    nodes: list[WorkflowNode]
    timeout: int = 0         # workflow-level timeout in seconds (0 = no limit)

    @staticmethod
    def load(path: Path) -> "Workflow":
        """Parse a workflow YAML file into a Workflow dataclass."""
        path = Path(path)
        if not path.exists():
            raise WorkflowError("unknown", f"Workflow file not found: {path}")

        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise WorkflowError("unknown", f"Invalid YAML: {e}")

        if not isinstance(raw, dict):
            raise WorkflowError("unknown", "Workflow file must be a YAML mapping")

        name = raw.get("name", path.stem)
        description = raw.get("description", "")
        workflow_timeout = raw.get("timeout", 0)
        nodes_raw = raw.get("nodes")

        if not nodes_raw:
            raise WorkflowError(name, "Workflow has no nodes")

        nodes = []
        for node_id, node_data in nodes_raw.items():
            if not isinstance(node_data, dict) or "worker" not in node_data:
                raise WorkflowError(name, f"Node must have a 'worker' field", node=node_id)
            nodes.append(WorkflowNode(
                id=node_id,
                worker=node_data["worker"],
                message=node_data.get("message", ""),
                depends_on=node_data.get("depends_on", []),
                condition=node_data.get("condition", "success"),
                timeout=node_data.get("timeout", 300),
                retries=node_data.get("retries", 0),
            ))

        return Workflow(name=name, description=description, nodes=nodes,
                        timeout=workflow_timeout)


@dataclass
class WorkflowRun:
    id: str
    workflow_name: str
    status: str = "pending"  # pending | running | completed | failed
    node_results: dict = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""


def topological_sort(nodes: list[WorkflowNode]) -> list[WorkflowNode]:
    """Sort nodes in dependency order. Raises WorkflowError on cycles."""
    node_map = {n.id: n for n in nodes}
    visited: set[str] = set()
    in_stack: set[str] = set()
    result: list[WorkflowNode] = []

    def visit(node_id: str):
        if node_id in in_stack:
            raise WorkflowError("unknown", f"Cycle detected involving node '{node_id}'")
        if node_id in visited:
            return
        in_stack.add(node_id)
        node = node_map[node_id]
        for dep in node.depends_on:
            if dep in node_map:
                visit(dep)
        in_stack.remove(node_id)
        visited.add(node_id)
        result.append(node)

    for n in nodes:
        visit(n.id)

    return result


def _compute_depths(nodes: list[WorkflowNode]) -> dict[str, int]:
    """Assign depth to each node. Roots = 0, others = max(dep depths) + 1."""
    node_map = {n.id: n for n in nodes}
    depths: dict[str, int] = {}

    def compute(nid: str) -> int:
        if nid in depths:
            return depths[nid]
        node = node_map[nid]
        if not node.depends_on:
            depths[nid] = 0
        else:
            depths[nid] = max(
                compute(d) for d in node.depends_on if d in node_map
            ) + 1
        return depths[nid]

    for n in nodes:
        compute(n.id)
    return depths


def _substitute_outputs(message: str, node_results: dict) -> str:
    """Replace {node_id.output} placeholders with actual outputs."""
    def replacer(match):
        node_id = match.group(1)
        result = node_results.get(node_id, {})
        return result.get("output", f"{{{{ {node_id}.output not available }}}}")

    return re.sub(r"\{(\w+)\.output\}", replacer, message)


def _check_condition(condition: str, depends_on: list[str], node_results: dict) -> bool:
    """Check whether a node's condition is met based on dependency results."""
    if condition == "success":
        return all(
            node_results.get(dep, {}).get("status") == "completed"
            for dep in depends_on
        )

    if condition.startswith("contains:"):
        keyword = condition[len("contains:"):].strip().lower()
        for dep in depends_on:
            output = node_results.get(dep, {}).get("output", "")
            if keyword in output.lower():
                return True
        return False

    # Unknown condition type — default to success check
    return all(
        node_results.get(dep, {}).get("status") == "completed"
        for dep in depends_on
    )


class WorkflowEngine:
    """Executes DAG workflows with parallel fan-out by depth layer."""

    def __init__(self, config: ProjectConfig, accountant, router: Router,
                 event_log: EventLog, db_path: Path | None = None):
        self.config = config
        self.accountant = accountant
        self.router = router
        self.event_log = event_log
        self.db_path = db_path or config.project_dir / "data" / "workflows.json"
        self._db, self._db_lock = get_db(self.db_path)

    def _execute_node(self, node: WorkflowNode, node_results: dict,
                      workflow_name: str, run_id: str) -> tuple[str, dict]:
        """Execute one node with timeout and retry support. Returns (node_id, result_dict)."""
        # Check dependencies and conditions
        if node.depends_on:
            if not _check_condition(node.condition, node.depends_on, node_results):
                return (node.id, {"status": "skipped", "output": ""})

        # Substitute outputs in message
        message = _substitute_outputs(node.message, node_results)

        max_attempts = 1 + node.retries
        last_error = None

        for attempt in range(max_attempts):
            if attempt > 0:
                logger.warning("Retry %d/%d for node %s in workflow %s",
                               attempt, node.retries, node.id, workflow_name)

            try:
                result = self._run_node_with_timeout(node, message, node.timeout)
                self.event_log.emit(Event(
                    type="workflow.node_completed",
                    source=f"workflow:{workflow_name}",
                    data={"run_id": run_id, "node": node.id, "status": "completed"},
                ))
                return (node.id, result)
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    continue  # retry
                break

        # All attempts exhausted
        error_msg = str(last_error)
        logger.warning("Node failed: workflow=%s, node=%s, error=%s",
                       workflow_name, node.id, error_msg)
        result = {"status": "failed", "output": "", "error": error_msg}
        self.event_log.emit(Event(
            type="workflow.node_completed",
            source=f"workflow:{workflow_name}",
            data={"run_id": run_id, "node": node.id, "status": "failed",
                  "error": error_msg},
        ))
        return (node.id, result)

    def _run_node_with_timeout(self, node: WorkflowNode, message: str,
                               timeout: int) -> dict:
        """Run a single node attempt with timeout. Returns result dict or raises."""
        worker_name = node.worker
        if worker_name == "auto":
            hr = HR(self.config, self.config.project_dir)
            task_router = TaskRouter(self.config, hr)
            selected = task_router.select_worker(message)
            if selected is None:
                raise RuntimeError("No workers available for auto-routing")
            worker_name = selected

        worker = Worker(worker_name, self.config.project_dir, self.config)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.chat, message, self.router)
            try:
                response, _ = future.result(timeout=timeout)
            except FuturesTimeoutError:
                raise TimeoutError(f"Node '{node.id}' timed out after {timeout}s")

        return {"status": "completed", "output": response[:2000]}

    def run(self, workflow: Workflow, max_workers: int = 4) -> WorkflowRun:
        """Execute a workflow with parallel fan-out. Returns the completed WorkflowRun."""
        sorted_nodes = topological_sort(workflow.nodes)
        depths = _compute_depths(sorted_nodes)

        run = WorkflowRun(
            id=uuid.uuid4().hex[:8],
            workflow_name=workflow.name,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info("Workflow started: name=%s, run=%s, nodes=%d",
                    workflow.name, run.id, len(sorted_nodes))

        self.event_log.emit(Event(
            type="workflow.started",
            source=f"workflow:{workflow.name}",
            data={"run_id": run.id, "nodes": [n.id for n in sorted_nodes]},
        ))

        # Group nodes by depth for parallel execution
        by_depth: dict[int, list[WorkflowNode]] = defaultdict(list)
        for node in sorted_nodes:
            by_depth[depths[node.id]].append(node)

        has_failures = False
        result_lock = threading.Lock()
        start_time = time.monotonic()

        for depth in sorted(by_depth):
            # Check workflow-level timeout before each depth layer
            if workflow.timeout > 0:
                elapsed = time.monotonic() - start_time
                if elapsed >= workflow.timeout:
                    # Mark remaining nodes as failed
                    for remaining_depth in sorted(by_depth):
                        if remaining_depth < depth:
                            continue
                        for node in by_depth[remaining_depth]:
                            if node.id not in run.node_results:
                                run.node_results[node.id] = {
                                    "status": "failed",
                                    "output": "",
                                    "error": "Workflow timeout exceeded",
                                }
                    has_failures = True
                    break

            nodes_at_depth = by_depth[depth]
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        self._execute_node, node, run.node_results,
                        workflow.name, run.id,
                    ): node.id
                    for node in nodes_at_depth
                }
                for future in as_completed(futures):
                    node_id, result = future.result()
                    with result_lock:
                        run.node_results[node_id] = result
                    if result["status"] == "failed":
                        has_failures = True

        run.status = "failed" if has_failures else "completed"
        run.completed_at = datetime.now(timezone.utc).isoformat()

        # Persist run
        with self._db_lock:
            self._db.insert({
                "id": run.id,
                "workflow_name": run.workflow_name,
                "status": run.status,
                "node_results": run.node_results,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
            })

        logger.info("Workflow %s: name=%s, run=%s", run.status, workflow.name, run.id)

        event_type = "workflow.completed" if run.status == "completed" else "workflow.failed"
        self.event_log.emit(Event(
            type=event_type,
            source=f"workflow:{workflow.name}",
            data={"run_id": run.id, "status": run.status},
        ))

        return run

    def list_runs(self, workflow_name: str | None = None) -> list[dict]:
        """List workflow runs, optionally filtered by name."""
        with self._db_lock:
            if workflow_name:
                Q = Query()
                return self._db.search(Q.workflow_name == workflow_name)
            return self._db.all()

    def get_run(self, run_id: str) -> dict | None:
        """Get a single workflow run by ID."""
        Q = Query()
        with self._db_lock:
            results = self._db.search(Q.id == run_id)
        return results[0] if results else None
